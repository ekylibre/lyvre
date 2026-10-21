"""SQLite backup and restore for tenant instances.

A backup is a `.zip` archive named `<slug>-YYYYMMDD-HHMMSS.zip` in
`<instance_folder>/backups/`: `database.db` (atomic copy made with SQLite's
online backup API) plus `uploads/…`, the instance's attachment folder
(`instance/uploads/<slug>/`, purchase invoices). Older `.db` backups (database
only) are still listed, downloadable and restorable. Restoring an archive
replaces the database and the attachment folder; a `.db` leaves attachments as
they are. Archive member names are checked (no absolute path, no `..`, no link,
only `database.db` and `uploads/…`) and sizes are bounded.

Postgres instances are out of scope: any call on a non-SQLite database_url
raises BackupError.
"""

from __future__ import annotations

import io
import os
import re
import secrets
import shutil
import sqlite3
import stat
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath

from flask import current_app

from app.tenant import clear_engine_cache


SQLITE_MAGIC = b"SQLite format 3\x00"
ZIP_MAGIC = b"PK\x03\x04"
ARCHIVE_DB = "database.db"
ARCHIVE_UPLOADS = "uploads/"
MAX_ARCHIVE_MEMBERS = 50_000
MAX_ARCHIVE_UNCOMPRESSED = 4 * 1024 * 1024 * 1024  # 4 Go
PRE_RESTORE_PREFIX = "pre-restore-"
MAX_BACKUP_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MB


class BackupError(RuntimeError):
    pass


@dataclass
class BackupFile:
    filename: str
    path: Path
    size_bytes: int
    created_at: datetime
    is_pre_restore: bool


def _backups_dir() -> Path:
    path = Path(current_app.instance_path) / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _resolve_sqlite_path(database_url: str) -> Path:
    """Return absolute filesystem path for a SQLite URL, or raise BackupError."""
    if not database_url.startswith("sqlite:///"):
        raise BackupError(
            "Sauvegardes disponibles uniquement pour les instances SQLite "
            "(URL actuelle : non-SQLite). Utilisez pg_dump pour Postgres."
        )
    raw = database_url[len("sqlite:///"):]
    path = Path(raw)
    if not path.is_absolute():
        path = Path(current_app.instance_path) / raw
    return path


def _filename_re(slug: str) -> re.Pattern:
    # <slug>-YYYYMMDD-HHMMSS.zip (or .db, older backups), optionally prefixed by 'pre-restore-'
    return re.compile(
        rf"^({re.escape(PRE_RESTORE_PREFIX)})?{re.escape(slug)}-\d{{8}}-\d{{6}}\.(?:zip|db)$"
    )


def _uploads_dir(slug: str) -> Path:
    from app.services.attachments import uploads_dir_for

    return uploads_dir_for(slug)


def _safe_backup_path(instance, filename: str) -> Path:
    if not _filename_re(instance.slug).match(filename):
        raise BackupError("Nom de fichier de sauvegarde invalide.")
    path = _backups_dir() / filename
    # Resolve and confirm the path stays inside backups dir (defense in depth).
    if not str(path.resolve()).startswith(str(_backups_dir().resolve())):
        raise BackupError("Chemin de sauvegarde hors du dossier autorisé.")
    return path


def list_backups(instance) -> list[BackupFile]:
    """Return all backups for this instance, newest first."""
    pattern = _filename_re(instance.slug)
    out: list[BackupFile] = []
    backups_dir = _backups_dir()
    for entry in backups_dir.iterdir():
        if not entry.is_file():
            continue
        if not pattern.match(entry.name):
            continue
        stat = entry.stat()
        out.append(BackupFile(
            filename=entry.name,
            path=entry,
            size_bytes=stat.st_size,
            created_at=datetime.fromtimestamp(stat.st_mtime),
            is_pre_restore=entry.name.startswith(PRE_RESTORE_PREFIX),
        ))
    out.sort(key=lambda b: b.created_at, reverse=True)
    return out


