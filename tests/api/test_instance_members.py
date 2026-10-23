"""Utilisateurs et rôles à la création d'une instance, à l'import d'un fichier et depuis la fiche
instance (E2, claudedocs/design_acces_instances.md §4.1 à §4.3)."""
import io
import json
import sqlite3
import zipfile

import pytest

from app.extensions import db
from app.models import Instance, InstanceMembership, User
from app.services import instance_provisioning


def _error(resp, status):
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()["error"]


def _user(email, *, is_active=True):
    user = User(email=email, is_active=is_active)
    user.set_password("x")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture()
def admin(app, tmp_path, monkeypatch, login_as):
    monkeypatch.setattr(app, "instance_path", str(tmp_path / "instance"))
    monkeypatch.setattr(instance_provisioning, "BASE_DIR", tmp_path)
    return login_as(is_admin=True)


@pytest.fixture()
def provisioned(monkeypatch, tmp_path):
    """Provisioning simulé : crée le fichier comme le vrai, sans migrations en sous-processus."""
    created = []

    def fake(url, chart):
        path = instance_provisioning.database_file_for_url(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"db")
        created.append(path)

    monkeypatch.setattr("app.api.instances.provision_sqlite_database", fake)
    return created


def _new(admin, members, slug="asso-x"):
    return admin.post("/api/v1/instances", json={"slug": slug, "label": "Asso X", "members": members})


# ------------------------------------------------------------------ création


def test_create_with_existing_and_new_users(admin, provisioned):
    marie = _user("marie@asso.fr")
    resp = _new(admin, [{"user_id": marie.id, "role": "treasurer"},
                        {"email": "paul@asso.fr", "full_name": "Paul", "password": "motdepasse", "role": "admin"}])
    assert resp.status_code == 201, resp.get_json()
    notices = resp.get_json()["notices"]
    assert notices == [{"level": "success", "message": "Instance « Asso X » créée ; 1 compte créé, 2 accès donnés."}]
    inst = Instance.query.filter_by(slug="asso-x").one()
    paul = User.query.filter_by(email="paul@asso.fr").one()
    assert paul.must_change_password and paul.check_password("motdepasse")
    roles = {m.user.email: m.role for m in InstanceMembership.query.filter_by(instance_id=inst.id)}
    assert roles == {"marie@asso.fr": "treasurer", "paul@asso.fr": "admin"}
    assert "password" not in json.dumps(resp.get_json()).replace("must_change_password", "")


def test_create_without_users_and_warnings(admin, provisioned):
    resp = _new(admin, [])
    assert resp.get_json()["notices"] == [{"level": "success", "message": "Instance « Asso X » créée."}]
    sleeping = _user("dort@asso.fr", is_active=False)
    notices = _new(admin, [{"user_id": sleeping.id, "role": "treasurer"}], slug="asso-y").get_json()["notices"]
    assert [n["level"] for n in notices] == ["success", "warning", "warning"]
    assert "Aucun administrateur" in notices[1]["message"] and "dort@asso.fr" in notices[2]["message"]


def test_invalid_line_creates_nothing(admin, provisioned):
    users = User.query.count()
    err = _error(_new(admin, [{"email": "paul@asso.fr", "password": "motdepasse", "role": "admin"},
                              {"email": "lea@asso.fr", "password": "court", "role": "treasurer"}]), 422)
    assert list(err["fields"]) == ["members.1.password"]
    assert provisioned == []  # refus avant le provisioning
    assert Instance.query.filter_by(slug="asso-x").count() == 0 and User.query.count() == users


def test_failure_after_provisioning_removes_the_database(admin, provisioned, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("panne")

    monkeypatch.setattr("app.services.instance_access.apply_grants", boom)
    with pytest.raises(RuntimeError):
        _new(admin, [{"email": "paul@asso.fr", "password": "motdepasse", "role": "admin"}])
    assert len(provisioned) == 1 and not provisioned[0].exists()
    assert Instance.query.filter_by(slug="asso-x").count() == 0
    assert User.query.filter_by(email="paul@asso.fr").count() == 0


# ------------------------------------------------------------------ import


def _archive(tmp_path):
    path = tmp_path / "source.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE IF NOT EXISTS t (v TEXT)")
    con.commit()
    con.close()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("database.db", path.read_bytes())
        archive.writestr("uploads/f.pdf", b"%PDF")
    return buffer.getvalue()


