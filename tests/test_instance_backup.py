"""Sauvegardes d'instance : archive .zip (base + pièces), restauration .zip / .db, archives hostiles."""
import io
import sqlite3
import stat
import zipfile
from types import SimpleNamespace

import pytest
from werkzeug.datastructures import FileStorage

from app.services import instance_backup as ib
from app.services.instance_backup import BackupError


@pytest.fixture()
def inst(app, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "instance_path", str(tmp_path))
    db_path = tmp_path / "tenants" / "sci.db"
    db_path.parent.mkdir()
    _make_db(db_path, "avant")
    uploads = tmp_path / "uploads" / "sci"
    (uploads / "achats" / "2026" / "09").mkdir(parents=True)
    (uploads / "achats" / "2026" / "09" / "3-ticket.pdf").write_bytes(b"%PDF ticket")
    (uploads / "tmp").mkdir()
    (uploads / "tmp" / "abc").write_bytes(b"en attente")
    return SimpleNamespace(id=999, slug="sci", database_url=f"sqlite:///{db_path}", db_path=db_path,
                           uploads=uploads)


def _make_db(path, value):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS t (v TEXT)")
    conn.execute("DELETE FROM t")
    conn.execute("INSERT INTO t VALUES (?)", (value,))
    conn.commit()
    conn.close()


def _value(path):
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT v FROM t").fetchone()[0]
    finally:
        conn.close()


def _db_bytes(tmp_path, value):
    path = tmp_path / f"src-{value}.db"
    _make_db(path, value)
    return path.read_bytes()


