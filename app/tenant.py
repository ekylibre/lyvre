"""Per-request tenant routing.

Each Instance points to its own SQLite (or other) database. We cache one
SQLAlchemy Engine per instance id; the `before_request` hook reads the
selected instance from the session and stashes the matching engine on
`g.tenant_engine`. The custom `MultiTenantSession` (see app.extensions)
then routes default-bind queries to this engine.
"""

from flask import current_app, g, redirect, request, session as flask_session, url_for
from flask_login import current_user
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.extensions import db
from app.models import Instance


_ENGINE_CACHE: dict[int, Engine] = {}

# Endpoints that may run without a selected tenant.
_TENANT_FREE_ENDPOINTS = {
    "auth.login",
    "auth.logout",
    "auth.select_instance",
    "static",
    # Session de la SPA (méta-base seulement), cf. app/api/session.py.
    "api.session_info",
    "api.login",
    "api.logout",
    "api.select_instance",
    "api.update_preferences",
    "api.change_password",
    "auth.change_password",
}

# Seules routes ouvertes à un compte dont le mot de passe est à changer (F5.4) : la session,
# le changement de mot de passe et la déconnexion.
PASSWORD_CHANGE_ALLOWED = {
    "api.session_info", "api.login", "api.logout", "api.change_password",
    "auth.login", "auth.logout", "auth.change_password", "about.index", "static",
}


def _resolve_database_url(url: str) -> str:
    """Resolve relative SQLite paths against the Flask instance folder.

    Flask-SQLAlchemy applies the same convention for the primary URI;
    we replicate it here so that an Instance row carrying
    `sqlite:///seconde-nature.db` points to `<instance>/seconde-nature.db`.
    """
    if not url.startswith("sqlite:///"):
        return url
    raw = url[len("sqlite:///"):]
    if raw.startswith("/"):
        return url  # absolute filesystem path
    from pathlib import Path
    abs_path = Path(current_app.instance_path) / raw
    return f"sqlite:///{abs_path}"


def get_tenant_engine(instance: Instance) -> Engine:
    """Return a cached engine for this instance, creating it on first use."""
    cached = _ENGINE_CACHE.get(instance.id)
    if cached is not None:
        return cached
    resolved = _resolve_database_url(instance.database_url)
    engine = create_engine(resolved, future=True)
    _ENGINE_CACHE[instance.id] = engine
    return engine


def clear_engine_cache(instance_id: int | None = None) -> None:
    """Drop one (or all) cached engines. Useful for tests and reconfigs."""
    if instance_id is None:
        for eng in _ENGINE_CACHE.values():
            eng.dispose()
        _ENGINE_CACHE.clear()
    else:
        eng = _ENGINE_CACHE.pop(instance_id, None)
        if eng is not None:
            eng.dispose()


def current_instance() -> Instance | None:
    return getattr(g, "current_instance", None)


def current_chart() -> str:
    """Plan comptable de l'instance courante ("asso" par défaut)."""
    from app.menu_config import DEFAULT_CHART

    return getattr(current_instance(), "chart", None) or DEFAULT_CHART


def _is_tenant_free_endpoint() -> bool:
    if request.endpoint is None:
        return True
    if request.endpoint in _TENANT_FREE_ENDPOINTS:
        return True
    # /users/* and /instances/* admin pages (and their API) run on meta only.
    return request.endpoint.startswith(("users.", "instances.", "api.users_", "api.instances_"))


def _relative_next():
    """Page demandée, en chemin relatif : la SPA ne suit que les chemins de l'application."""
    return request.full_path.rstrip("?")


def register_tenant_hooks(app):
    """Wire up the before_request hook that selects the tenant per request."""

    # Import tardif : l'API (et les services qu'elle charge) importent ce module.
    from app.api import error_response, is_api_request

    @app.before_request
    def _select_tenant():
        g.tenant_engine = None
        g.current_instance = None
        g.instance_role = None

        if not current_user.is_authenticated:
            return None

        # Re-check is_active on every request (cheap, catches admin deactivation).
        if not current_user.is_active:
            from flask_login import logout_user
            logout_user()
            if is_api_request():
                return error_response("unauthenticated", "Compte désactivé.", 401)
            return redirect(url_for("auth.login"))

        if current_user.must_change_password and request.endpoint not in PASSWORD_CHANGE_ALLOWED:
            if is_api_request():
                return error_response("password_change_required",
                                      "Choisissez un nouveau mot de passe pour continuer.", 403)
            return redirect(url_for("auth.change_password", next=_relative_next()))

        if _is_tenant_free_endpoint():
            return None

        instance_id = flask_session.get("instance_id")
        inst = db.session.get(Instance, instance_id) if instance_id is not None else None
        if inst is None or not inst.is_active:
            flask_session.pop("instance_id", None)
            if is_api_request():
                return error_response("no_instance", "Aucune instance sélectionnée.", 409)
            return redirect(url_for("auth.select_instance", next=_relative_next()))

        # Accès vérifié à chaque requête : un retrait d'accès prend effet immédiatement.
        from app.access import role_for
        role = role_for(current_user, inst)
        if role is None:
            flask_session.pop("instance_id", None)
            if is_api_request():
                return error_response("no_instance", "Vous n'avez pas accès à cette instance.", 409)
            return redirect(url_for("auth.select_instance", next=_relative_next()))

        g.current_instance = inst
        g.instance_role = role
        g.tenant_engine = get_tenant_engine(inst)
        return None
