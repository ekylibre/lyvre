"""Assistant Claude (lot AG9b, claudedocs/design_assistant_agricole.md § 7, AGD26) : statut, conversations de
l'utilisateur, question avec réponse diffusée au fil de l'eau (SSE). Tous les rôles conversent ; les outils de
proposition sont réservés aux rôles admin et treasurer (Q-C9)."""
import json

from flask import Response, jsonify, request, stream_with_context
from flask_login import current_user

from app.access import current_role
from app.extensions import db
from app.models import AssistantConversation
from app.models.instance_membership import ROLE_ADMIN, ROLE_TREASURER
from app.services import external_config
from app.services.assistant import loop, settings

from . import ApiError, bp, json_body, notice


def _require():
    if not external_config.applies(settings.SERVICE):
        raise ApiError("not_found", "Assistant réservé aux exploitations agricoles.", 404)
    if not settings.available():
        raise ApiError("conflict", external_config.unavailable_message(settings.SERVICE) or "Assistant indisponible.", 409)


def _can_propose() -> bool:
    return current_role() in (ROLE_ADMIN, ROLE_TREASURER)


def _conversation(conversation_id: int) -> AssistantConversation:
    row = db.session.get(AssistantConversation, conversation_id)
    if row is None or row.user_id != current_user.id:
        raise ApiError("not_found", "Conversation introuvable.", 404)
    return row


def _conversation_payload(c: AssistantConversation) -> dict:
    return {"id": c.id, "title": c.title, "updated_at": c.updated_at.isoformat(timespec="seconds")}


@bp.route("/assistant/status")
def assistant_status():
    applies = external_config.applies(settings.SERVICE)
    available = applies and settings.available()
    left = loop.quota_left() if available else None
    return jsonify(item={
        "applies": applies, "enabled": applies and external_config.is_enabled(settings.SERVICE), "available": available,
        "message": external_config.unavailable_message(settings.SERVICE) if applies and not available else None,
        "model": settings.model() if available else None,
        "model_label": settings.MODELS.get(settings.model()) if available else None,
        "can_propose": _can_propose(), "quota_left": left,
        "server_key": external_config.server_locked(settings.SERVICE),
    })


@bp.route("/assistant/usage")
def assistant_usage():
    """Usage du mois (tokens et coût estimé), pour la fiche de l'intégration (lot AG9b.d)."""
    if current_role() != ROLE_ADMIN:
        raise ApiError("forbidden", "Réservé à l'administrateur de l'instance.", 403)
    if not external_config.applies(settings.SERVICE):
        raise ApiError("not_found", "Assistant réservé aux exploitations agricoles.", 404)
    return jsonify(item=loop.month_report())


@bp.route("/assistant/conversations")
def assistant_conversations():
    _require()
    rows = (AssistantConversation.query.filter_by(user_id=current_user.id)
            .order_by(AssistantConversation.updated_at.desc()).limit(50))
    return jsonify(items=[_conversation_payload(c) for c in rows])


@bp.route("/assistant/conversations", methods=["POST"])
def assistant_conversation_create():
    _require()
    row = AssistantConversation(user_id=current_user.id)
    db.session.add(row)
    db.session.commit()
    return jsonify(item=_conversation_payload(row)), 201


@bp.route("/assistant/conversations/<int:conversation_id>")
def assistant_conversation_detail(conversation_id):
    _require()
    row = _conversation(conversation_id)
    return jsonify(item={**_conversation_payload(row), "messages": loop.visible_messages(row)})


@bp.route("/assistant/conversations/<int:conversation_id>", methods=["DELETE"])
def assistant_conversation_delete(conversation_id):
    _require()
    db.session.delete(_conversation(conversation_id))
    db.session.commit()
    return jsonify(notices=[notice("Conversation supprimée.")])


@bp.route("/assistant/conversations/<int:conversation_id>/messages", methods=["POST"])
def assistant_ask(conversation_id):
    """Question → flux `text/event-stream` (événements text, tool, error, done)."""
    _require()
    row = _conversation(conversation_id)
    body = json_body()
    text, page, explain = body.get("text"), body.get("page"), body.get("explain") is True
    role, can_propose = current_role(), _can_propose()
    if not isinstance(text, str) or not text.strip():
        raise ApiError("validation_error", "Question vide.", 422, {"text": "Question vide."})

    from app.tenant import current_instance
    instance_key = getattr(current_instance(), "slug", None) or "default"
    if not loop.acquire(instance_key):
        raise ApiError("conflict", "Deux réponses de l'assistant sont déjà en cours pour cette exploitation : "
                       "réessayez dans un instant.", 409)

    def events():
        try:
            for event in loop.ask(row, text, page, role, can_propose, explain):
                yield f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            loop.release(instance_key)

    response = Response(stream_with_context(events()), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"              # pas de mise en tampon derrière nginx
    return response


# ------------------------------------------------------------------ propositions (lot AG9b.c)

def proposal_of_user(proposal_id: int):
    """Proposition d'une conversation de l'utilisateur courant (sinon 404)."""
    from app.models import AssistantMessage, AssistantProposal
    proposal = db.session.get(AssistantProposal, proposal_id)
    message = db.session.get(AssistantMessage, proposal.message_id) if proposal else None
    conversation = db.session.get(AssistantConversation, message.conversation_id) if message else None
    if conversation is None or conversation.user_id != current_user.id:
        raise ApiError("not_found", "Proposition introuvable.", 404)
    return proposal


@bp.route("/assistant/proposals/<int:proposal_id>")
def assistant_proposal(proposal_id):
    return jsonify(item=loop.proposal_payload(proposal_of_user(proposal_id)))


@bp.route("/assistant/proposals/<int:proposal_id>", methods=["PATCH"])
def assistant_proposal_update(proposal_id):
    """Statut d'une proposition : `accepted` (avec la référence du résultat enregistré par l'utilisateur) ou `ignored`."""
    proposal = proposal_of_user(proposal_id)
    body = json_body()
    status = body.get("status")
    if status not in ("accepted", "ignored", "open"):
        raise ApiError("validation_error", "Statut attendu : accepted, ignored ou open.", 422, {"status": "Statut inconnu."})
    proposal.status = status
    if "result_ref" in body:
        proposal.result_ref = str(body.get("result_ref") or "")[:60] or None
    db.session.commit()
    return jsonify(item=loop.proposal_payload(proposal))
