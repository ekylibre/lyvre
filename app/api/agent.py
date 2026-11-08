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
        result, is_error = agent_tools.run(name, args if args is not None else {}, key, channel="rest")
    except agent_tools.ToolRefused as exc:
        status = 404 if exc.code == "unknown_tool" else 403
        raise ApiError(exc.code, exc.message, status) from None
    if is_error:
        return jsonify(error={"code": "tool_error", "message": result.get("error", "Erreur de l'outil."),
                              "result": result}), 422
    return jsonify(result=result)


@bp.route("/agent/files", methods=["POST"])
def agent_files_upload():
    """Dépôt d'une pièce (multipart `file`, PDF/JPEG/PNG ≤ 10 Mo) : jeton à passer en `file_token` aux outils
    d'écriture. Réservé à une clé qui écrit dans au moins un domaine."""
    from app.services import attachments
    from app.services.attachments import AttachmentError
    key = _key()
    if not key.writes:
        raise ApiError("domain_forbidden", f"La clé « {key.name} » n'écrit dans aucun domaine.", 403)
    try:
        token = attachments.stage(request.files.get("file"))
    except AttachmentError as exc:
        raise ApiError("validation_error", str(exc), 422) from None
    _path, meta = attachments.staged(token)
    return jsonify(file_token=token, name=meta["name"], mime=meta["mime"], size=meta["size"]), 201
