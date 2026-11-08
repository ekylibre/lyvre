"""JSON API used by the React islands (see claudedocs/design_front_reactif.md §6).

Common rules:
- session authentication (Flask-Login) and instance routing (app.tenant) as
  for the HTML pages; an unauthenticated call gets a 401 JSON, never a redirect;
- CSRF required on POST/PUT/DELETE through the ``X-CSRFToken`` header;
- amounts in integer cents, dates as ISO ``YYYY-MM-DD``;
- one error format::

    {"error": {"code": "validation_error", "message": "…", "fields": {"lines[1].account_id": "…"}}}
"""
from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException

API_PREFIX = "/api/"

bp = Blueprint("api", __name__, url_prefix="/api/v1")

# Seules routes accessibles sans être connecté (toutes les autres : 401 JSON).
PUBLIC_ENDPOINTS = {"api.login", "api.logout", "api.password_forgot", "api.password_reset_check",
                    "api.password_reset", "api.app_version"}

# Écritures permises en lecture seule (expert-comptable) : session et préférences personnelles.
READ_ONLY_ALLOWED = {"api.login", "api.logout", "api.select_instance", "api.update_preferences",
                     # Assistant Claude (lot AG9b) : conversations seulement, sans outil de proposition.
                     "api.assistant_conversation_create", "api.assistant_conversation_delete", "api.assistant_ask",
                     "api.assistant_proposal_update",
                     "api.notifications_mark_read", "api.change_password", "api.password_forgot",
                     "api.password_reset_check", "api.password_reset",
                     # Calculettes (lot AG12) : un calcul n'écrit rien.
                     "api.calculators_compute",
                     # Clés d'API (lot AK1) : chacun révoque les siennes.
                     "api.api_keys_revoke",
                     # Outils d'agent par REST (lot AK4) : l'écriture est refusée outil par outil à une clé d'expert-comptable.
                     "api.agent_tools_call"}
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

_HTTP_CODES = {
    400: "bad_request",
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    422: "validation_error",
}

# Messages affichés par les îlots (toasts) : Werkzeug les fournit en anglais.
_HTTP_MESSAGES = {
    400: "Requête invalide.",
    401: "Session expirée ou utilisateur non connecté : reconnectez-vous.",
    403: "Action non autorisée.",
    404: "Ressource introuvable.",
    405: "Méthode non autorisée pour cette adresse.",
    413: "Contenu trop volumineux.",
}


