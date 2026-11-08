"""Clés d'API (lot AK1, claudedocs/design_api_mcp_aiffel.md § 5, récits 1, 5 et 6)."""
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.extensions import db
from app.models import ApiKey, InstanceMembership, User


def _create(client, **body):
    payload = {"name": "Aiffel — saisie terrain", "read_domains": ["purchases", "agenda"], "write_domains": []}
    payload.update(body)
    return client.post("/api/v1/api-keys", json=payload)


def _bearer(app, token, path, method="get", **kw):
    client = app.test_client()   # sans session
    return getattr(client, method)(path, headers={"Authorization": f"Bearer {token}"}, **kw)


@pytest.fixture()
def admin(login_as):
    return login_as(role="admin")


def test_create_shows_token_once(app, admin):
    res = _create(admin)
    assert res.status_code == 201, res.json
    token = res.json["token"]
    assert token.startswith("lyv_") and len(token) > 50
    key = db.session.query(ApiKey).one()
    assert token.split("_", 2)[2] not in key.secret_hash and len(key.secret_hash) == 64
    listing = admin.get("/api/v1/api-keys").json
    assert "token" not in listing["items"][0]
    assert listing["items"][0]["prefix"] == f"lyv_{key.public_id}_…"
    assert listing["items"][0]["read_domains"] == ["purchases", "agenda"]
    assert {d["key"] for d in listing["meta"]["domains"]} >= {"accounting", "purchases"}


def test_key_reads_its_domains_only(app, admin):
    token = _create(admin).json["token"]
    res = _bearer(app, token, "/api/v1/purchases")
    assert res.status_code == 200, res.json
    assert "Set-Cookie" not in res.headers
    denied = _bearer(app, token, "/api/v1/bank-accounts")
    assert denied.status_code == 403 and denied.json["error"]["code"] == "domain_forbidden"
    assert denied.json["error"]["domain"] == "bank"


def test_key_cannot_write_through_rest_nor_reach_admin(app, admin):
    token = _create(admin, read_domains=["accounting"]).json["token"]
    res = _bearer(app, token, "/api/v1/entries", method="post", json={})
    assert res.status_code == 403 and res.json["error"]["code"] == "read_only_key"
    for path in ("/api/v1/api-keys", "/api/v1/access/members", "/api/v1/integrations", "/api/v1/session"):
        assert _bearer(app, token, path).json["error"]["code"] == "forbidden_for_key", path


def test_bad_revoked_expired_keys_get_401(app, admin):
    token = _create(admin).json["token"]
    assert _bearer(app, token + "x", "/api/v1/purchases").status_code == 401
    assert _bearer(app, "lyv_nothing", "/api/v1/purchases").status_code == 401
    key = db.session.query(ApiKey).one()
    key.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.session.commit()
    res = _bearer(app, token, "/api/v1/purchases")
    assert res.status_code == 401 and res.headers["WWW-Authenticate"].startswith("Bearer")
    key.expires_at = datetime.utcnow() + timedelta(days=1)
    db.session.commit()
    assert _bearer(app, token, "/api/v1/purchases").status_code == 200
    assert admin.post(f"/api/v1/api-keys/{key.id}/revoke").status_code == 200
    assert _bearer(app, token, "/api/v1/purchases").status_code == 401


def test_key_stops_when_user_loses_access(app, admin):
    member = User(email="tresorier@example.org")
    member.set_password("x")
    db.session.add(member)
    db.session.flush()
    instance_id = db.session.query(InstanceMembership).first().instance_id
    db.session.add(InstanceMembership(user_id=member.id, instance_id=instance_id, role="treasurer"))
    db.session.commit()
    res = _create(admin, user_id=member.id, write_domains=["purchases"])
    assert res.status_code == 201, res.json
    token = res.json["token"]
    assert _bearer(app, token, "/api/v1/purchases").status_code == 200
    db.session.query(InstanceMembership).filter_by(user_id=member.id).delete()
    db.session.commit()
    assert _bearer(app, token, "/api/v1/purchases").status_code == 401


def test_accountant_key_cannot_write(app, admin):
    accountant = User(email="expert@example.org")
    accountant.set_password("x")
    db.session.add(accountant)
    db.session.flush()
    instance_id = db.session.query(InstanceMembership).first().instance_id
    db.session.add(InstanceMembership(user_id=accountant.id, instance_id=instance_id, role="accountant"))
    db.session.commit()
    res = _create(admin, user_id=accountant.id, write_domains=["purchases"])
    assert res.status_code == 422 and "expert-comptable" in res.json["error"]["message"]
    assert _create(admin, user_id=accountant.id).status_code == 201


def test_domain_rules(app, admin):
    assert _create(admin, read_domains=["agronomy"]).status_code == 422          # pas une exploitation
    assert _create(admin, read_domains=[], write_domains=["bank"]).status_code == 422   # pas d'écriture banque
    res = _create(admin, read_domains=[], write_domains=["purchases"])
    assert res.status_code == 201 and res.json["item"]["read_domains"] == ["purchases"]   # écrire suppose lire
    assert _create(admin, name=" ").status_code == 422
    assert _create(admin, expires_on="2001-01-01").status_code == 422


def test_non_admin_sees_and_revokes_own_keys(app, login_as):
    client = login_as(role="treasurer")
    assert client.get("/api/v1/api-keys").status_code == 403
    user = db.session.query(User).filter_by(email="user@example.org").one()
    key = ApiKey(public_id="abcdefghij", secret_hash="0" * 64, instance_id=db.session.query(InstanceMembership).first().instance_id,
                 user_id=user.id, name="Mienne", expires_at=datetime.utcnow() + timedelta(days=3))
    db.session.add(key)
    db.session.commit()
    assert [k["name"] for k in client.get("/api/v1/me/api-keys").json["items"]] == ["Mienne"]
    assert client.post(f"/api/v1/api-keys/{key.id}/revoke").json["item"]["state"] == "revoked"


def test_csrf_still_protects_session_requests(app, admin):
    app.config["WTF_CSRF_ENABLED"] = True
    res = admin.post("/api/v1/api-keys", json={"name": "x", "read_domains": ["purchases"]})
    assert res.status_code == 400 and res.json["error"]["code"] == "csrf_error"


def test_every_api_module_is_classified():
    from app.services import api_domains
    modules = {p.stem for p in (Path(__file__).resolve().parents[2] / "app" / "api").glob("*.py")} - {"__init__"}
    missing = modules - set(api_domains.MODULE_DOMAINS)
    assert not missing, f"Modules de l'API sans domaine (app/services/api_domains.py) : {sorted(missing)}"
    assert set(api_domains.MODULE_DOMAINS.values()) - {None} <= set(api_domains.DOMAINS)
