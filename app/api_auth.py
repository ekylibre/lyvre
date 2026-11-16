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
    """Requête authentifiée par clé : clé vérifiée **et** en-tête Bearer sur cette requête (le contexte `g` peut être
    partagé entre requêtes en test)."""
    from flask import has_request_context
    return has_request_context() and getattr(g, "api_key", None) is not None and _bearer() is not None


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
    # Utilisateur mis en cache par Flask-Login : jamais repris d'une requête précédente (contexte d'application
    # partagé, en test) — une requête sans clé relit la session.
    g.pop("_login_user", None)
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
    if getattr(view, "__module__", None) == "app.api.agent":
        return None       # outils d'agent : domaine contrôlé par outil (app/services/agent_tools.py)
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


def enforce_limits():
    """Après le choix de l'instance (lot AK4) : débit de la clé, dernier usage. Au-delà : 429 et `Retry-After`."""
    if not is_key_request():
        return None
    from app.services import api_journal
    key = g.api_key
    api_journal.touch(key.id)
    wait = api_journal.rate_check(key.id, key.rate_per_minute)
    if wait is None:
        return None
    message = (f"Trop de requêtes pour la clé « {key.name} » ({key.rate_per_minute} par minute) : "
               f"réessayez dans {wait} s.")
    channel = "mcp" if request.path.startswith("/mcp") else "rest"
    api_journal.record(key.id, channel, request.endpoint or request.path, status=429, error=message)
    if channel == "mcp":
        from flask import jsonify
        response = jsonify({"jsonrpc": "2.0", "id": None, "error": {"code": -32000, "message": message,
                                                                    "data": {"retry_after": wait}}})
        response.status_code = 429
    else:
        from app.api import error_response
        response, _status = error_response("rate_limited", message, 429, extra={"retry_after": wait})
        response.status_code = 429
    response.headers["Retry-After"] = str(wait)
    return response


def log_rest_call(response):
    """Blueprint de l'API : chaque appel REST par clé est inscrit au journal (les outils d'agent s'inscrivent eux-mêmes,
    les refus de débit aussi)."""
    if not is_key_request() or response.status_code == 429:
        return response
    view = current_app.view_functions.get(request.endpoint) if request.endpoint else None
    module = getattr(view, "__module__", None)
    if module == "app.api.agent" and request.endpoint != "api.agent_files_upload":
        return response
    from app.services import api_domains, api_journal
    domain = api_domains.domain_of(request.endpoint, module)
    error = None
    if response.status_code >= 400 and response.is_json:
        error = ((response.get_json(silent=True) or {}).get("error") or {}).get("message")
    upload = bool(getattr(g, "api_upload", False)) and response.status_code < 400
    api_journal.record(g.api_key.id, "rest", request.endpoint or request.path, domain=domain,
                       access="write" if request.method not in ("GET", "HEAD") else "read",
                       status=response.status_code, error=error,
                       # Dépôt de pièce : compté comme une création (plafond quotidien, revue de sécurité AK4).
                       object_type="file" if upload else None, object_id=0 if upload else None)
    return response


def register_limits(app):
    """À appeler après `register_tenant_hooks` : les limites et le journal ont besoin de la base de l'instance."""
    app.before_request(enforce_limits)


def register(app):
    """À appeler avant `csrf.init_app` : hooks dans le bon ordre, session sans cookie pour une clé."""
    app.session_interface = KeyAwareSessionInterface()
    app.before_request(authenticate)
    app.config["WTF_CSRF_CHECK_DEFAULT"] = False
    app.before_request(csrf_protect)