def _import(admin, blob, name, **fields):
    return admin.post("/api/v1/instances/import", data={"backup_file": (io.BytesIO(blob), name), **fields},
                      content_type="multipart/form-data")


def test_import_creates_instance_with_users(admin, tmp_path):
    members = json.dumps([{"email": "expert@cabinet.fr", "password": "motdepasse", "role": "accountant"}])
    resp = _import(admin, _archive(tmp_path), "asso-z-20261023-120000.zip", members=members)
    assert resp.status_code == 201, resp.get_json()
    assert "1 compte créé, 1 accès donné" in resp.get_json()["notices"][0]["message"]
    inst = Instance.query.filter_by(slug="asso-z").one()
    assert InstanceMembership.query.filter_by(instance_id=inst.id).one().role == "accountant"


def test_import_invalid_users_installs_nothing(admin, tmp_path):
    members = json.dumps([{"email": "expert@cabinet.fr", "password": "court", "role": "accountant"}])
    err = _error(_import(admin, _archive(tmp_path), "asso-z.zip", members=members), 422)
    assert "members.0.password" in err["fields"]
    assert not (tmp_path / "instance" / "tenants" / "asso-z.db").exists()
    assert "members" in _error(_import(admin, _archive(tmp_path), "asso-z.zip", members="{pas du json"), 422)["fields"]


def test_import_failure_after_install_cleans_up(admin, tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("panne")

    monkeypatch.setattr("app.services.instance_access.apply_grants", boom)
    with pytest.raises(RuntimeError):
        _import(admin, _archive(tmp_path), "asso-z.zip")
    assert not (tmp_path / "instance" / "tenants" / "asso-z.db").exists()
    assert not (tmp_path / "instance" / "uploads" / "asso-z").exists()
    assert Instance.query.filter_by(slug="asso-z").count() == 0


def test_restore_refuses_members(admin, tmp_path):
    members = json.dumps([{"email": "x@y.fr", "password": "motdepasse", "role": "admin"}])
    err = _error(_import(admin, _archive(tmp_path), "test.zip", confirm="test", members=members), 422)
    assert "ne modifie pas les accès" in err["message"]


# ------------------------------------------------------------------ fiche instance


def test_members_from_instance_page(admin):
    inst = Instance(slug="dormante", label="Dormante", database_url="sqlite:///tenants/dormante.db", is_active=False)
    db.session.add(inst)
    db.session.commit()
    base = f"/api/v1/instances/{inst.id}/members"
    body = admin.get(base).get_json()
    assert [m["email"] for m in body["items"]] == ["admin@example.org"] and len(body["meta"]["roles"]) == 3

    resp = admin.post(base, json={"email": "paul@asso.fr", "password": "motdepasse", "role": "admin"})
    assert resp.status_code == 201 and "Compte créé et accès donné" in resp.get_json()["notices"][0]["message"]
    marie = _user("marie@asso.fr")
    assert admin.post(base, json={"user_id": marie.id, "role": "treasurer"}).status_code == 201
    paul = User.query.filter_by(email="paul@asso.fr").one()
    assert "au moins un administrateur" in _error(admin.patch(f"{base}/{paul.id}", json={"role": "treasurer"}), 409)["message"]
    assert admin.patch(f"{base}/{marie.id}", json={"role": "admin"}).status_code == 200
    assert admin.delete(f"{base}/{paul.id}").status_code == 200
    assert {m.user_id: m.role for m in InstanceMembership.query.filter_by(instance_id=inst.id)} == {marie.id: "admin"}
    _error(admin.get("/api/v1/instances/999/members"), 404)


def test_instance_page_members_admin_only(login_as):
    client = login_as(role="admin")  # administrateur de l'instance, pas administrateur global
    inst = Instance.query.filter_by(slug="test").one()
    assert client.get(f"/api/v1/instances/{inst.id}/members").status_code == 403
