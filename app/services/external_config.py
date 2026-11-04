"""Per-instance credentials and switches for external services.

Settings come from the `external_connections` table (tenant DB). The Flask
app config (populated from .env) is a fallback in development only
(`INTEGRATIONS_ENV_FALLBACK`): elsewhere the instance's own settings are
authoritative.

The on/off switch lives on the instance in the meta DB
(`Instance.integrations`), so menus and the session read it without opening
the tenant DB. An integration exists only for some structures
(`SERVICE_CHARTS`, from `Instance.chart`); one that does not apply is off.
"""

from __future__ import annotations

import hashlib
import json

from flask import current_app, g, has_app_context

from app.extensions import db
from app.models import ExternalConnection, IntegrationState
from app.tenant import current_instance


SERVICE_KEYS: dict[str, list[str]] = {
    "stancer":   ["secret_key", "mode"],
    "odoo":      ["url", "db", "username", "api_key"],
    "helloasso": ["client_id", "client_secret", "org_slug", "api_base"],
    "smtp":      ["host", "port", "use_tls", "username", "password", "sender"],
    "ga4":       ["property_id", "credentials_json"],
    "facebook":  ["page_id", "page_token", "app_id", "app_secret"],
    "qonto":     ["login", "secret_key", "staging_token"],
    "documenso": ["url", "api_key"],
    "brevo":     ["api_key", "list_id"],
}

SERVICE_LABELS: dict[str, str] = {
    "stancer":   "Stancer",
    "odoo":      "Odoo",
    "helloasso": "HelloAsso",
    "smtp":      "SMTP (emails)",
    "ga4":       "Google Analytics (GA4)",
    "facebook":  "Facebook (Page)",
    "qonto":     "Qonto",
    "documenso": "Documenso",
    "brevo":     "Brevo",
}

# Usage de chaque intégration dans l'application (page index des intégrations).
SERVICE_DESCRIPTIONS: dict[str, str] = {
    "stancer":   "Versements et paiements par carte, rapprochés des relevés bancaires",
    "odoo":      "Commandes, factures clients et mise à jour des partenaires",
    "helloasso": "Adhésions et formulaires des adhérents",
    "smtp":      "Envoi des relances d'adhésion et des reçus fiscaux par email",
    "ga4":       "Fréquentation du site pour Visibilité & Impact",
    "facebook":  "Abonnés de la Page pour Visibilité & Impact",
    "qonto":     "Comptes, transactions bancaires et factures d'achat",
    "documenso": "Signature électronique des baux",
    "brevo":     "Liste de contacts des adhérents (synchronisée depuis Lyvre)",
}

# Structures (Instance.chart) pour lesquelles l'intégration existe ; absente = toutes.
SERVICE_CHARTS: dict[str, set[str]] = {
    "helloasso": {"asso"},
    "ga4":       {"asso"},
    "facebook":  {"asso"},
    "brevo":     {"asso"},
}

# Périmètre d'une intégration (cases de sa fiche) ; défaut quand rien n'est enregistré.
SCOPES: dict[str, dict[str, str]] = {
    "qonto": {"transactions": "Relevés de compte", "purchases": "Achats", "sales": "Ventes"},
}
DEFAULT_SCOPES: dict[str, set[str]] = {"qonto": {"transactions", "purchases"}}

# Intégrations dont l'activation est proposée, par structure.
RECOMMENDED: dict[str, list[str]] = {
    "sci":  ["qonto"],
    "societe": ["qonto"],
    "agri": ["qonto"],
    "asso": ["helloasso"],
}