class ApiError(Exception):
    """Error returned to the client as JSON."""

    def __init__(self, code, message, status=400, fields=None, extra=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.fields = fields or {}
        self.extra = extra or {}


def is_api_request() -> bool:
    return request.path.startswith(API_PREFIX)


def error_response(code, message, status, fields=None, extra=None):
    body = {"code": code, "message": message, **(extra or {})}
    if fields:
        body["fields"] = fields
    return jsonify(error=body), status


def get_or_404(model, object_id, message="Ressource introuvable."):
    """Ligne du modèle, ou ApiError 404 (au lieu de la page HTML de Flask)."""
    from app.extensions import db

    obj = db.session.get(model, object_id)
    if obj is None:
        raise ApiError("not_found", message, status=404)
    return obj


def invalid(message, field=None):
    """Erreur de validation 422, rattachée à un champ du formulaire si `field` est donné."""
    return ApiError("validation_error", message, status=422, fields={field: message} if field else None)


def require_integration(service, scope=None):
    """Action qui a besoin d'une intégration (ou d'une partie de son périmètre : `scope`) : 409
    `integration_required` si elle est désactivée ou la partie décochée (l'écran propose de
    l'activer), 409 `conflict` si elle est activée mais non configurée."""
    from app.services import external_config

    enabled = external_config.scope_enabled(service, scope) if scope else external_config.is_enabled(service)
    if not enabled:
        raise ApiError("integration_required", external_config.required_message(service, scope), status=409,
                       extra={"service": service, **({"scope": scope} if scope else {})})
    if not external_config.is_configured(service):
        raise ApiError("conflict", external_config.unavailable_message(service), status=409)


def notice(message, level="success"):
    """Message métier renvoyé avec une action (`notices`, design §5)."""
    return {"level": level, "message": message}


def json_body() -> dict:
    """Request JSON object, or a 400 ApiError."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("bad_request", "Corps JSON (objet) attendu.", status=400)
    return data


@bp.before_request
def _require_login():
    """Connexion exigée sur toute l'API, sauf PUBLIC_ENDPOINTS (aucune route oubliée)."""
    if request.endpoint in PUBLIC_ENDPOINTS or current_app.config.get("LOGIN_DISABLED"):
        return None
    if not current_user.is_authenticated:
        return error_response("unauthenticated", _HTTP_MESSAGES[401], 401)
    return None


@bp.before_request
def _read_only_accountant():
    """L'expert-comptable consulte tout mais ne modifie rien, quelle que soit la route."""
    from app.access import current_role
    from app.models.instance_membership import ROLE_ACCOUNTANT

    if request.method in WRITE_METHODS and request.endpoint not in READ_ONLY_ALLOWED \
            and current_role() == ROLE_ACCOUNTANT:
        return error_response("read_only", "Accès en lecture seule (expert-comptable) : modification impossible.", 403)
    return None


@bp.before_request
def _api_key_scope():
    """Clé d'API (lot AK1) : lecture seulement, dans les domaines de la clé (app/api_auth.py)."""
    from app.api_auth import authorize
    return authorize()


@bp.after_request
def _api_key_journal(response):
    """Clé d'API (lot AK4) : appel inscrit au journal de la clé."""
    from app.api_auth import log_rest_call
    return log_rest_call(response)


def register_api(app):
    app.register_blueprint(bp)

    @app.errorhandler(ApiError)
    def _api_error(e):
        return error_response(e.code, e.message, e.status, e.fields, e.extra)

    from app.services.ledger_errors import LedgerGuardError

    @app.errorhandler(LedgerGuardError)
    def _ledger_guard_error(e):
        # Refus de la garde des écritures (écriture validée…), levé au flush par n'importe quel chemin.
        from app.extensions import db
        db.session.rollback()
        if is_api_request():
            extra = {"first_open_date": e.first_open_date.isoformat()} if e.first_open_date else None
            return error_response(e.code, str(e), 409, extra=extra)
        raise e

    # App-level handlers: unmatched /api/... URLs never reach the blueprint.
    @app.errorhandler(CSRFError)
    def _csrf_error(e):
        if is_api_request():
            return error_response("csrf_error", "Jeton CSRF manquant ou invalide.", 400)
        return e

    @app.errorhandler(HTTPException)
    def _http_error(e):
        if is_api_request():
            # Message explicite d'un abort(code, "…") conservé ; sinon message en français.
            custom = e.description != type(e).description
            message = e.description if custom else _HTTP_MESSAGES.get(e.code, e.description)
            return error_response(_HTTP_CODES.get(e.code, "http_error"), message, e.code)
        return e

    @app.errorhandler(500)
    def _server_error(e):
        if is_api_request():
            return error_response("server_error", "Erreur interne du serveur.", 500)
        return e


# Routes are attached to ``bp`` by these modules (import for side effects).
from . import (  # noqa: E402,F401
    access, activity_report, agent, api_keys, assets, brevo, data_import, associate_expenses, associates, bank_accounts, bank_statements,
    budgets, calculators, cash, cash_forecast, chart, coop_statements, documents, ekylibre, entities, entries, ereporting, fiscal_years,
    impact, imports, lettering,
    instances, integrations, journals, leases, lookups, members, notifications, odoo, organization, payouts,
    products, projects, purchases, receipts, reconciliation, regulatory, reports, rules, sales, search, session,
    share_movements, tax_profiles,
    sirene,
    simple_categories, subscriptions,
    simple_operations, simple_reports,
    task_types, users, agenda, aids, analytic, assistant, checklists, msa, rfa, stock, tax_result, vat_books, vat_returns,
    work_times,
)