def _zip(members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in members.items():
            if isinstance(data, zipfile.ZipInfo):
                z.writestr(data, b"x")
            else:
                z.writestr(name, data)
    return buf.getvalue()


def upload(blob, name="sci-20261022-120000.zip"):
    return FileStorage(stream=io.BytesIO(blob), filename=name)


def _files(root):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


# ------------------------------------------------------------------ création

def test_backup_is_zip_with_database_and_attachments(inst):
    path = ib.create_backup(inst)
    assert path.name.startswith("sci-") and path.suffix == ".zip"
    with zipfile.ZipFile(path) as z:
        assert sorted(z.namelist()) == ["database.db", "uploads/achats/2026/09/3-ticket.pdf"]
        assert z.read("database.db").startswith(ib.SQLITE_MAGIC)
    assert [b.filename for b in ib.list_backups(inst)] == [path.name]
    assert not list(path.parent.glob("*.partial"))


def test_legacy_db_backups_listed_and_downloadable(inst):
    legacy = ib._backups_dir() / "sci-20250101-000000.db"
    legacy.write_bytes(b"x")
    (ib._backups_dir() / "autre-20250101-000000.zip").write_bytes(b"x")
    assert [b.filename for b in ib.list_backups(inst)] == ["sci-20250101-000000.db"]
    assert ib.backup_path(inst, legacy.name) == legacy
    with pytest.raises(BackupError):
        ib.backup_path(inst, "../sci-20250101-000000.db")


# ------------------------------------------------------------------ restauration

def test_restore_zip_replaces_database_and_attachments(inst, tmp_path):
    blob = _zip({"database.db": _db_bytes(tmp_path, "après"),
                 "uploads/achats/2026/10/7-free.pdf": b"%PDF free"})
    pre, target = ib.restore_from_upload(inst, upload(blob))
    assert _value(inst.db_path) == "après" and target == inst.db_path
    assert _files(inst.uploads) == ["achats/2026/10/7-free.pdf"]
    # La sauvegarde de sécurité contient l'état d'avant (base et pièces).
    with zipfile.ZipFile(pre) as z:
        assert pre.name.startswith("pre-restore-sci-")
        assert "uploads/achats/2026/09/3-ticket.pdf" in z.namelist()
    assert not list(inst.uploads.parent.glob(".incoming-*"))


def test_restore_round_trip(inst):
    backup = ib.create_backup(inst).read_bytes()
    _make_db(inst.db_path, "modifiée")
    (inst.uploads / "achats" / "2026" / "09" / "3-ticket.pdf").unlink()
    ib.restore_from_upload(inst, upload(backup))
    assert _value(inst.db_path) == "avant"
    assert _files(inst.uploads) == ["achats/2026/09/3-ticket.pdf"]


def test_restore_legacy_db_keeps_attachments(inst, tmp_path):
    ib.restore_from_upload(inst, upload(_db_bytes(tmp_path, "db seule"), "sci.db"))
    assert _value(inst.db_path) == "db seule"
    assert "achats/2026/09/3-ticket.pdf" in _files(inst.uploads)


def _symlink_info():
    info = zipfile.ZipInfo("uploads/lien")
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    return info


@pytest.mark.parametrize("members, message", [
    ({"database.db": "DB", "uploads/../../evil.txt": b"x"}, "chemin interdit"),
    ({"database.db": "DB", "/etc/passwd": b"x"}, "chemin interdit"),
    ({"database.db": "DB", "uploads\\..\\evil": b"x"}, "chemin interdit"),
    ({"database.db": "DB", "C:/evil": b"x"}, "chemin interdit"),
    ({"database.db": "DB", "run.py": b"x"}, "contenu inattendu"),
    ({"database.db": "DB", "uploads/lien": "LINK"}, "chemin interdit"),
    ({"uploads/a.pdf": b"x"}, "absent"),
    ({"database.db": b"pas une base"}, "pas une base SQLite"),
])
def test_hostile_archives_change_nothing(inst, tmp_path, members, message):
    members = {k: (_db_bytes(tmp_path, "pirate") if v == "DB" else _symlink_info() if v == "LINK" else v)
               for k, v in members.items()}
    before = _files(inst.uploads)
    with pytest.raises(BackupError, match=message):
        ib.restore_from_upload(inst, upload(_zip(members)))
    assert _value(inst.db_path) == "avant" and _files(inst.uploads) == before
    assert ib.list_backups(inst) == []  # refusée avant la sauvegarde de sécurité
    assert not (tmp_path / "evil.txt").exists()


def test_archive_limits(inst, tmp_path, monkeypatch):
    monkeypatch.setattr(ib, "MAX_ARCHIVE_UNCOMPRESSED", 10)
    blob = _zip({"database.db": _db_bytes(tmp_path, "x")})
    with pytest.raises(BackupError, match="trop volumineux"):
        ib.restore_from_upload(inst, upload(blob))
    monkeypatch.setattr(ib, "MAX_ARCHIVE_MEMBERS", 1)
    monkeypatch.setattr(ib, "MAX_ARCHIVE_UNCOMPRESSED", 10**9)
    with pytest.raises(BackupError, match="trop de fichiers"):
        ib.restore_from_upload(inst, upload(_zip({"database.db": _db_bytes(tmp_path, "y"),
                                                   "uploads/a": b"a"})))


def test_unknown_or_corrupt_files(inst):
    with pytest.raises(BackupError, match="ni une base SQLite ni une archive"):
        ib.restore_from_upload(inst, upload(b"MZ executable"))
    with pytest.raises(BackupError, match="Archive illisible"):
        ib.restore_from_upload(inst, upload(b"PK\x03\x04 tronquee"))


def test_new_instance_from_archive(inst, tmp_path):
    blob = _zip({"database.db": _db_bytes(tmp_path, "nouvelle"), "uploads/achats/x.pdf": b"%PDF"})
    target = tmp_path / "tenants" / "neuve.db"
    ib.stage_upload_to_path(upload(blob, "neuve-20261022-120000.zip"), target, "neuve")
    assert _value(target) == "nouvelle"
    assert _files(tmp_path / "uploads" / "neuve") == ["achats/x.pdf"]


def test_slug_from_archive_name():
    assert ib.extract_slug_from_filename("chenes-verts-20261022-120000.zip") == "chenes-verts"
    assert ib.extract_slug_from_filename("pre-restore-sci-20261022-120000.zip") == "sci"
    assert ib.extract_slug_from_filename("Mon Archive.zip") is None


def test_backup_routes(app, tmp_path, monkeypatch, login_as):
    from app.models import Instance
    monkeypatch.setattr(app, "instance_path", str(tmp_path))
    client = login_as(is_admin=True)
    inst = Instance.query.filter_by(slug="test").one()
    (tmp_path / "uploads" / "test").mkdir(parents=True)
    (tmp_path / "uploads" / "test" / "a.pdf").write_bytes(b"%PDF")
    client.post(f"/instances/{inst.id}/backup")
    (backup,) = ib.list_backups(inst)
    page = client.get(f"/instances/{inst.id}").get_data(as_text=True)
    assert backup.filename in page and "base seule" not in page
    response = client.get(f"/instances/{inst.id}/backups/{backup.filename}/download")
    assert response.mimetype == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.data)) as z:
        assert sorted(z.namelist()) == ["database.db", "uploads/a.pdf"]
    assert ".zip" in client.get(f"/instances/{inst.id}/restore").get_data(as_text=True)
