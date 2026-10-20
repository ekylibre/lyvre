"""Statut et test de fonctionnement des intégrations externes.

- `status` / `overview` / `detail` : état affiché (aucun appel réseau).
- `run_check` : exécute la sonde d'un service (un appel léger en lecture,
  borné par `CHECK_TIMEOUT`), traduit l'erreur en message lisible, masque
  les secrets et enregistre le résultat dans `integration_states`.

Une sonde renvoie son message de succès ou lève une exception ; les tests
remplacent les entrées de `PROBES`.
"""
from __future__ import annotations

import json
import smtplib
import time
import xmlrpc.client
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

import requests
from flask import current_app

from app.extensions import db
from app.models import IntegrationState, SyncJob
from app.models.sync_job import (
    SYNC_KIND_METRICS, SYNC_KIND_PAYOUT_PAYMENTS, SYNC_KIND_PAYOUTS,
)
from app.services import external_config

CHECK_TIMEOUT = 10  # secondes, par sonde
MAX_MESSAGE_LENGTH = 500
MASK = "••••"

STATUS_DISABLED = "disabled"
STATUS_UNCONFIGURED = "unconfigured"
STATUS_UNTESTED = "untested"
STATUS_OK = "ok"
STATUS_ERROR = "error"

STATUS_LABELS = {
    STATUS_DISABLED: "Désactivée",
    STATUS_UNCONFIGURED: "À configurer",
    STATUS_UNTESTED: "Non testée",
    STATUS_OK: "Opérationnelle",
    STATUS_ERROR: "En erreur",
}

# Champ à vérifier quand le service répond « introuvable » (HTTP 404).
_NOT_FOUND_HINTS = {
    "stancer": "la clé secrète",
    "odoo": "l'URL et le nom de la base",
    "helloasso": "le slug de l'organisation",
    "ga4": "l'ID de propriété",
    "facebook": "l'ID de la Page",
}

# Synchronisations suivies par service : (types de SyncJob, clé dans result_json, écran).
_SYNC_SOURCES = {
    "stancer": ((SYNC_KIND_PAYOUTS, SYNC_KIND_PAYOUT_PAYMENTS), None, "payouts.index"),
    "ga4": ((SYNC_KIND_METRICS,), "ga4", "impact.index"),
    "facebook": ((SYNC_KIND_METRICS,), "facebook", "impact.index"),
}


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    message: str
    checked_at: datetime
    duration_ms: int


@dataclass(frozen=True)
class SyncInfo:
    status: str  # running | done | failed
    started_at: datetime
    finished_at: datetime | None
    message: str | None
    imported: int | None  # part propre à la source (GA4 / Facebook)
    errors: list[str]
    endpoint: str


@dataclass(frozen=True)
class IntegrationView:
    slug: str
    label: str
    description: str
    status: str
    enabled: bool
    configured: bool
    last_check: CheckResult | None
    check_outdated: bool  # configuration modifiée depuis le dernier test
    last_sync: SyncInfo | None = None
    sync_tracked: bool = False

    @property
    def status_label(self) -> str:
        return STATUS_LABELS[self.status]


# --------------------------------------------------------------------- statut

def _last_check(state: IntegrationState | None) -> CheckResult | None:
    if state is None or state.checked_at is None or state.check_ok is None:
        return None
    return CheckResult(
        ok=bool(state.check_ok),
        message=state.check_message or "",
        checked_at=state.checked_at,
        duration_ms=state.check_duration_ms or 0,
    )


def _view(service: str, state: IntegrationState | None) -> IntegrationView:
    enabled = True if state is None else bool(state.enabled)
    configured = external_config.is_configured(service)
    last_check = _last_check(state)
    outdated = last_check is not None and (
        state.checked_fingerprint != external_config.fingerprint(service)
    )
    if not enabled:
        status = STATUS_DISABLED
    elif not configured:
        status = STATUS_UNCONFIGURED
    elif last_check is None or outdated:
        status = STATUS_UNTESTED
    elif last_check.ok:
        status = STATUS_OK
    else:
        status = STATUS_ERROR
    return IntegrationView(
        slug=service,
        label=external_config.SERVICE_LABELS[service],
        description=external_config.SERVICE_DESCRIPTIONS[service],
        status=status,
        enabled=enabled,
        configured=configured,
        last_check=last_check,
        check_outdated=outdated,
        sync_tracked=service in _SYNC_SOURCES,
    )


def _state(service: str) -> IntegrationState | None:
    return db.session.query(IntegrationState).filter_by(service=service).first()


def status(service: str) -> str:
    return _view(service, _state(service)).status


def overview() -> list[IntegrationView]:
    """Toutes les intégrations, dans l'ordre de déclaration (page index)."""
    states = {s.service: s for s in db.session.query(IntegrationState).all()}
    return [_view(service, states.get(service)) for service in external_config.SERVICE_KEYS]


