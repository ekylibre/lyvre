"""Outils d'agent par REST (lot AK2, claudedocs/design_api_mcp_aiffel.md § 2 D2, § 9.3).

Même registre que le serveur MCP (app/services/agent_tools.py) : `GET /agent/tools` liste les outils de la clé avec
leurs schémas, `POST /agent/tools/<outil>` les exécute (corps = arguments). Clé d'API seulement.
"""
from flask import g, jsonify, request

from app.services import agent_tools

from . import ApiError, bp


def _key():
    key = getattr(g, "api_key", None)
    if key is None:
        raise ApiError("forbidden", "Outils d'agent : appel par clé d'API seulement (Authorization: Bearer lyv_…).", 403)
    return key


@bp.route("/agent/tools")
def agent_tools_list():
    key = _key()
    return jsonify(items=[{**t.definition(), "domain": t.domain, "access": t.access} for t in agent_tools.for_key(key)])


@bp.route("/agent/tools/<name>", methods=["POST"])
def agent_tools_call(name):
    key = _key()
    args = request.get_json(silent=True)
    try:
        result, is_error = agent_tools.run(name, args if args is not None else {}, key)
    except agent_tools.ToolRefused as exc:
        status = 404 if exc.code == "unknown_tool" else 403
        raise ApiError(exc.code, exc.message, status) from None
    if is_error:
        return jsonify(error={"code": "tool_error", "message": result.get("error", "Erreur de l'outil."),
                              "result": result}), 422
    return jsonify(result=result)
