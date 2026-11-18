"""Mode démonstration (LYVRE_DEMO, app/demo.py) : écritures sensibles refusées, aucun appel sortant ni e-mail,
identifiants exposés à la connexion ; seed sans effet quand la démo existe déjà (scripts/demo_seed.py)."""
import smtplib

import pytest
import requests

from app import demo
from app.extensions import db
from app.models import Instance, User


@pytest.fixture(autouse=True)
def app_env(monkeypatch):
    """Avant l'application (tests/conftest.py) ; les fonctions remplacées sont rendues à la fin du test."""
    monkeypatch.setenv("LYVRE_DEMO", "1")
    monkeypatch.delenv("DEMO_ALLOWED_HOSTS", raising=False)
    monkeypatch.setattr(requests.Session, "send", requests.Session.send)
    monkeypatch.setattr(smtplib.SMTP, "connect", smtplib.SMTP.connect)


def _refused(resp):
    assert resp.status_code == 403, (resp.status_code, resp.get_json())
    assert resp.get_json()["error"]["code"] == "demo"


@pytest.mark.parametrize("method, path, expected", [
    ("POST", "/api/v1/instances", True),
    ("DELETE", "/api/v1/instances/3", True),
    ("POST", "/api/v1/users", True),
    ("POST", "/api/v1/me/password", True),
    ("POST", "/api/v1/session/password-forgot", True),
    ("PUT", "/api/v1/integrations/qonto", True),
    ("POST", "/api/v1/integrations/smtp/check", True),
    ("POST", "/api/v1/integrations/qonto/dismiss", False),
    ("POST", "/api/v1/api-keys", True),
    ("POST", "/api/v1/imports/ekylibre/upload", True),
    ("POST", "/api/v1/imports/ofx", False),
    ("POST", "/api/v1/assistant/conversations", True),
    ("POST", "/mcp", True),
    ("GET", "/api/v1/instances", False),
    ("POST", "/api/v1/sales", False),
    ("POST", "/api/v1/session/login", False),
])
def test_blocked_paths(method, path, expected):
    assert demo.blocked(method, path) is expected


def test_instance_creation_and_password_refused(app, login_as):
    client = login_as(is_admin=True)
    _refused(client.post("/api/v1/instances", json={"slug": "pirate", "label": "Pirate"}))
    _refused(client.post("/api/v1/me/password", json={"current_password": "x", "new_password": "y" * 12}))
    _refused(client.put("/api/v1/integrations/smtp", json={"host": "smtp.example.org"}))
    assert db.session.query(Instance).filter_by(slug="pirate").first() is None
    assert client.post("/api/v1/integrations/qonto/dismiss").status_code != 403


def test_password_forgot_refused_without_login(app):
    _refused(app.test_client().post("/api/v1/session/password-forgot", json={"email": "demo@lyvre.org"}))


def test_no_outgoing_call_nor_email(app):
    with pytest.raises(requests.ConnectionError, match="Démonstration"):
        requests.get("https://thirdparty.qonto.com/v2/organization", timeout=1)
    with pytest.raises(smtplib.SMTPConnectError):
        smtplib.SMTP("smtp.example.org", 587, timeout=1)


def test_allowed_host_goes_through(app, monkeypatch):
    monkeypatch.setenv("DEMO_ALLOWED_HOSTS", "data.geopf.fr")
    with pytest.raises(requests.ConnectionError) as info:  # hôte permis : la vraie requête part (adresse injoignable)
        requests.get("http://data.geopf.fr:1/", timeout=0.5)
    assert "Démonstration" not in str(info.value)


def test_credentials_on_login_page_and_session(app, login_as, monkeypatch):
    page = app.test_client().get("/login").get_data(as_text=True)
    assert 'name="lyvre-demo" data-email="demo@lyvre.org" data-password="demo-lyvre"' in page
    body = login_as().get("/api/v1/session").get_json()
    assert body["demo"] == {"email": "demo@lyvre.org", "password": "demo-lyvre"}


def test_seed_skipped_when_demo_account_exists(app):
    from scripts import demo_seed

    user = User(email="demo@lyvre.org", is_admin=False)
    user.set_password("demo-lyvre")
    db.session.add(user)
    db.session.commit()
    before = db.session.query(Instance).count()
    assert demo_seed.main() == 0
    assert db.session.query(Instance).count() == before


def test_outside_demo_nothing_changes(monkeypatch):
    monkeypatch.setenv("LYVRE_DEMO", "0")
    from app import create_app
    other = create_app("development")
    assert other.config["LYVRE_DEMO"] is False
    assert "lyvre-demo" not in other.test_client().get("/login").get_data(as_text=True)
