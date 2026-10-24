"""Mot de passe oublié : lien de réinitialisation envoyé par e-mail (méta-base, avant le choix de
l'instance).

- Jeton signé (`SECRET_KEY`, itsdangerous) contenant l'utilisateur et une empreinte de son mot de passe
  actuel : valable `MAX_AGE` (1 heure) et **une seule fois** (le mot de passe changé, l'empreinte ne
  correspond plus) ; rien n'est stocké.
- La demande répond toujours la même chose, que le compte existe ou non (pas de découverte des
  adresses) ; un e-mail au plus toutes les 5 minutes par compte.
- Lien construit sur `APP_BASE_URL` (adresse publique de Lyvre) — jamais sur l'en-tête `Host` de la
  requête, qu'un tiers pourrait falsifier — sauf en développement.
- Envoi par le SMTP du serveur (`MAIL_*`), le même pour toutes les instances ; les tests remplacent
  `deliver`.
"""
from __future__ import annotations

import hashlib
import smtplib
import time
from email.message import EmailMessage

from flask import current_app, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import func

from app.extensions import db
from app.models import User
from app.services.instance_access import MIN_PASSWORD

MAX_AGE = 3600
THROTTLE_SECONDS = 300
SALT = "password-reset"
SUBJECT = "Lyvre — réinitialisation de votre mot de passe"

_last_sent: dict[int, float] = {}


class ResetError(ValueError):
    def __init__(self, message, field=None):
        super().__init__(message)
        self.message, self.field = message, field


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=SALT)


def _fingerprint(user: User) -> str:
    return hashlib.sha256((user.password_hash or "").encode()).hexdigest()[:16]


def make_token(user: User) -> str:
    return _serializer().dumps({"u": user.id, "h": _fingerprint(user)})


def user_for(token: str) -> User | None:
    """Compte actif du jeton, s'il est valide, non expiré et pas déjà utilisé."""
    try:
        data = _serializer().loads(token or "", max_age=MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    user = db.session.get(User, data.get("u")) if isinstance(data, dict) else None
    if user is None or not user.is_active or data.get("h") != _fingerprint(user):
        return None
    return user


def base_url() -> str | None:
    configured = (current_app.config.get("APP_BASE_URL") or "").rstrip("/")
    if configured:
        return configured
    return request.host_url.rstrip("/") if current_app.config.get("DEBUG") or current_app.testing else None


def deliver(to: str, subject: str, text: str) -> None:
    """Envoi par le SMTP du serveur (MAIL_*) ; remplacé dans les tests."""
    config = current_app.config
    if not config.get("MAIL_SERVER") or not config.get("MAIL_DEFAULT_SENDER"):
        raise RuntimeError("SMTP du serveur non configuré (MAIL_SERVER, MAIL_DEFAULT_SENDER).")
    message = EmailMessage()
    message["Subject"], message["From"], message["To"] = subject, config["MAIL_DEFAULT_SENDER"], to
    message.set_content(text)
    smtp_class = smtplib.SMTP_SSL if config.get("MAIL_USE_SSL") else smtplib.SMTP
    with smtp_class(config["MAIL_SERVER"], config.get("MAIL_PORT", 587), timeout=15) as server:
        if config.get("MAIL_USE_TLS") and not config.get("MAIL_USE_SSL"):
            server.starttls()
        if config.get("MAIL_USERNAME"):
            server.login(config["MAIL_USERNAME"], config.get("MAIL_PASSWORD", ""))
        server.send_message(message)


def request_reset(email: str) -> None:
    """Envoie le lien si l'adresse est celle d'un compte actif ; ne dit jamais si c'est le cas. Une
    panne d'envoi est journalisée, pas montrée (même réponse pour tous)."""
    email = (email or "").strip().lower()
    user = db.session.query(User).filter(func.lower(User.email) == email).first() if email else None
    if user is None or not user.is_active:
        return
    now = time.monotonic()
    if now - _last_sent.get(user.id, -THROTTLE_SECONDS) < THROTTLE_SECONDS:
        return
    url = base_url()
    if url is None:
        current_app.logger.error("Mot de passe oublié : APP_BASE_URL non configurée, lien non envoyé.")
        return
    link = f"{url}/password/reset?token={make_token(user)}"
    text = (f"Bonjour,\n\nUne réinitialisation du mot de passe de votre compte Lyvre ({user.email}) a été "
            f"demandée. Pour choisir un nouveau mot de passe, ouvrez ce lien (valable une heure, une seule "
            f"fois) :\n\n{link}\n\nSi vous n'êtes pas à l'origine de cette demande, ignorez ce message : "
            f"votre mot de passe actuel reste valable.\n")
    try:
        deliver(user.email, SUBJECT, text)
    except Exception:  # noqa: BLE001 — même réponse pour tous ; la panne est journalisée
        current_app.logger.exception("Mot de passe oublié : envoi de l'e-mail impossible.")
        return
    _last_sent[user.id] = now


def reset(token: str, password: str) -> User:
    user = user_for(token)
    if user is None:
        raise ResetError("Lien invalide, expiré ou déjà utilisé : demandez un nouveau lien.", "token")
    if len(password or "") < MIN_PASSWORD:
        raise ResetError(f"{MIN_PASSWORD} caractères au moins.", "password")
    user.set_password(password)
    user.must_change_password = False
    db.session.commit()
    _last_sent.pop(user.id, None)
    return user