def create_backup(instance, prefix: str = "") -> Path:
    """Archive the instance: atomic copy of its SQLite database + its attachment folder."""
    src_path = _resolve_sqlite_path(instance.database_url)
    if not src_path.exists():
        raise BackupError(f"Base introuvable : {src_path}")

    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    target = _backups_dir() / f"{prefix}{instance.slug}-{timestamp}.zip"
    db_copy = target.with_suffix(".db.partial")
    partial = target.with_suffix(".zip.partial")

    src = sqlite3.connect(str(src_path))
    try:
        dst = sqlite3.connect(str(db_copy))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()

    from app.services.attachments import STAGING_DIR

    try:
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(db_copy, ARCHIVE_DB)
            uploads = _uploads_dir(instance.slug)
            if uploads.is_dir():
                for path in sorted(uploads.rglob("*")):
                    relative = path.relative_to(uploads)
                    if path.is_file() and not path.is_symlink() and relative.parts[0] != STAGING_DIR:
                        archive.write(path, ARCHIVE_UPLOADS + relative.as_posix())
        os.replace(partial, target)
    finally:
        db_copy.unlink(missing_ok=True)
        partial.unlink(missing_ok=True)
    return target


def delete_backup(instance, filename: str) -> None:
    path = _safe_backup_path(instance, filename)
    if not path.exists():
        raise BackupError("Sauvegarde introuvable.")
    path.unlink()


def backup_path(instance, filename: str) -> Path:
    path = _safe_backup_path(instance, filename)
    if not path.exists():
        raise BackupError("Sauvegarde introuvable.")
    return path


def _read_upload(uploaded_file) -> tuple[str, bytes]:
    """Read the upload into memory after sanity checks: ("db" | "zip", bytes)."""
    # Werkzeug FileStorage; size already capped by MAX_CONTENT_LENGTH.
    head = uploaded_file.stream.read(16)
    if head == SQLITE_MAGIC:
        kind = "db"
    elif head.startswith(ZIP_MAGIC):
        kind = "zip"
    else:
        raise BackupError(
            "Le fichier n'est ni une base SQLite ni une archive de sauvegarde (.zip)."
        )
    body = uploaded_file.stream.read(MAX_BACKUP_UPLOAD_BYTES + 1)
    if len(body) > MAX_BACKUP_UPLOAD_BYTES:
        raise BackupError(
            f"Le fichier dépasse la taille maximale "
            f"({MAX_BACKUP_UPLOAD_BYTES // (1024 * 1024)} Mo)."
        )
    return kind, head + body


def _open_archive(blob: bytes) -> tuple[zipfile.ZipFile, list[zipfile.ZipInfo]]:
    """Open a backup archive and check its members; returns (archive, attachment members)."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile as e:
        raise BackupError(f"Archive illisible : {e}") from e
    infos = archive.infolist()
    if len(infos) > MAX_ARCHIVE_MEMBERS:
        raise BackupError("Archive refusée : trop de fichiers.")
    if sum(i.file_size for i in infos) > MAX_ARCHIVE_UNCOMPRESSED:
        raise BackupError("Archive refusée : contenu décompressé trop volumineux.")
    uploads, has_db = [], False
    for info in infos:
        name = info.filename
        parts = PurePosixPath(name).parts
        if (name.startswith(("/", "\\")) or "\\" in name or ".." in parts or ":" in name
                or stat.S_ISLNK(info.external_attr >> 16)):
            raise BackupError(f"Archive refusée : chemin interdit « {name} ».")
        if name == ARCHIVE_DB:
            has_db = True
        elif name.startswith(ARCHIVE_UPLOADS):
            if not info.is_dir() and name != ARCHIVE_UPLOADS:
                uploads.append(info)
        else:
            raise BackupError(f"Archive refusée : contenu inattendu « {name} ».")
    if not has_db:
        raise BackupError(f"Archive refusée : « {ARCHIVE_DB} » absent.")
    return archive, uploads


def _extract_uploads(archive: zipfile.ZipFile, members, slug: str) -> Path:
    """Extract attachments into a staging folder next to the instance's folder."""
    final = _uploads_dir(slug)
    staged = final.parent / f".incoming-{final.name}-{secrets.token_hex(4)}"
    staged.mkdir(parents=True)
    root = staged.resolve()
    try:
        for info in members:
            target = (staged / info.filename[len(ARCHIVE_UPLOADS):]).resolve()
            if not target.is_relative_to(root):
                raise BackupError(f"Archive refusée : chemin interdit « {info.filename} ».")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
    except Exception:
        shutil.rmtree(staged, ignore_errors=True)
        raise
    return staged


def _swap_uploads(slug: str, staged: Path) -> None:
    """Replace the instance's attachment folder by the extracted one."""
    final = _uploads_dir(slug)
    if final.exists():
        shutil.rmtree(final)
    os.replace(staged, final)


