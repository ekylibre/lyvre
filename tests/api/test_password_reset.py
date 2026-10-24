"""Mot de passe oublié : lien envoyé seulement à un compte actif (réponse identique sinon), une fois
toutes les 5 minutes, sur l'adresse publique configurée ; jeton valable une heure et une seule fois ;
nouveau mot de passe ; pages publiques. Aucun e-mail réel (envoi remplacé)."""
import re

import pytest

from app.extensions import db
from app.models import User
from app.services import password_reset

API = "/api/v1/session"


@pytest.fixture()
def mailbox(app, monkeypatch):
    sent = []
    monkeypatch.setattr(password_reset, "deliver", lambda to, subject, text: sent.append((to, subject, text)))
    monkeypatch.setattr(password_reset, "_last_sent", {})
    app.config["APP_BASE_URL"] = "https://compta.exemple.org/"
    app.config["WTF_CSRF_ENABLED"] = False
    return sent


@pytest.fixture()
def account(app):
    user = User(email="Gerante@Exemple.org", is_active=True, must_change_password=True)
    user.set_password("ancien-mot-de-passe")
    db.session.add(user)
    db.session.commit()
    return user


def _token(text):
    return re.search(r"/password/reset\?token=(\S+)", text).group(1)


def test_link_sent_once_and_same_answer_for_unknown(app, mailbox, account):
    client = app.test_client()
    unknown = client.post(f"{API}/password-forgot", json={"email": "personne@exemple.org"})
    known = client.post(f"{API}/password-forgot", json={"email": "  gerante@exemple.org "})
    assert unknown.status_code == known.status_code == 200
    assert unknown.get_json() == known.get_json()  # rien ne dit si le compte existe
    assert len(mailbox) == 1
    to, subject, text = mailbox[0]
    assert to == "Gerante@Exemple.org" and "réinitialisation" in subject
    assert "https://compta.exemple.org/password/reset?token=" in text
    client.post(f"{API}/password-forgot", json={"email": "gerante@exemple.org"})
    assert len(mailbox) == 1  # au plus un e-mail toutes les 5 minutes


def test_reset_then_login_and_single_use(app, mailbox, account):
    client = app.test_client()
    client.post(f"{API}/password-forgot", json={"email": "gerante@exemple.org"})
    token = _token(mailbox[0][2])
    assert client.post(f"{API}/password-reset/check", json={"token": token}).get_json() == {
        "valid": True, "email": "Gerante@Exemple.org"}
    short = client.post(f"{API}/password-reset", json={"token": token, "password": "court"})
    assert short.status_code == 422 and short.get_json()["error"]["fields"]["password"]
    assert client.post(f"{API}/password-reset", json={"token": token, "password": "nouveau-mot-de-passe"}).status_code == 200
    user = db.session.get(User, account.id)
    assert user.check_password("nouveau-mot-de-passe") and user.must_change_password is False
    login = client.post(f"{API}/login", json={"email": "gerante@exemple.org", "password": "nouveau-mot-de-passe"})
    assert login.status_code == 200
    # Le lien a servi : il ne vaut plus rien.
    again = client.post(f"{API}/password-reset", json={"token": token, "password": "encore-un-autre"})
    assert again.status_code == 422 and "déjà utilisé" in again.get_json()["error"]["message"]
    assert client.post(f"{API}/password-reset/check", json={"token": token}).get_json()["valid"] is False


def test_expired_forged_and_inactive(app, mailbox, account, monkeypatch):
    client = app.test_client()
    client.post(f"{API}/password-forgot", json={"email": "gerante@exemple.org"})
    token = _token(mailbox[0][2])
    assert client.post(f"{API}/password-reset/check", json={"token": token + "x"}).get_json()["valid"] is False
    monkeypatch.setattr(password_reset, "MAX_AGE", -1)
    assert client.post(f"{API}/password-reset/check", json={"token": token}).get_json()["valid"] is False
    monkeypatch.setattr(password_reset, "MAX_AGE", 3600)
    account.is_active = False
    db.session.commit()
    assert client.post(f"{API}/password-reset/check", json={"token": token}).get_json()["valid"] is False
    monkeypatch.setattr(password_reset, "_last_sent", {})
    client.post(f"{API}/password-forgot", json={"email": "gerante@exemple.org"})
    assert len(mailbox) == 1  # compte désactivé : rien d'envoyé


def test_no_public_address_no_link_outside_development(app, mailbox, account):
    app.config["APP_BASE_URL"] = ""
    app.config["DEBUG"], app.testing = False, False
    try:
        with app.test_request_context("/", headers={"Host": "attaquant.example"}):
            password_reset.request_reset("gerante@exemple.org")
    finally:
        app.testing = True
    assert mailbox == []  # jamais de lien construit sur l'en-tête Host


def test_pages_are_public(app):
    client = app.test_client()
    for url in ("/password/forgot", "/password/reset?token=abc", "/login"):
        assert client.get(url).status_code == 200, url