def detail(service: str) -> IntegrationView:
    if service not in external_config.SERVICE_KEYS:
        raise ValueError(f"Unknown service: {service}")
    view = _view(service, _state(service))
    return IntegrationView(**{**view.__dict__, "last_sync": last_sync(service)})


def last_sync(service: str) -> SyncInfo | None:
    """Dernière synchronisation suivie du service, ou None (non suivie / jamais lancée)."""
    source = _SYNC_SOURCES.get(service)
    if source is None:
        return None
    kinds, result_key, endpoint = source
    job = (
        db.session.query(SyncJob)
        .filter(SyncJob.kind.in_(kinds))
        .order_by(SyncJob.started_at.desc(), SyncJob.id.desc())
        .first()
    )
    if job is None:
        return None
    imported, errors = None, []
    if result_key and job.result_json:
        try:
            part = json.loads(job.result_json).get(result_key) or {}
        except (TypeError, ValueError, AttributeError):
            part = {}
        imported = part.get("imported")
        errors = [str(e) for e in part.get("errors") or []]
    return SyncInfo(
        status=job.status,
        started_at=job.started_at,
        finished_at=job.finished_at,
        message=job.message,
        imported=imported,
        errors=errors,
        endpoint=endpoint,
    )


# --------------------------------------------------------------------- sondes

def _probe_stancer() -> str:
    from app.services import stancer_sync

    stancer_sync._api_get("/payouts", timeout=CHECK_TIMEOUT, limit=1)
    mode = (external_config.get("stancer", "mode") or "live").strip().lower()
    key = external_config.get("stancer", "secret_key") or ""
    message = f"Clé acceptée par Stancer (mode {mode})."
    key_mode = "test" if key.startswith("stest_") else "live" if key.startswith("sprod_") else None
    if key_mode and key_mode != mode:
        message += f" Attention : la clé est une clé {key_mode}, le mode configuré est {mode}."
    return message


def _probe_odoo() -> str:
    from app.services import odoo_client

    client = odoo_client.from_app_config(timeout=CHECK_TIMEOUT)
    version = (client.version() or {}).get("server_version") or "?"
    uid = client.uid
    return f"Connecté à Odoo {version} (utilisateur n° {uid})."


def _probe_helloasso() -> str:
    from app.services import helloasso_client

    client = helloasso_client.from_app_config(timeout=CHECK_TIMEOUT)
    org = client.get_organization() or {}
    return f"Organisation « {org.get('name') or client.org_slug} » accessible."


def _probe_smtp() -> str:
    from app.services import membership_reminders

    settings = membership_reminders.smtp_settings()
    server = membership_reminders._open_smtp(settings, timeout=CHECK_TIMEOUT)
    try:
        server.noop()
    finally:
        server.quit()
    tls = "TLS activé" if settings["use_tls"] else "TLS désactivé"
    auth = ", authentifié" if settings["username"] else ""
    return f"Serveur {settings['host']}:{settings['port']} joignable, {tls}{auth}."


def _probe_ga4() -> str:
    from app.services import ga4_client

    client = ga4_client.from_app_config()
    client.ping(timeout=CHECK_TIMEOUT)
    return f"Propriété {client.property_id} accessible."


def _probe_facebook() -> str:
    from app.services import facebook_client

    client = facebook_client.from_app_config(timeout=CHECK_TIMEOUT)
    return f"Page « {client.fetch_page_name()} » accessible."


PROBES: dict[str, Callable[[], str]] = {
    "stancer": _probe_stancer,
    "odoo": _probe_odoo,
    "helloasso": _probe_helloasso,
    "smtp": _probe_smtp,
    "ga4": _probe_ga4,
    "facebook": _probe_facebook,
}


# ----------------------------------------------------------- erreurs lisibles

def _http_message(service: str, status_code: int, detail: str | None = None) -> str:
    label = external_config.SERVICE_LABELS[service]
    if status_code in (401, 403):
        message = f"Identifiants refusés par {label} (HTTP {status_code})."
    elif status_code == 404:
        hint = _NOT_FOUND_HINTS.get(service, "la configuration")
        message = f"Ressource introuvable chez {label} : vérifiez {hint} (HTTP 404)."
    elif status_code == 429:
        message = f"Trop de requêtes vers {label}, réessayez plus tard (HTTP 429)."
    elif status_code >= 500:
        message = f"{label} rencontre une erreur (HTTP {status_code}), réessayez plus tard."
    else:
        message = f"{label} a répondu HTTP {status_code}."
    return f"{message} Détail : {detail}" if detail else message