# Secrets : jamais réaffichés dans l'interface ni dans les messages de test.
SECRET_KEYS: set[tuple[str, str]] = {
    ("stancer",   "secret_key"),
    ("odoo",      "api_key"),
    ("helloasso", "client_secret"),
    ("smtp",      "password"),
    ("ga4",       "credentials_json"),
    ("facebook",  "page_token"),
    ("facebook",  "app_secret"),
    ("qonto",     "secret_key"),
    ("qonto",     "staging_token"),
    ("documenso", "api_key"),
    ("brevo",     "api_key"),
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
    "qonto":     ["login", "secret_key"],
    "documenso": ["url", "api_key"],
    "brevo":     ["api_key", "list_id"],
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
    ("qonto",     "login"):           "QONTO_LOGIN",
    ("qonto",     "secret_key"):      "QONTO_SECRET_KEY",
    ("qonto",     "staging_token"):   "QONTO_STAGING_TOKEN",
    ("brevo",     "api_key"):         "BREVO_API_KEY",
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
    elif env_fallback():
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
    """True if every required key for this service has a value (DB, or .env in development)."""
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
    if env_fallback() and env_name and current_app.config.get(env_name):
        return "env"
    return "none"


def env_fallback() -> bool:
    """Réglages repris du .env (développement seulement)."""
    return has_app_context() and bool(current_app.config.get("INTEGRATIONS_ENV_FALLBACK"))


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


def _state(service: str) -> IntegrationState | None:
    return db.session.query(IntegrationState).filter_by(service=service).first()


def applies(service: str, chart: str | None = None) -> bool:
    """L'intégration existe pour cette structure (par défaut celle de l'instance courante)."""
    if service not in SERVICE_KEYS:
        return False
    if chart is None:
        chart = getattr(current_instance(), "chart", None) or "asso"
    charts = SERVICE_CHARTS.get(service)
    return charts is None or chart in charts


def applicable(chart: str | None = None) -> list[str]:
    """Intégrations de la structure, dans l'ordre de déclaration."""
    return [s for s in SERVICE_KEYS if applies(s, chart)]


def recommended(chart: str | None = None) -> list[str]:
    if chart is None:
        chart = getattr(current_instance(), "chart", None) or "asso"
    return [s for s in RECOMMENDED.get(chart, []) if applies(s, chart)]


def is_enabled(service: str) -> bool:
    """Interrupteur de l'instance courante ; une intégration non applicable est éteinte.

    Hors instance (aucune en contexte : tests unitaires des clients d'API), pas d'interrupteur.
    En production, requêtes et tâches en arrière-plan ont toujours leur instance.
    """
    inst = current_instance()
    if inst is None:
        return service in SERVICE_KEYS
    return applies(service, inst.chart) and service in inst.enabled_integrations()


def _instance_or_fail():
    inst = current_instance()
    if inst is None:
        raise RuntimeError("Aucune instance en contexte.")
    return inst


def set_enabled(service: str, enabled: bool) -> None:
    if service not in SERVICE_KEYS:
        raise ValueError(f"Unknown service: {service}")
    inst = _instance_or_fail()
    if enabled and not applies(service, inst.chart):
        raise ValueError(f"Service not available for this structure: {service}")
    inst.set_integration(service, enabled)
    db.session.commit()


def scopes(service: str, inst=None) -> set[str]:
    """Périmètre de l'intégration pour l'instance (défaut si rien n'est enregistré)."""
    inst = inst if inst is not None else current_instance()
    saved = inst.integration_scopes(service) if inst is not None else None
    return saved if saved is not None else set(DEFAULT_SCOPES.get(service, set()))


def scope_enabled(service: str, scope: str) -> bool:
    """Intégration activée et partie cochée (ex. Qonto › Ventes)."""
    return is_enabled(service) and scope in scopes(service)


def set_scopes(service: str, values) -> None:
    allowed = SCOPES.get(service)
    if not allowed:
        raise ValueError(f"No scopes for service: {service}")
    unknown = set(values) - set(allowed)
    if unknown:
        raise ValueError(f"Unknown scopes: {sorted(unknown)}")
    _instance_or_fail().set_integration_scopes(service, values)
    db.session.commit()


def dismiss(service: str) -> None:
    """« Ne plus proposer » : l'intégration recommandée sort de l'encart du tableau de bord."""
    inst = _instance_or_fail()
    inst.dismiss_integration(service)
    db.session.commit()


def proposals(inst) -> list[str]:
    """Recommandées pour la structure, ni activées ni écartées."""
    if inst is None or inst.integrations is None:
        return []
    done = inst.enabled_integrations() | inst.dismissed_integrations()
    return [s for s in recommended(inst.chart) if s not in done]


def configured_in_db(service: str) -> bool:
    """Réglages requis enregistrés dans la base de l'instance (jamais le .env)."""
    rows = {r.key for r in db.session.query(ExternalConnection).filter_by(service=service).all() if r.value}
    return all(k in rows for k in SERVICE_REQUIRED_KEYS[service])


def ensure_initialized(inst) -> None:
    """Première ouverture d'une instance existante : active les intégrations applicables
    paramétrées dans sa base et non désactivées (ancien interrupteur de la base de l'instance).
    Les autres restent désactivées ; une seule fois par instance."""
    if inst is None or inst.integrations is not None:
        return
    enabled = []
    for service in applicable(inst.chart):
        state = _state(service)
        if configured_in_db(service) and (state is None or state.enabled):
            enabled.append(service)
    inst._set_integrations(enabled, [])
    db.session.commit()


def scope_available(service: str, scope: str) -> bool:
    return scope_enabled(service, scope) and is_configured(service)


def is_available(service: str) -> bool:
    """True if the integration can be used: switched on and fully configured."""
    return is_enabled(service) and is_configured(service)


def unavailable_reason(service: str) -> str | None:
    """None if usable, else "disabled" or "unconfigured" (the switch wins)."""
    if not is_enabled(service):
        return "disabled"
    if not is_configured(service):
        return "unconfigured"
    return None


def state(service: str, scope: str | None = None) -> dict:
    """État d'une intégration pour les écrans : activée (sinon rien ne s'affiche), disponible
    (activée et configurée), message si elle est activée mais indisponible. `scope` : partie du
    périmètre (Qonto › Achats…) ; décochée, l'intégration est vue comme désactivée."""
    enabled = scope_enabled(service, scope) if scope else is_enabled(service)
    return {"enabled": enabled, "available": is_available(service),
            "message": unavailable_message(service) if enabled else None}


def required_message(service: str, scope: str | None = None) -> str:
    """Action courante qui a besoin d'une intégration désactivée (ou d'une partie décochée)."""
    if scope and is_enabled(service):
        return (f"Cette action nécessite la partie « {SCOPES[service][scope]} » de l'intégration "
                f"{SERVICE_LABELS[service]}, non cochée (Configuration › Intégrations).")
    return f"Cette action nécessite l'intégration {SERVICE_LABELS[service]}, désactivée."


def unavailable_message(service: str) -> str | None:
    """French message for screens and errors when the integration cannot be used."""
    reason = unavailable_reason(service)
    if reason is None:
        return None
    state = "désactivée" if reason == "disabled" else "non configurée"
    return f"Intégration {SERVICE_LABELS[service]} {state} (Configuration › Intégrations)."


def fingerprint(service: str) -> str:
    """SHA-256 of the effective configuration (DB, else .env), keys sorted.

    Used to tell whether the last check still applies; never displayed.
    """
    payload = json.dumps(get_all(service), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
