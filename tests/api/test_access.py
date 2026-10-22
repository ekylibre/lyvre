"""Accès par instance et rôles (phase A.1) : instances visibles, expert-comptable en lecture
seule sur toute l'API, administration de l'instance, gestion des membres, reprise des accès."""
import os

import pytest

from app.extensions import db
from app.models import Instance, InstanceMembership, User


def _error(resp, status):
    assert resp.status_code == status, (resp.status_code, resp.get_json())
    return resp.get_json()["error"]


def _other_instance(slug="autre", label="Autre"):
    inst = Instance(slug=slug, label=label, database_url=os.environ["DATABASE_URL"])
    db.session.add(inst)
    db.session.commit()
    return inst


def _me():
    return User.query.filter_by(email="user@example.org").one()


# ------------------------------------------------------------------ instances visibles


def test_user_sees_only_his_instances(login_as):
    client = login_as()
    other = _other_instance()
    body = client.get("/api/v1/session").get_json()
    assert [i["label"] for i in body["instances"]] == ["Test"]
    assert body["role"] == "treasurer"
    resp = client.post("/api/v1/session/instance", json={"instance_id": other.id})
    assert _error(resp, 422)["fields"]["instance_id"].startswith("Instance introuvable")


def test_global_admin_sees_all_instances(login_as):
    client = login_as(is_admin=True)
    _other_instance()
    body = client.get("/api/v1/session").get_json()
    assert [i["label"] for i in body["instances"]] == ["Autre", "Test"]
    assert body["role"] == "admin" and body["permissions"]["instance_admin"] is True


def test_revoked_access_takes_effect_immediately(login_as):
    client = login_as()
    assert client.get("/api/v1/journals").status_code == 200
    db.session.query(InstanceMembership).delete()
    db.session.commit()
    assert _error(client.get("/api/v1/journals"), 409)["code"] == "no_instance"
    assert client.get("/journals/").status_code == 302  # page : vers le choix d'instance


def test_user_without_access(login_as):
    client = login_as(role=None)
    assert client.get("/api/v1/session").get_json()["instances"] == []
    assert _error(client.get("/api/v1/journals"), 409)["code"] == "no_instance"


# ------------------------------------------------------------------ expert-comptable


def test_accountant_reads_but_cannot_write(login_as):
    client = login_as(role="accountant")
    body = client.get("/api/v1/session").get_json()
    assert body["role"] == "accountant" and body["permissions"] == {"write": False, "instance_admin": False}
    assert client.get("/api/v1/journals").status_code == 200
    assert client.get("/api/v1/entries").status_code == 200
    err = _error(client.post("/api/v1/journals", json={"code": "ZZ", "label": "Test"}), 403)
    assert err["code"] == "read_only" and "lecture seule" in err["message"]
    # Ce qui reste permis : préférences personnelles, notifications, session.
    assert client.patch("/api/v1/me/preferences", json={"color_scheme": "dark"}).status_code == 200
    assert client.post("/api/v1/notifications/read", json={}).status_code == 200


def _sample_url(rule):
    values = {}
    for name, converter in rule._converters.items():
        values[name] = 1 if type(converter).__name__ == "IntegerConverter" else "x"
    return rule.build(values, append_unknown=False)[1]


def test_every_api_write_route_is_refused_to_accountant(app, login_as):
    """Garde-fou : aucune route d'écriture de l'API n'échappe à la lecture seule."""
    from app.api import READ_ONLY_ALLOWED

    client = login_as(role="accountant")
    checked = []
    for rule in app.url_map.iter_rules():
        if not rule.endpoint.startswith("api.") or rule.endpoint in READ_ONLY_ALLOWED:
            continue
        for method in sorted((rule.methods or set()) & {"POST", "PUT", "PATCH", "DELETE"}):
            resp = client.open(_sample_url(rule), method=method, json={})
            assert resp.status_code == 403, (method, rule.rule, resp.status_code)
            checked.append((method, rule.rule))
    assert len(checked) > 80


# ------------------------------------------------------------------ administration de l'instance


def test_instance_admin_features(login_as):
    treasurer = login_as()
    assert treasurer.get("/api/v1/integrations").status_code == 403
    assert treasurer.get("/api/v1/access/members").status_code == 403
    InstanceMembership.query.one().role = "admin"
    db.session.commit()
    assert treasurer.get("/api/v1/integrations").status_code == 200
    assert treasurer.get("/api/v1/session").get_json()["permissions"]["instance_admin"] is True
    nav = treasurer.get("/api/v1/session").get_json()["nav"]
    config = next(m for m in nav if m["key"] == "configuration")
    assert [i["label"] for i in config["items"]] == ["Structure", "Intégrations", "Accès"]


@pytest.fixture()
def admin(login_as):
    client = login_as(role="admin")
    return client


