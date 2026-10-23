"""API de session de la SPA : connexion, instance, menus, préférences, tâches."""
import json

from app.extensions import db
from app.models import Instance, SyncJob, User


def _user(email="tresorier@example.org", password="secret", **kw):
    user = User(email=email, **kw)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def _instance(slug="test", label="Test", chart="asso", active=True):
    import os
    inst = Instance(slug=slug, label=label, chart=chart, is_active=active,
                    database_url=os.environ["DATABASE_URL"])
    db.session.add(inst)
    db.session.commit()
    return inst


def _login(client, email="tresorier@example.org", password="secret"):
    return client.post("/api/v1/session/login", json={"email": email, "password": password})


def test_login_errors(app):
    _user()
    _user(email="old@example.org", is_active=False)
    client = app.test_client()
    resp = _login(client, password="nope")
    assert resp.status_code == 422
    assert resp.get_json()["error"]["message"] == "Email ou mot de passe incorrect."
    resp = _login(client, email="old@example.org")
    assert resp.status_code == 422 and "désactivé" in resp.get_json()["error"]["message"]
    assert client.get("/api/v1/session").status_code == 401


def test_login_selects_single_instance_and_returns_session(app):
    from app.models import InstanceMembership
    user = _user(email="Tresorier@Example.org", full_name="Trésorier")
    inst = _instance(chart="sci")
    db.session.add(InstanceMembership(user_id=user.id, instance_id=inst.id, role="treasurer"))
    db.session.commit()
    client = app.test_client()
    body = _login(client, email=" tresorier@example.org ").get_json()
    assert body["user"]["email"] == "Tresorier@Example.org" and body["user"]["is_admin"] is False
    assert body["instance"] == {"id": inst.id, "slug": "test", "label": "Test", "chart": "sci", "bookkeeping": "double"}
    assert body["instances"] == [{"id": inst.id, "label": "Test"}]
    labels = [m["label"] for m in body["nav"]]
    assert "Tableau de bord" in labels and "Tiers" in labels
    compta = next(m for m in body["nav"] if m["key"] == "compta")
    assert {"key": "entries", "label": "Écritures", "url": "/entries/"} in compta["items"]
    assert body["csrf_token"] and body["preferences"] == {} and body["admin_links"] == []
    assert body["role"] == "treasurer" and body["permissions"] == {"write": True, "instance_admin": False}
    assert client.get("/api/v1/session").get_json()["instance"]["id"] == inst.id
    assert User.query.one().last_login_at is not None


def test_nav_follows_chart_and_admin(app):
    _user(is_admin=True)
    _instance(slug="a", label="Asso", chart="asso")
    _instance(slug="b", label="SCI", chart="sci")
    client = app.test_client()
    body = _login(client).get_json()
    assert body["instance"] is None and body["nav"] == [] and len(body["instances"]) == 2
    assert [l["url"] for l in body["admin_links"]] == ["/users/", "/instances/"]
    asso = next(i for i in body["instances"] if i["label"] == "Asso")
    body = client.post("/api/v1/session/instance", json={"instance_id": asso["id"]}).get_json()
    urls = [i.get("url") for m in body["nav"] for i in m.get("items", [])]
    assert "/configuration/integrations/" in urls and "/entities/members" in urls
    sci = next(i for i in body["instances"] if i["label"] == "SCI")
    body = client.post("/api/v1/session/instance", json={"instance_id": sci["id"]}).get_json()
    urls = [i.get("url") for m in body["nav"] for i in m.get("items", [])]
    assert "/entities/members" not in urls


def test_select_instance_errors(app):
    _user()
    hidden = _instance(active=False)
    client = app.test_client()
    _login(client)
    for payload in ({"instance_id": "x"}, {"instance_id": hidden.id}):
        resp = client.post("/api/v1/session/instance", json=payload)
        assert resp.status_code == 422 and "instance_id" in resp.get_json()["error"]["fields"]


def test_logout(app):
    _user()
    _instance()
    client = app.test_client()
    _login(client)
    body = client.post("/api/v1/session/logout").get_json()
    assert body["user"] is None
    assert client.get("/api/v1/session").status_code == 401


def test_preferences_merge_delete_and_limits(app):
    _user()
    _instance()
    client = app.test_client()
    _login(client)
    patch = lambda data: client.patch("/api/v1/me/preferences", json=data)
    assert patch({"color_scheme": "dark", "tables": {"journals": {"hidden": ["code"]}}}).status_code == 200
    body = patch({"tables": {"purchases": {"hidden": []}}}).get_json()
    assert body["preferences"] == {"color_scheme": "dark",
                                   "tables": {"journals": {"hidden": ["code"]}, "purchases": {"hidden": []}}}
    body = patch({"tables": {"journals": None}}).get_json()
    assert body["preferences"]["tables"] == {"purchases": {"hidden": []}}
    assert json.loads(User.query.one().preferences)["color_scheme"] == "dark"
    assert client.get("/api/v1/session").get_json()["preferences"]["color_scheme"] == "dark"

    resp = patch({"color_scheme": "pink"})
    assert resp.status_code == 422 and "color_scheme" in resp.get_json()["error"]["fields"]
    assert patch({"big": "x" * 20000}).status_code == 413
    assert client.patch("/api/v1/me/preferences", data="[]", content_type="application/json").status_code == 400


def test_job_status(app, login_as):
    client = login_as()
    job = SyncJob(kind="qonto_supplier_invoices", status="done", message="Terminé",
                  progress_done=3, result_json='{"created": 2}')
    db.session.add(job)
    db.session.commit()
    body = client.get(f"/api/v1/jobs/{job.id}").get_json()["job"]
    assert body["status"] == "done" and body["result"] == {"created": 2} and body["progress_done"] == 3
    assert client.get("/api/v1/jobs/999").status_code == 404