def _api_detail(response) -> str | None:
    """Explication renvoyée par l'API dans le corps JSON (Graph, OAuth2, Stancer…)."""
    try:
        body = response.json()
    except Exception:  # noqa: BLE001 — corps absent ou non JSON
        return None
    if not isinstance(body, dict):
        return None
    error = body.get("error")
    if isinstance(error, dict):  # Graph API, Stancer
        detail = error.get("message")
    else:  # OAuth2 : {"error": "...", "error_description": "..."}
        detail = body.get("error_description") or error or body.get("message")
    return _first_line(detail)[:200] if detail else None


def _first_line(text) -> str:
    return (str(text).strip().splitlines() or [""])[0]


def describe_error(service: str, exc: BaseException) -> str:
    """Message en français, compréhensible par un non-technicien."""
    from app.services.facebook_client import FacebookConfigError
    from app.services.ga4_client import GA4ConfigError
    from app.services.helloasso_client import HelloAssoConfigError
    from app.services.odoo_client import OdooConfigError

    name = type(exc).__name__
    timeout_msg = f"Délai dépassé ({CHECK_TIMEOUT} s) : le service ne répond pas."

    response = getattr(exc, "response", None)
    if isinstance(exc, (requests.HTTPError, HelloAssoConfigError)) and response is not None:
        return _http_message(service, response.status_code, _api_detail(response))
    if isinstance(exc, (OdooConfigError, HelloAssoConfigError, GA4ConfigError,
                        FacebookConfigError)):
        return str(exc)
    if isinstance(exc, (requests.Timeout, TimeoutError)) or name == "DeadlineExceeded":
        return timeout_msg
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "Identifiant ou mot de passe SMTP refusé."
    if isinstance(exc, smtplib.SMTPResponseException):
        return f"Le serveur SMTP a refusé la connexion ({exc.smtp_code})."
    if isinstance(exc, xmlrpc.client.Fault):
        return f"Odoo a répondu une erreur : {_first_line(exc.faultString)}"
    if isinstance(exc, xmlrpc.client.ProtocolError):
        return _http_message(service, exc.errcode)
    if name == "RefreshError":  # google.auth : clé du compte de service refusée
        return "Clé du compte de service refusée par Google."
    code = getattr(exc, "code", None)
    if type(exc).__module__.startswith("google.api_core") and isinstance(code, int):
        return _http_message(service, code)
    if isinstance(exc, (requests.ConnectionError, ConnectionError, OSError)):
        return f"Serveur injoignable (adresse ou réseau) : {_first_line(exc)}"
    if isinstance(exc, ImportError):
        return f"Dépendance manquante : {exc.name or exc}."
    return f"Erreur inattendue : {name} — {_first_line(exc)}"


def _secrets(service: str) -> list[str]:
    values = [
        external_config.get(svc, key) or ""
        for svc, key in external_config.SECRET_KEYS
        if svc == service
    ]
    if service == "ga4":
        try:
            info = json.loads(external_config.get("ga4", "credentials_json") or "")
            values += [str(info.get("private_key") or ""), str(info.get("private_key_id") or "")]
        except (TypeError, ValueError, AttributeError):
            pass
    # Les valeurs trop courtes masqueraient du texte ordinaire.
    return sorted({v for v in values if len(v) >= 4}, key=len, reverse=True)


def mask_secrets(service: str, text: str) -> str:
    for secret in _secrets(service):
        text = text.replace(secret, MASK)
    return text


# --------------------------------------------------------------------- test

def run_check(service: str) -> CheckResult:
    """Teste le service et enregistre le résultat (sauf si désactivé ou incomplet)."""
    if service not in PROBES:
        raise ValueError(f"Unknown service: {service}")
    now = datetime.utcnow()
    if not external_config.is_enabled(service):
        return CheckResult(False, "Intégration désactivée.", now, 0)
    if not external_config.is_configured(service):
        missing = [
            key for key in external_config.SERVICE_REQUIRED_KEYS[service]
            if not external_config.get(service, key)
        ]
        return CheckResult(
            False, "Configuration incomplète (manquant : " + ", ".join(missing) + ").", now, 0
        )

    start = time.monotonic()
    try:
        message, ok = PROBES[service](), True
    except Exception as exc:  # noqa: BLE001 — toute erreur devient un message
        message, ok = describe_error(service, exc), False
        current_app.logger.warning(
            "Integration check %s failed: %s", service, mask_secrets(service, repr(exc))
        )
    duration_ms = int((time.monotonic() - start) * 1000)
    message = mask_secrets(service, message)
    if len(message) > MAX_MESSAGE_LENGTH:
        message = message[: MAX_MESSAGE_LENGTH - 1] + "…"

    state = _state(service)
    if state is None:
        state = IntegrationState(service=service, enabled=True)
        db.session.add(state)
    state.checked_at = now
    state.check_ok = ok
    state.check_message = message
    state.check_duration_ms = duration_ms
    state.checked_fingerprint = external_config.fingerprint(service)
    db.session.commit()
    return CheckResult(ok, message, now, duration_ms)