def test_members_list_includes_global_admins(admin):
    boss = User(email="boss@example.org", is_admin=True)
    boss.set_password("x")
    db.session.add(boss)
    db.session.commit()
    body = admin.get("/api/v1/access/members").get_json()
    rows = {m["email"]: m for m in body["items"]}
    assert rows["user@example.org"]["role"] == "admin" and rows["user@example.org"]["is_me"]
    assert rows["boss@example.org"]["global_admin"] is True
    assert [r["value"] for r in body["meta"]["roles"]] == ["admin", "treasurer", "accountant"]


def test_add_existing_or_new_member(admin):
    expert = User(email="expert@cabinet.fr")
    expert.set_password("x")
    db.session.add(expert)
    db.session.commit()
    resp = admin.post("/api/v1/access/members", json={"email": "Expert@Cabinet.fr", "role": "accountant"})
    assert resp.status_code == 201 and "Accès donné" in resp.get_json()["notices"][0]["message"]
    assert _error(admin.post("/api/v1/access/members", json={"email": "expert@cabinet.fr", "role": "accountant"}), 422)

    err = _error(admin.post("/api/v1/access/members", json={"email": "nouveau@asso.fr", "role": "treasurer"}), 422)
    assert "password" in err["fields"]
    resp = admin.post("/api/v1/access/members", json={"email": "nouveau@asso.fr", "role": "treasurer",
                                                     "password": "motdepasse1", "full_name": "Nouveau"})
    assert "Compte créé" in resp.get_json()["notices"][0]["message"]
    new = User.query.filter_by(email="nouveau@asso.fr").one()
    assert new.check_password("motdepasse1") and not new.is_admin
    assert _error(admin.post("/api/v1/access/members", json={"email": "x@y.fr", "role": "chef"}), 422)


def test_change_role_and_last_admin_guard(admin):
    me = _me()
    err = _error(admin.patch(f"/api/v1/access/members/{me.id}", json={"role": "treasurer"}), 409)
    assert "au moins un administrateur" in err["message"]
    _error(admin.delete(f"/api/v1/access/members/{me.id}"), 409)
    admin.post("/api/v1/access/members", json={"email": "deux@asso.fr", "role": "admin", "password": "motdepasse2"})
    other = User.query.filter_by(email="deux@asso.fr").one()
    assert admin.patch(f"/api/v1/access/members/{other.id}", json={"role": "accountant"}).status_code == 200
    assert InstanceMembership.query.filter_by(user_id=other.id).one().role == "accountant"
    assert admin.delete(f"/api/v1/access/members/{other.id}").status_code == 200
    assert InstanceMembership.query.filter_by(user_id=other.id).count() == 0
    _error(admin.delete("/api/v1/access/members/999"), 404)


def test_global_admin_users_screen_sets_memberships(login_as):
    client = login_as(is_admin=True)
    other = _other_instance()
    test = Instance.query.filter_by(slug="test").one()
    resp = client.post("/api/v1/users", json={"email": "membre@asso.fr", "password": "x", "memberships": [
        {"instance_id": test.id, "role": "treasurer"}, {"instance_id": other.id, "role": "accountant"}]})
    item = resp.get_json()["item"]
    assert [(m["instance"], m["role"]) for m in item["memberships"]] == [("Autre", "accountant"), ("Test", "treasurer")]
    client.patch(f"/api/v1/users/{item['id']}", json={"email": "membre@asso.fr", "is_active": True,
                                                       "memberships": [{"instance_id": other.id, "role": "admin"}]})
    rows = InstanceMembership.query.filter_by(user_id=item["id"]).all()
    assert [(r.instance_id, r.role) for r in rows] == [(other.id, "admin")]
    meta = client.get("/api/v1/users").get_json()["meta"]
    assert {i["label"] for i in meta["instances"]} == {"Autre", "Test"} and len(meta["roles"]) == 3


# ------------------------------------------------------------------ reprise


def test_backfill_keeps_everyone_access(app):
    import seed_meta

    admin = User(email="a@x.fr", is_admin=True)
    user = User(email="u@x.fr")
    for u in (admin, user):
        u.set_password("x")
    a, b = Instance(slug="a", label="A", database_url="sqlite://"), Instance(slug="b", label="B", database_url="sqlite://")
    db.session.add_all([admin, user, a, b])
    db.session.commit()
    seed_meta._backfill_memberships()
    db.session.commit()
    rows = {(m.user.email, m.instance.slug): m.role for m in InstanceMembership.query.all()}
    assert rows == {("a@x.fr", "a"): "admin", ("a@x.fr", "b"): "admin",
                    ("u@x.fr", "a"): "treasurer", ("u@x.fr", "b"): "treasurer"}


def test_redirect_to_instance_choice_keeps_relative_next(login_as):
    client = login_as()
    db.session.query(InstanceMembership).delete()
    db.session.commit()
    resp = client.get("/configuration/organization?x=1")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/select-instance?next=/configuration/organization?x%3D1")
