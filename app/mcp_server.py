"""Serveur MCP de Lyvre (lot AK2, claudedocs/design_api_mcp_aiffel.md § 6, décision D1).

Transport HTTP streamable **sans état**, réponses JSON (pas de flux SSE) : `POST /mcp` reçoit un message JSON-RPC 2.0
(ou un lot) et répond en `application/json` ; une notification seule reçoit 202. `GET` et `DELETE` : 405 (pas de flux
serveur, pas de session). Authentification par clé d'API (`Authorization: Bearer lyv_…`, app/api_auth.py) ; les outils
sont ceux des domaines de la clé (app/services/agent_tools.py).
"""
from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, request


bp = Blueprint("mcp", __name__)

PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26")
SERVER_NAME = "lyvre"

PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS, INTERNAL_ERROR = -32700, -32600, -32601, -32602, -32603


def _error(msg_id, code, message, data=None) -> dict:
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": msg_id, "error": error}


def _result(msg_id, result) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def instructions(key) -> str:
    from app.models import FiscalYear
    from app.services import api_domains, organization
    from app.tenant import current_instance
    from datetime import date
    inst = current_instance()
    org = organization.get()
    today = date.today()
    fy = FiscalYear.query.filter(FiscalYear.start_date <= today, FiscalYear.end_date >= today).first()
    kinds = {"asso": "association", "sci": "SCI", "societe": "société", "agri": "exploitation agricole"}
    reads = ", ".join(api_domains.label(d) for d in sorted(key.reads)) or "aucun"
    writes = ", ".join(api_domains.label(d) for d in sorted(key.writes)) or "aucun"
    period = f"exercice en cours « {fy.label} » du {fy.start_date:%d/%m/%Y} au {fy.end_date:%d/%m/%Y}" if fy \
        else "aucun exercice ouvert à la date du jour"
    return (f"Lyvre, comptabilité de « {org.name or inst.label} » ({kinds.get(inst.chart, inst.chart)}), {period}. "
            f"Domaines lus : {reads}. Domaines écrits : {writes}. "
            "Toute création est un BROUILLON que l'utilisateur vérifie et valide lui-même dans Lyvre : ne dites jamais "
            "qu'une saisie est comptabilisée, validée ou envoyée. Montants en euros, avec une virgule décimale. "
            "Commencez par get_context si vous ne connaissez pas le dossier ; les résultats donnent le lien (url) vers "
            "l'écran de Lyvre.")


def _version() -> str:
    from app import version
    try:
        return version.version()
    except Exception:  # noqa: BLE001 — journal des versions absent : le serveur répond quand même
        return "inconnue"


def _initialize(params: dict) -> dict:
    wanted = params.get("protocolVersion")
    version = wanted if wanted in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
    return {"protocolVersion": version, "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "title": "Lyvre", "version": _version()},
            "instructions": instructions(g.api_key)}


def _call(params: dict) -> dict:
    from app.services import agent_tools
    name = params.get("name")
    if not isinstance(name, str):
        raise _RpcError(INVALID_PARAMS, "Paramètre « name » attendu.")
    try:
        result, is_error = agent_tools.run(name, params.get("arguments"), g.api_key)
    except agent_tools.ToolRefused as exc:
        result, is_error = {"error": exc.message, "code": exc.code}, True
    return {"content": [{"type": "text", "text": agent_tools.to_text(result)}],
            "structuredContent": result, "isError": is_error}


class _RpcError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def _handle(message) -> dict | None:
    """Réponse à un message JSON-RPC, ou None pour une notification."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
        return _error(message.get("id") if isinstance(message, dict) else None, INVALID_REQUEST, "Requête JSON-RPC invalide.")
    msg_id, method = message.get("id"), message["method"]
    params = message.get("params") or {}
    if "id" not in message:          # notification (notifications/initialized, notifications/cancelled…)
        return None
    if not isinstance(params, dict):
        return _error(msg_id, INVALID_PARAMS, "Paramètres : objet attendu.")
    try:
        if method == "initialize":
            return _result(msg_id, _initialize(params))
        if method == "ping":
            return _result(msg_id, {})
        if method == "tools/list":
            from app.services import agent_tools
            return _result(msg_id, {"tools": [t.definition() for t in agent_tools.for_key(g.api_key)]})
        if method == "tools/call":
            return _result(msg_id, _call(params))
        return _error(msg_id, METHOD_NOT_FOUND, f"Méthode inconnue : {method}.")
    except _RpcError as exc:
        return _error(msg_id, exc.code, exc.message)
    except Exception:  # noqa: BLE001
        current_app.logger.exception("MCP : erreur sur %s", method)
        return _error(msg_id, INTERNAL_ERROR, "Erreur interne du serveur.")


def _origin_ok() -> bool:
    """Contre le rebinding DNS : un en-tête Origin, s'il est présent, doit être l'adresse de Lyvre."""
    origin = request.headers.get("Origin")
    if not origin:
        return True
    base = (current_app.config.get("APP_BASE_URL") or "").rstrip("/")
    return bool(base) and origin.rstrip("/") == base


def _unauthorized():
    from app.api_auth import INVALID_MESSAGE
    response = jsonify(_error(None, INVALID_REQUEST, INVALID_MESSAGE))
    response.status_code = 401
    response.headers["WWW-Authenticate"] = 'Bearer realm="lyvre"'
    return response


@bp.route("/mcp", methods=["POST"])
def endpoint():
    if getattr(g, "api_key", None) is None:
        return _unauthorized()
    if not _origin_ok():
        response = jsonify(_error(None, INVALID_REQUEST, "Origine refusée."))
        response.status_code = 403
        return response
    version = request.headers.get("MCP-Protocol-Version")
    if version and version not in PROTOCOL_VERSIONS:
        response = jsonify(_error(None, INVALID_REQUEST, f"Version du protocole MCP non prise en charge : {version}."))
        response.status_code = 400
        return response
    payload = request.get_json(silent=True)
    if payload is None:
        response = jsonify(_error(None, PARSE_ERROR, "Corps JSON attendu."))
        response.status_code = 400
        return response
    if isinstance(payload, list):
        replies = [r for r in (_handle(m) for m in payload) if r is not None]
        return (jsonify(replies), 200) if replies else ("", 202)
    reply = _handle(payload)
    return (jsonify(reply), 200) if reply is not None else ("", 202)


@bp.route("/mcp", methods=["GET", "DELETE"])
def no_stream():
    response = jsonify(_error(None, INVALID_REQUEST, "Serveur sans état : ni flux serveur (GET) ni session (DELETE)."))
    response.status_code = 405
    response.headers["Allow"] = "POST"
    return response


def register(app):
    from app.extensions import csrf
    csrf.exempt(bp)           # requêtes par clé seulement, sans cookie
    app.register_blueprint(bp)
