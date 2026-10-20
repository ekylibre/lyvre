"""JSON API used by the React islands (see claudedocs/design_front_reactif.md §6).

Common rules:
- session authentication (Flask-Login) and instance routing (app.tenant) as
  for the HTML pages; an unauthenticated call gets a 401 JSON, never a redirect;
- CSRF required on POST/PUT/DELETE through the ``X-CSRFToken`` header;
- amounts in integer cents, dates as ISO ``YYYY-MM-DD``;
- one error format::

    {"error": {"code": "validation_error", "message": "…", "fields": {"lines[1].account_id": "…"}}}
"""
from flask import Blueprint, g, jsonify, request
from flask_login import current_user, login_required
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException

API_PREFIX = "/api/"

bp = Blueprint("api", __name__, url_prefix="/api/v1")

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


class ApiError(Exception):
    """Error returned to the client as JSON."""

    def __init__(self, code, message, status=400, fields=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.fields = fields or {}


def is_api_request() -> bool:
    return request.path.startswith(API_PREFIX)


def error_response(code, message, status, fields=None):
    body = {"code": code, "message": message}
    if fields:
        body["fields"] = fields
    return jsonify(error=body), status


def json_body() -> dict:
    """Request JSON object, or a 400 ApiError."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("bad_request", "Corps JSON (objet) attendu.", status=400)
    return data


@bp.route("/session")
@login_required
def session_info():
    """Current user and instance — lets an island check its session is alive."""
    instance = getattr(g, "current_instance", None)
    return jsonify(
        user={"email": getattr(current_user, "email", None),
              "is_admin": bool(getattr(current_user, "is_admin", False))},
        instance=(
            {"slug": instance.slug, "label": instance.label, "chart": instance.chart}
            if instance else None
        ),
    )


def register_api(app):
    app.register_blueprint(bp)

    @app.errorhandler(ApiError)
    def _api_error(e):
        return error_response(e.code, e.message, e.status, e.fields)

    # App-level handlers: unmatched /api/... URLs never reach the blueprint.
    @app.errorhandler(CSRFError)
    def _csrf_error(e):
        if is_api_request():
            return error_response("csrf_error", "Jeton CSRF manquant ou invalide.", 400)
        return e

    @app.errorhandler(HTTPException)
    def _http_error(e):
        if is_api_request():
            return error_response(_HTTP_CODES.get(e.code, "http_error"), e.description, e.code)
        return e

    @app.errorhandler(500)
    def _server_error(e):
        if is_api_request():
            return error_response("server_error", "Erreur interne du serveur.", 500)
        return e
