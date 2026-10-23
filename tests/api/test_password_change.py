"""Mot de passe à changer (E3, F5) : garde côté serveur, `POST /api/v1/me/password`, session."""
import pytest

from app.extensions import db
from app.models import User


def _error(resp, status):
    assert resp.status_code == status, (resp.status_code, resp.get_json())
    return resp.get_json()["error"]


@pytest.fixture()
def flagged(login_as):
    """Trésorier connecté dont le mot de passe (« x ») est à changer."""
    client = login_as()
    user = User.query.filter_by(email="user@example.org").one()
    user.must_change_password = True
    db.session.commit()
    return client


def test_guard_blocks_api_and_pages(flagged):
    assert _error(flagged.get("/api/v1/journals"), 403)["code"] == "password_change_required"
    assert _error(flagged.post("/api/v1/session/instance", json={"instance_id": 1}), 403)["code"] == \
        "password_change_required"
    resp = flagged.get("/journals/")
    assert resp.status_code == 302 and resp.headers["Location"].startswith("/password?next=")
    assert flagged.get("/exports/budget/tracking.xlsx").status_code == 302  # route Flask hors SPA


def test_guard_lets_session_password_and_logout_through(flagged):
    body = flagged.get("/api/v1/session").get_json()
    assert body["user"]["must_change_password"] is True
    assert 'id="root"' in flagged.get("/password").get_data(as_text=True)
    assert flagged.get("/about").status_code == 200
    assert flagged.post("/api/v1/session/logout").status_code == 200


def test_change_password_validation(flagged):
    err = _error(flagged.post("/api/v1/me/password", json={"current_password": "faux", "new_password": "motdepasse"}), 422)
    assert list(err["fields"]) == ["current_password"]
    err = _error(flagged.post("/api/v1/me/password", json={"current_password": "x", "new_password": "court"}), 422)
    assert list(err["fields"]) == ["new_password"]
    user = User.query.filter_by(email="user@example.org").one()
    user.set_password("ancien-mdp")
    db.session.commit()
    err = _error(flagged.post("/api/v1/me/password", json={"current_password": "ancien-mdp", "new_password": "ancien-mdp"}), 422)
    assert "différent" in err["fields"]["new_password"]


def test_change_password_lifts_the_guard(flagged):
    resp = flagged.post("/api/v1/me/password", json={"current_password": "x", "new_password": "nouveau-mdp"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["user"]["must_change_password"] is False and body["notices"][0]["message"] == "Mot de passe modifié."
    db.session.expire_all()
    user = User.query.filter_by(email="user@example.org").one()
    assert user.check_password("nouveau-mdp") and not user.must_change_password
    assert flagged.get("/api/v1/journals").status_code == 200


def test_unflagged_user_is_not_blocked_and_may_change_password(login_as):
    client = login_as()
    assert client.get("/api/v1/session").get_json()["user"]["must_change_password"] is False
    assert client.get("/api/v1/journals").status_code == 200
    assert client.post("/api/v1/me/password", json={"current_password": "x", "new_password": "nouveau-mdp"}).status_code == 200


def test_accountant_may_change_password(login_as):
    client = login_as(role="accountant")
    assert client.post("/api/v1/me/password", json={"current_password": "x", "new_password": "nouveau-mdp"}).status_code == 200


def test_new_member_must_change_password_at_first_login(app, login_as):
    """US6 : compte créé depuis la page Accès, première connexion, changement imposé."""
    admin = login_as(role="admin")
    admin.post("/api/v1/access/members", json={"email": "paul@asso.fr", "password": "initial-mdp", "role": "treasurer"})
    paul = app.test_client()
    body = paul.post("/api/v1/session/login", json={"email": "paul@asso.fr", "password": "initial-mdp"}).get_json()
    assert body["user"]["must_change_password"] is True and body["instance"]["slug"] == "test"
    assert _error(paul.get("/api/v1/journals"), 403)["code"] == "password_change_required"
    paul.post("/api/v1/me/password", json={"current_password": "initial-mdp", "new_password": "choisi-mdp"})
    assert paul.get("/api/v1/journals").status_code == 200
