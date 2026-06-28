"""Per-instance credentials for external services.

Reads from the `external_connections` table (tenant DB) first; falls back
to the Flask app config (which is populated from .env). This keeps existing
deployments working while letting admins migrate progressively to the UI.
"""

from __future__ import annotations

from flask import current_app, g, has_app_context

from app.extensions import db
from app.models import ExternalConnection


SERVICE_KEYS: dict[str, list[str]] = {
    "stancer":   ["secret_key", "mode"],
    "odoo":      ["url", "db", "username", "api_key"],
    "helloasso": ["client_id", "client_secret", "org_slug", "api_base"],
    "smtp":      ["host", "port", "use_tls", "username", "password", "sender"],
    "ga4":       ["property_id", "credentials_json"],
    "facebook":  ["page_id", "page_token", "app_id", "app_secret"],
}

SERVICE_LABELS: dict[str, str] = {
    "stancer":   "Stancer",
    "odoo":      "Odoo",
    "helloasso": "HelloAsso",
    "smtp":      "SMTP (relance email)",
    "ga4":       "Google Analytics (GA4)",
    "facebook":  "Facebook (Page)",
}

# Champs à rendre en <textarea> (valeurs longues / secrets multilignes).
SERVICE_TEXTAREA_KEYS: set[tuple[str, str]] = {
    ("ga4", "credentials_json"),
}

# Keys required for a service to be considered "configured" (a subset of SERVICE_KEYS).
SERVICE_REQUIRED_KEYS: dict[str, list[str]] = {
    "stancer":   ["secret_key"],
    "odoo":      ["url", "db", "username", "api_key"],
    "helloasso": ["client_id", "client_secret", "org_slug"],
    "smtp":      ["host", "sender"],
    "ga4":       ["property_id", "credentials_json"],
    "facebook":  ["page_id", "page_token"],
}

ENV_FALLBACK: dict[tuple[str, str], str] = {
    ("stancer",   "secret_key"):   "STANCER_SECRET_KEY",
    ("stancer",   "mode"):         "STANCER_MODE",
    ("odoo",      "url"):          "ODOO_URL",
    ("odoo",      "db"):           "ODOO_DB",
    ("odoo",      "username"):     "ODOO_USERNAME",
    ("odoo",      "api_key"):      "ODOO_API_KEY",
    ("helloasso", "client_id"):    "HELLOASSO_CLIENT_ID",
    ("helloasso", "client_secret"): "HELLOASSO_CLIENT_SECRET",
    ("helloasso", "org_slug"):     "HELLOASSO_ORG_SLUG",
    ("helloasso", "api_base"):     "HELLOASSO_API_BASE",
    ("smtp",      "host"):         "MAIL_SERVER",
    ("smtp",      "port"):         "MAIL_PORT",
    ("smtp",      "use_tls"):      "MAIL_USE_TLS",
    ("smtp",      "username"):     "MAIL_USERNAME",
    ("smtp",      "password"):     "MAIL_PASSWORD",
    ("smtp",      "sender"):       "MAIL_DEFAULT_SENDER",
    ("ga4",       "property_id"):     "GA4_PROPERTY_ID",
    ("ga4",       "credentials_json"): "GA4_CREDENTIALS_JSON",
    ("facebook",  "page_id"):         "FACEBOOK_PAGE_ID",
    ("facebook",  "page_token"):      "FACEBOOK_PAGE_TOKEN",
    ("facebook",  "app_id"):          "FACEBOOK_APP_ID",
    ("facebook",  "app_secret"):      "FACEBOOK_APP_SECRET",
}


def _cache() -> dict:
    if not has_app_context():
        return {}
    cache = getattr(g, "_ext_config_cache", None)
    if cache is None:
        cache = g._ext_config_cache = {}
    return cache


def get(service: str, key: str) -> str | None:
    """Return the configured value, or fall back to .env, or None."""
    cache = _cache()
    cache_key = (service, key)
    if cache_key in cache:
        return cache[cache_key]

    value = None
    row = (
        db.session.query(ExternalConnection)
        .filter_by(service=service, key=key)
        .first()
    )
    if row is not None and row.value:
        value = row.value
    else:
        env_name = ENV_FALLBACK.get(cache_key)
        if env_name:
            cfg_value = current_app.config.get(env_name)
            if cfg_value:
                value = cfg_value

    cache[cache_key] = value
    return value


def get_all(service: str) -> dict[str, str | None]:
    return {k: get(service, k) for k in SERVICE_KEYS[service]}


def is_configured(service: str) -> bool:
    """True if every required key for this service has a value (DB or .env)."""
    return all(get(service, k) for k in SERVICE_REQUIRED_KEYS[service])


def source(service: str, key: str) -> str:
    """Return 'db', 'env', or 'none' for diagnostics in the UI."""
    row = (
        db.session.query(ExternalConnection)
        .filter_by(service=service, key=key)
        .first()
    )
    if row is not None and row.value:
        return "db"
    env_name = ENV_FALLBACK.get((service, key))
    if env_name and current_app.config.get(env_name):
        return "env"
    return "none"


def set_many(service: str, values: dict[str, str | None]) -> None:
    """Upsert values for one service. Empty value → row removed."""
    if service not in SERVICE_KEYS:
        raise ValueError(f"Unknown service: {service}")
    for key in SERVICE_KEYS[service]:
        new_val = (values.get(key) or "").strip() or None
        row = (
            db.session.query(ExternalConnection)
            .filter_by(service=service, key=key)
            .first()
        )
        if new_val is None:
            if row is not None:
                db.session.delete(row)
        else:
            if row is None:
                db.session.add(
                    ExternalConnection(service=service, key=key, value=new_val)
                )
            else:
                row.value = new_val
    db.session.commit()
    # Invalidate per-request cache for this service.
    cache = _cache()
    for k in list(cache.keys()):
        if k[0] == service:
            cache.pop(k, None)