def _database_blob(kind: str, blob: bytes):
    """(database bytes, archive or None, attachment members)."""
    if kind == "db":
        return blob, None, []
    archive, members = _open_archive(blob)
    data = archive.read(ARCHIVE_DB)
    if not data.startswith(SQLITE_MAGIC):
        raise BackupError(f"« {ARCHIVE_DB} » n'est pas une base SQLite valide.")
    return data, archive, members


def _stage_and_validate(blob: bytes, target_path: Path) -> Path:
    """Write blob next to target_path, integrity-check, return temp path.

    Caller is responsible for the final os.replace(tmp, target). On failure
    the temp file is removed and BackupError is raised.
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_suffix(target_path.suffix + ".incoming")
    tmp_path.write_bytes(blob)
    try:
        conn = sqlite3.connect(str(tmp_path))
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise BackupError(
                    f"PRAGMA integrity_check a échoué : {result[0] if result else 'aucun résultat'}"
                )
        finally:
            conn.close()
    except sqlite3.DatabaseError as e:
        tmp_path.unlink(missing_ok=True)
        raise BackupError(f"Fichier SQLite invalide : {e}") from e
    except BackupError:
        tmp_path.unlink(missing_ok=True)
        raise
    return tmp_path


def _install(uploaded_file, target_path: Path, slug: str, before_replace=None):
    """Validate the upload (.db or .zip), then put database (and attachments) in place."""
    kind, blob = _read_upload(uploaded_file)
    data, archive, members = _database_blob(kind, blob)
    tmp_path = _stage_and_validate(data, target_path)
    staged = None
    try:
        if archive is not None:
            staged = _extract_uploads(archive, members, slug)
        result = before_replace() if before_replace else None
    except Exception:
        tmp_path.unlink(missing_ok=True)
        if staged is not None:
            shutil.rmtree(staged, ignore_errors=True)
        raise
    # Atomic replace (same filesystem); attachments follow the archive.
    os.replace(tmp_path, target_path)
    if staged is not None:
        _swap_uploads(slug, staged)
    return result


def restore_from_upload(instance, uploaded_file) -> tuple[Path, Path]:
    """Replace the instance DB (and, for an archive, its attachments) with the upload.

    Returns (pre_restore_backup_path, restored_target_path).
    """
    target_path = _resolve_sqlite_path(instance.database_url)
    # Safety: snapshot the current DB and attachments before overwriting.
    pre_backup = _install(uploaded_file, target_path, instance.slug,
                          before_replace=lambda: create_backup(instance, prefix=PRE_RESTORE_PREFIX))

    # Drop cached engine so the next request opens the new file.
    clear_engine_cache(instance.id)

    return pre_backup, target_path


_TIMESTAMPED_RE = re.compile(
    r"^(?P<slug>[a-z0-9][a-z0-9-]*[a-z0-9])-\d{8}-\d{6}\.(?:db|sqlite|backup|zip)$",
    re.IGNORECASE,
)
_PLAIN_RE = re.compile(
    r"^(?P<slug>[a-z0-9][a-z0-9-]*[a-z0-9])\.(?:db|sqlite|backup|zip)$",
    re.IGNORECASE,
)


def extract_slug_from_filename(filename: str) -> str | None:
    """Best-effort slug extraction from an uploaded filename.

    - 'seconde-nature.db'                       → 'seconde-nature'
    - 'seconde-nature-20260521-175502.db'       → 'seconde-nature'
    - 'pre-restore-seconde-nature-20260521-…' → 'seconde-nature'
    - 'export.backup'                           → 'export'
    - 'seconde-nature-20260521-175502.zip'      → 'seconde-nature'
    - 'Mon Archive.zip'                         → None
    """
    if not filename:
        return None
    stem = Path(filename).name
    if stem.lower().startswith("pre-restore-"):
        stem = stem[len("pre-restore-"):]
    match = _TIMESTAMPED_RE.match(stem) or _PLAIN_RE.match(stem)
    if not match:
        return None
    return match.group("slug").lower()


def stage_upload_to_path(uploaded_file, target_path: Path, slug: str) -> None:
    """Validate the upload and atomically write it to target_path (attachments of an
    archive go to the instance's folder).

    Used for NEW instance creation from upload (no pre-restore backup).
    """
    _install(uploaded_file, target_path, slug)


def is_sqlite_instance(instance) -> bool:
    return instance.database_url.startswith("sqlite:///")


def total_size_bytes(instance) -> int:
    return sum(b.size_bytes for b in list_backups(instance))
