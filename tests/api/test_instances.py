"""API des instances (admin, méta-base) : liste, création, modification ; pages de la SPA."""
import pytest

from app.extensions import db
from app.models import Instance
from app.services import instance_provisioning


def _error(resp, status):
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()["error"]


@pytest.fixture()
def admin(app, tmp_path, monkeypatch, login_as):
    # Création automatique : la base SQLite de la nouvelle instance est créée ici.
    monkeypatch.setattr(app, "instance_path", str(tmp_path / "instance"))
    monkeypatch.setattr(instance_provisioning, "BASE_DIR", tmp_path)
    return login_as(is_admin=True)


def test_spa_pages(admin):
    inst = Instance.query.filter_by(slug="test").one()
    for url in ("/instances/", "/instances/new", "/instances/import", f"/instances/{inst.id}",
                f"/instances/{inst.id}/edit", f"/instances/{inst.id}/restore"):
        assert 'id="root"' in admin.get(url).get_data(as_text=True), url


def test_list_and_detail(admin):
    body = admin.get("/api/v1/instances").get_json()
    assert [i["slug"] for i in body["items"]] == ["test"]
    assert {c["value"] for c in body["meta"]["charts"]} == {"asso", "sci", "societe"}
    detail = admin.get(f"/api/v1/instances/{body['items'][0]['id']}").get_json()
    assert detail["item"]["sqlite"] is True and detail["backups"] == []
    _error(admin.get("/api/v1/instances/999"), 404)


def test_create_auto_and_validation(admin, monkeypatch):
    calls = []
    # Le provisioning (migrations en sous-processus) est testé à part : ici, l'appel suffit.
    monkeypatch.setattr("app.api.instances.provision_sqlite_database", lambda url, chart: calls.append((url, chart)))
    resp = admin.post("/api/v1/instances", json={"slug": "sci-dupont", "label": "SCI Dupont", "chart": "sci"})
    assert resp.status_code == 201, resp.get_json()
    inst = Instance.query.filter_by(slug="sci-dupont").one()
    assert inst.chart == "sci" and inst.database_url == "sqlite:///tenants/sci-dupont.db"
    assert calls == [("sqlite:///tenants/sci-dupont.db", "sci")]
    assert "slug" in _error(admin.post("/api/v1/instances", json={"slug": "sci-dupont", "label": "x"}), 422)["fields"]
    assert "slug" in _error(admin.post("/api/v1/instances", json={"slug": "Pas Bon!", "label": "x"}), 422)["fields"]
    assert "label" in _error(admin.post("/api/v1/instances", json={"slug": "ok-ok", "label": " "}), 422)["fields"]
    err = _error(admin.post("/api/v1/instances", json={"slug": "pg-asso", "label": "PG", "provisioning_mode": "manual"}), 422)
    assert "database_url" in err["fields"]


def test_create_manual_masks_password(admin):
    resp = admin.post("/api/v1/instances", json={"slug": "pg-asso", "label": "PG", "provisioning_mode": "manual",
                                                 "database_url": "postgresql://u:motdepasse@h/db"})
    assert resp.status_code == 201
    assert resp.get_json()["item"]["database"] == "postgresql://u:***@h/db"
    assert resp.get_json()["item"]["sqlite"] is False
    pg = Instance.query.filter_by(slug="pg-asso").one()
    assert _error(admin.post(f"/api/v1/instances/{pg.id}/backups"), 409)["code"] == "conflict"


def test_update(admin):
    inst = Instance.query.filter_by(slug="test").one()
    body = admin.patch(f"/api/v1/instances/{inst.id}", json={"label": "Test 2", "is_active": False}).get_json()
    assert body["item"]["label"] == "Test 2" and body["item"]["is_active"] is False
    _error(admin.patch(f"/api/v1/instances/{inst.id}", json={"label": ""}), 422)


def test_admin_only(login_as):
    client = login_as()
    _error(client.get("/api/v1/instances"), 403)
    _error(client.post("/api/v1/instances", json={}), 403)


def test_works_without_selected_instance(admin):
    with admin.session_transaction() as sess:
        sess.pop("instance_id")
    assert admin.get("/api/v1/instances").status_code == 200
    assert admin.get("/api/v1/integrations").status_code == 409  # intégrations : propres à une instance
