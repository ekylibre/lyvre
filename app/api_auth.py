"""Authentification par clé d'API (lot AK1, claudedocs/design_api_mcp_aiffel.md § 5).

Ordre des hooks (`app/__init__.py`) :
1. `authenticate` (avant le CSRF et le tenant) : `Authorization: Bearer lyv_…` sur `/api/v1/*` et `/mcp` →
   `g.api_key` (KeyContext) et utilisateur de la requête, **sans session** (ni lecture ni cookie) ;
2. CSRF : la protection de Flask-WTF est appelée par `csrf_protect`, sauf pour une requête par clé
   (aucun cookie : pas de requête intersite possible) ;
3. le tenant prend l'instance **de la clé** (`app/tenant.py`) ;
4. `authorize` (blueprint de l'API) : GET seulement, dans les domaines lus de la clé.
"""
from __future__ import annotations

from flask import current_app, g, request
from flask.sessions import SecureCookieSessionInterface

BEARER = "Bearer "
KEY_PATHS = ("/api/v1/", "/mcp")
INVALID_MESSAGE = "Clé d'API invalide, expirée ou révoquée."


def is_key_request() -> bool:
    return getattr(g, "api_key", None) is not None


class KeyAwareSessionInterface(SecureCookieSessionInterface):
    """Pas de cookie de session pour une requête par clé."""

    def should_set_cookie(self, app, session):
        if is_key_request():
            return False
        return super().should_set_cookie(app, session)

    def save_session(self, app, session, response):
        if is_key_request():
            return None
        return super().save_session(app, session, response)


def _bearer() -> str | None:
    header = request.headers.get("Authorization", "")
    if not header.startswith(BEARER):
        return None
    return header[len(BEARER):].strip()


def _unauthorized():
    from app.api import error_response
    response, status = error_response("invalid_api_key", INVALID_MESSAGE, 401)
    response.headers["WWW-Authenticate"] = 'Bearer realm="lyvre"'
    return response, status


def authenticate():
    g.api_key = None
    if not request.path.startswith(KEY_PATHS):
        return None
    token = _bearer()
    if token is None:
        return None
    from app.extensions import login_manager
    from app.services import api_keys
    key = api_keys.verify(token)
    if key is None:
        return _unauthorized()
    g.api_key = api_keys.context(key)
    # Utilisateur de la requête, sans passer par la session (Flask-Login le lit dans g._login_user).
    login_manager._update_request_context_with_user(key.user)
    return None


def csrf_protect():
    """Même contrôle que Flask-WTF (`WTF_CSRF_CHECK_DEFAULT` coupé), sauf pour une requête par clé."""
    app = current_app
    if not app.config.get("WTF_CSRF_ENABLED", True) or is_key_request():
        return None
    if request.method not in app.config["WTF_CSRF_METHODS"] or not request.endpoint:
        return None
    csrf = app.extensions["csrf"]
    if app.blueprints.get(request.blueprint) in csrf._exempt_blueprints:
        return None
    view = app.view_functions.get(request.endpoint)
    if view is not None and f"{view.__module__}.{view.__name__}" in csrf._exempt_views:
        return None
    csrf.protect()
    return None


def authorize():
    """Blueprint de l'API : une clé lit (GET) dans ses domaines ; tout le reste est refusé."""
    if not is_key_request():
        return None
    from app.api import error_response
    from app.services import api_domains
    view = current_app.view_functions.get(request.endpoint) if request.endpoint else None
    domain = api_domains.domain_of(request.endpoint, getattr(view, "__module__", None))
    if domain is None:
        return error_response("forbidden_for_key", "Cette adresse n'est pas ouverte aux clés d'API.", 403)
    if request.method not in ("GET", "HEAD"):
        return error_response("read_only_key", "Une clé d'API lit seulement par l'API REST (GET) ; les saisies "
                              "passent par les outils d'agent.", 403)
    if domain not in g.api_key.reads:
        return error_response("domain_forbidden",
                              f"Domaine « {api_domains.label(domain)} » non accordé à la clé « {g.api_key.name} ».",
                              403, extra={"domain": domain})
    return None


def register(app):
    """À appeler avant `csrf.init_app` : hooks dans le bon ordre, session sans cookie pour une clé."""
    app.session_interface = KeyAwareSessionInterface()
    app.before_request(authenticate)
    app.config["WTF_CSRF_CHECK_DEFAULT"] = False
    app.before_request(csrf_protect)
