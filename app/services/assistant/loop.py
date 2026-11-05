"""Boucle de conversation de l'assistant (lot AG9b.a, claudedocs/design_assistant_agricole.md §§ 3 et 7).

Boucle d'outils **manuelle**, côté serveur, diffusée au fil de l'eau : le générateur `ask` rend des événements
(`text`, `tool`, `error`, `done`) que l'API relaie en SSE.
- Historique **en ajout seulement** : chaque message (question, contexte de page, réponse complète avec ses blocs,
  résultats d'outils) est enregistré tel quel et renvoyé tel quel aux tours suivants.
- Préfixe en cache : outils (liste triée) + consignes figées, `cache_control` sur le dernier bloc des consignes.
- Contexte de page : message `system` en cours de conversation, après la question.
- Refus : `stop_reason == "refusal"` contrôlé avant tout ; repli serveur (`fallbacks: "default"`) avec Sonnet 5.5 et
  Opus 5.5 seulement (Haiku 5.5 n'en a pas).
- 8 tours d'outils au plus par question ; quota mensuel de tokens par instance.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Iterator

from sqlalchemy import func

from app.extensions import db
from app.models import AssistantConversation, AssistantMessage
from app.services.assistant import corpus, prompt, settings, tools

MAX_TOOL_TURNS = 8
MAX_TOKENS = 16_000
EFFORT = "medium"
FALLBACK_BETA = "server-side-fallback-2026-07-01"


import threading

_ACTIVE: dict[str, int] = {}
_LOCK = threading.Lock()


def acquire(instance_key: str) -> bool:
    """Au plus `MAX_ACTIVE_PER_INSTANCE` réponses en cours par instance (un fil de gunicorn chacune)."""
    with _LOCK:
        if _ACTIVE.get(instance_key, 0) >= settings.MAX_ACTIVE_PER_INSTANCE:
            return False
        _ACTIVE[instance_key] = _ACTIVE.get(instance_key, 0) + 1
        return True


def release(instance_key: str) -> None:
    with _LOCK:
        _ACTIVE[instance_key] = max(_ACTIVE.get(instance_key, 1) - 1, 0)


class AssistantError(Exception):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.message, self.status = message, status


# ------------------------------------------------------------------ usage

def month_usage(today: date | None = None) -> int:
    today = today or date.today()
    start = datetime(today.year, today.month, 1)
    total = (db.session.query(func.coalesce(func.sum(AssistantMessage.input_tokens + AssistantMessage.output_tokens
                                                     + AssistantMessage.cache_creation_tokens), 0))
             .filter(AssistantMessage.created_at >= start).scalar())
    return int(total or 0)


def month_report(today: date | None = None) -> dict:
    """Usage du mois par modèle (tokens, coût estimé en dollars)."""
    today = today or date.today()
    start = datetime(today.year, today.month, 1)
    rows = (db.session.query(AssistantMessage.model, func.count(AssistantMessage.id),
                             func.sum(AssistantMessage.input_tokens), func.sum(AssistantMessage.output_tokens),
                             func.sum(AssistantMessage.cache_read_tokens), func.sum(AssistantMessage.cache_creation_tokens))
            .filter(AssistantMessage.created_at >= start, AssistantMessage.role == "assistant")
            .group_by(AssistantMessage.model).all())
    models = []
    for model, count, tin, tout, cread, cwrite in rows:
        tin, tout, cread, cwrite = int(tin or 0), int(tout or 0), int(cread or 0), int(cwrite or 0)
        models.append({"model": model, "responses": count, "input_tokens": tin, "output_tokens": tout,
                       "cache_read_tokens": cread, "cache_write_tokens": cwrite,
                       "cost_usd": settings.cost_usd(model or settings.DEFAULT_MODEL, tin, tout, cread, cwrite)})
    quota = settings.monthly_tokens()
    used = month_usage(today)
    return {"month": f"{today:%Y-%m}", "used_tokens": used, "quota_tokens": quota or None,
            "left_tokens": None if not quota else max(quota - used, 0), "models": models,
            "cost_usd": round(sum(m["cost_usd"] for m in models), 4)}


def quota_left() -> int | None:
    quota = settings.monthly_tokens()
    return None if quota == 0 else max(quota - month_usage(), 0)


# ------------------------------------------------------------------ historique

def _save(conversation: AssistantConversation, role: str, content, kind: str = "text", **fields) -> AssistantMessage:
    row = AssistantMessage(conversation_id=conversation.id, role=role, content_json=json.dumps(content, ensure_ascii=False),
                           kind=kind, **fields)
    db.session.add(row)
    conversation.updated_at = datetime.utcnow()
    db.session.commit()
    return row


def history(conversation: AssistantConversation) -> list[dict]:
    return [{"role": m.role, "content": json.loads(m.content_json)} for m in conversation.messages]


def _blocks(response) -> list[dict]:
    """Blocs de la réponse, tels que l'API les a rendus (réflexion comprise), pour être renvoyés à l'identique."""
    return [block.to_dict() for block in response.content]


# ------------------------------------------------------------------ requête

def _request(model: str, messages: list[dict], can_propose: bool, effort: str = EFFORT) -> dict:
    params = {
        "model": model, "max_tokens": MAX_TOKENS,
        "system": [{"type": "text", "text": prompt.SYSTEM},
                   {"type": "text", "text": corpus.text(), "cache_control": {"type": "ephemeral"}}],
        "tools": [t.definition() for t in tools.for_role(can_propose)],
        "output_config": {"effort": effort},
        "messages": messages,
    }
    betas = []
    if model in settings.FALLBACK_MODELS:
        betas.append(FALLBACK_BETA)
        params["fallbacks"] = "default"
    if settings.lexicon():                                   # lot AG9b.d : serveur MCP public de Lexicon (Q-C6)
        betas.append(settings.MCP_BETA)
        params["mcp_servers"] = [{"type": "url", "url": settings.LEXICON_MCP_URL, "name": "lexicon"}]
        params["tools"] = params["tools"] + [{"type": "mcp_toolset", "mcp_server_name": "lexicon"}]
    if betas:
        params["betas"] = betas
    return params


def ask(conversation: AssistantConversation, text: str, page: dict | None, role: str | None,
        can_propose: bool, explain: bool = False) -> Iterator[dict]:
    """Pose une question et diffuse la réponse. Les erreurs deviennent un événement `error` (jamais d'exception)."""
    text = (text or "").strip()
    if not text:
        yield {"type": "error", "message": "Question vide."}
        return
    left = quota_left()
    if left is not None and left <= 0:
        yield {"type": "error", "message": "Quota mensuel de l'assistant atteint (Configuration › Intégrations)."}
        return
    if not conversation.messages:
        conversation.title = text[:80]
    _save(conversation, "user", [{"type": "text", "text": text[:8000]}])
    _save(conversation, "system", prompt.page_context(role, page, can_propose), kind="context")
    model = settings.model()
    try:
        client = settings.client()
    except RuntimeError as exc:
        yield {"type": "error", "message": str(exc)}
        return
    usage = {"input": 0, "output": 0, "cache_read": 0}
    for _turn in range(MAX_TOOL_TURNS + 1):
        try:
            with client.beta.messages.stream(**_request(model, history(conversation), can_propose,
                                                        "high" if explain else EFFORT)) as stream:
                for event in stream:
                    if event.type == "text":
                        yield {"type": "text", "text": event.text}
                response = stream.get_final_message()
        except Exception as exc:  # noqa: BLE001 — erreur de l'API rendue à l'interface, en français
            yield {"type": "error", "message": settings.describe_error(exc)}
            return
        u = response.usage
        tokens = {"input_tokens": u.input_tokens or 0, "output_tokens": u.output_tokens or 0,
                  "cache_read_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
                  "cache_creation_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0}
        usage["input"] += tokens["input_tokens"]
        usage["output"] += tokens["output_tokens"]
        usage["cache_read"] += tokens["cache_read_tokens"]
        answer = _save(conversation, "assistant", _blocks(response), model=getattr(response, "model", model),
                       stop_reason=response.stop_reason, **tokens)
        if response.stop_reason == "refusal":
            yield {"type": "error", "message": "L'assistant ne peut pas répondre à cette demande"
                   + ("." if model in settings.FALLBACK_MODELS else " avec ce modèle ; reformulez ou changez de modèle.")}
            break
        if response.stop_reason == "pause_turn":
            continue
        for block in response.content:
            if block.type == "mcp_tool_use":
                yield {"type": "tool", "name": f"lexicon:{getattr(block, 'name', '')}"}
        uses = [b for b in response.content if b.type == "tool_use"]
        if not uses:
            break
        if response.stop_reason == "max_tokens":
            yield {"type": "error", "message": "Réponse trop longue, interrompue : posez une question plus précise."}
            break
        results = []
        for block in uses:
            yield {"type": "tool", "name": block.name}
            ctx = {"message_id": answer.id}
            content, is_error = tools.run(block.name, block.input, can_propose, ctx)
            for action in ctx.get("actions", []):
                yield {"type": "action", "action": action}
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": content, "is_error": is_error})
        _save(conversation, "user", results, kind="tool_results")
    else:
        yield {"type": "error", "message": "Trop d'étapes pour cette question : reformulez plus simplement."}
    yield {"type": "done", "usage": usage, "conversation_id": conversation.id, "title": conversation.title}


# ------------------------------------------------------------------ vues

def visible_messages(conversation: AssistantConversation) -> list[dict]:
    """Messages affichés : questions et textes de réponse (ni contexte, ni résultats d'outils, ni réflexion), avec
    les propositions de chaque réponse."""
    from app.models import AssistantProposal
    ids = [m.id for m in conversation.messages if m.role == "assistant"]
    proposals: dict[int, list] = {}
    for p in AssistantProposal.query.filter(AssistantProposal.message_id.in_(ids)).order_by(AssistantProposal.id) if ids else []:
        proposals.setdefault(p.message_id, []).append(proposal_payload(p))
    out = []
    for m in conversation.messages:
        if m.kind != "text" or m.role == "system":
            continue
        blocks = json.loads(m.content_json)
        text = "".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text")
        tools_used = [b.get("name") for b in blocks if isinstance(b, dict) and b.get("type") == "tool_use"]
        if not text and not tools_used:
            continue
        out.append({"id": m.id, "role": m.role, "text": text, "tools": tools_used,
                    "actions": proposals.get(m.id, []), "created_at": m.created_at.isoformat(timespec="seconds")})
    return out


def proposal_payload(p) -> dict:
    payload = json.loads(p.payload_json)
    return {"id": p.id, "kind": p.kind, "payload": payload, "status": p.status, "result_ref": p.result_ref,
            "summary": payload.get("label") if p.kind == "navigate" else None}
