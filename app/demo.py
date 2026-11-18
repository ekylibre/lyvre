"""Mode démonstration (`LYVRE_DEMO=1`, demo.lyvre.org, lot L7 du site).

Une démo publique partage un même compte entre tous les visiteurs, sur des données fabriquées remises à zéro
chaque nuit (`scripts/demo_seed.py`, `docker/entrypoint.sh`). Ce module garantit qu'elle ne peut rien faire
sortir du serveur ni en changer les accès :

- **aucun appel sortant** : `requests` refuse toute adresse hors de `DEMO_ALLOWED_HOSTS` (vide par défaut :
  Qonto, HelloAsso, Brevo, Sirene, Documenso, l'assistant… échouent proprement), et SMTP est coupé (relances,
  mot de passe oublié) ;
- **écritures refusées** (403 `demo`) : instances, utilisateurs, mots de passe, réglages des intégrations, clés
  d'API, paramètres réglementaires, restauration Ekylibre, assistant et agent, serveur MCP ;
- **pièces jointes limitées** à `DEMO_MAX_UPLOAD_MB` (10 Mo).

La session expose `demo` (identifiants affichés à la connexion, bandeau de l'application).
"""
from __future__ import annotations

import os
import re
import smtplib
from urllib.parse import urlsplit

DEFAULT_EMAIL = "demo@lyvre.org"
DEFAULT_PASSWORD = "demo-lyvre"
MESSAGE = "Démonstration : action désactivée (données fictives partagées, remises à zéro chaque nuit)."
NETWORK_MESSAGE = "Démonstration : les services externes sont désactivés."

# Écritures refusées (toute méthode autre que GET, HEAD, OPTIONS).
BLOCKED = [re.compile(p) for p in (
    r"^/api/v1/instances(/|$)",
    r"^/api/v1/users(/|$)",
    r"^/api/v1/me/password$",
    r"^/api/v1/session/password-",
    r"^/api/v1/integrations/[^/]+(/(enabled|check|scopes))?$",
    r"^/api/v1/api-keys(/|$)",
    r"^/api/v1/regulatory-values(/|$)",
    r"^/api/v1/imports/ekylibre(/|$)",
    r"^/api/v1/assistant/",
    r"^/api/v1/agent/",
    r"^/mcp$",
)]
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def enabled() -> bool:
    return os.environ.get("LYVRE_DEMO", "").strip().lower() in ("1", "true", "yes", "on")


def credentials() -> dict:
    return {"email": os.environ.get("DEMO_EMAIL") or DEFAULT_EMAIL,
            "password": os.environ.get("DEMO_PASSWORD") or DEFAULT_PASSWORD}


def session_info() -> dict | None:
    """`demo` de la session : identifiants publics, ou None hors démonstration."""
    from flask import current_app
    return credentials() if current_app.config.get("LYVRE_DEMO") else None


def blocked(method: str, path: str) -> bool:
    return method.upper() not in SAFE_METHODS and any(p.search(path) for p in BLOCKED)


def allowed_hosts() -> set[str]:
    return {h.strip().lower() for h in os.environ.get("DEMO_ALLOWED_HOSTS", "").split(",") if h.strip()}


class DemoNetworkBlocked(Exception):
    pass


def _install_network_block() -> None:
    """Coupe les appels sortants du processus (idempotent)."""
    import requests

    if getattr(requests.Session.send, "_lyvre_demo", False):
        return
    original_send = requests.Session.send

    def send(self, request, **kwargs):
        host = (urlsplit(request.url).hostname or "").lower()
        if host not in allowed_hosts():
            raise requests.ConnectionError(NETWORK_MESSAGE, request=request)
        return original_send(self, request, **kwargs)

    send._lyvre_demo = True
    requests.Session.send = send

    def no_smtp(self, *args, **kwargs):
        raise smtplib.SMTPConnectError(421, NETWORK_MESSAGE)

    smtplib.SMTP.connect = no_smtp


def register(app) -> None:
    """À appeler dans `create_app` : rien hors démonstration."""
    app.config["LYVRE_DEMO"] = enabled()
    if not app.config["LYVRE_DEMO"]:
        return
    app.config["LYVRE_DEMO_CREDENTIALS"] = credentials()  # page de connexion (app/templates/spa.html)
    _install_network_block()
    app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("DEMO_MAX_UPLOAD_MB", "10")) * 1024 * 1024

    @app.before_request
    def _demo_guard():
        from flask import jsonify, request
        if blocked(request.method, request.path):
            return jsonify(error={"code": "demo", "message": MESSAGE}), 403
        return None
