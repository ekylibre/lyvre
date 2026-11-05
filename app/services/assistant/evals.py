"""Évaluation de l'assistant (lot AG9b.d, claudedocs/design_assistant_agricole.md § 8). HORS CI.

- `score(case, run)` : contrôles **déterministes** d'une exécution (outils appelés, textes, citations, propositions).
- `run_case(case, role)` : exécute un cas sur l'instance courante, dans une conversation jetable, et rend le texte, les
  outils, les propositions, l'usage et le coût estimé.
La notation par un modèle (grille courte) viendra après, pour les cas qui passent les contrôles déterministes.
"""
from __future__ import annotations

import re

ADMIN, ACCOUNTANT = "admin", "accountant"


def score(case: dict, run: dict) -> list[str]:
    """Écarts entre l'attendu du cas et l'exécution (liste vide : cas réussi)."""
    expect = case.get("expect") or {}
    text = (run.get("text") or "").lower()
    tools = set(run.get("tools") or [])
    problems = []
    if expect.get("tools_any") and not tools & set(expect["tools_any"]):
        problems.append(f"aucun des outils attendus appelé ({', '.join(expect['tools_any'])})")
    used = tools & set(expect.get("tools_none") or [])
    if used:
        problems.append(f"outils interdits appelés : {', '.join(sorted(used))}")
    for needle in expect.get("contains") or []:
        if needle.lower() not in text:
            problems.append(f"texte absent : « {needle} »")
    for needle in expect.get("not_contains") or []:
        if needle.lower() in text:
            problems.append(f"texte interdit présent : « {needle} »")
    for pattern in expect.get("cites") or []:
        if not re.search(pattern, run.get("text") or ""):
            problems.append(f"citation absente : {pattern}")
    if "proposals" in expect:
        kinds = sorted(run.get("proposals") or [])
        if kinds != sorted(expect["proposals"] or []):
            problems.append(f"propositions {kinds} au lieu de {sorted(expect['proposals'] or [])}")
    if run.get("errors"):
        problems.append("erreurs : " + " ; ".join(run["errors"]))
    return problems


def run_case(case: dict) -> dict:
    """Exécute le cas dans une conversation jetable de l'instance courante (appel réel à l'API Claude)."""
    from app.extensions import db
    from app.models import AssistantConversation
    from app.services.assistant import loop, settings

    role = case.get("role") or ADMIN
    conversation = AssistantConversation(user_id=0, title=f"[évaluation] {case['id']}")
    db.session.add(conversation)
    db.session.commit()
    out = {"text": "", "tools": [], "proposals": [], "errors": [], "usage": {}}
    try:
        for event in loop.ask(conversation, case["question"], case.get("page"), role, role != ACCOUNTANT):
            if event["type"] == "text":
                out["text"] += event["text"]
            elif event["type"] == "tool":
                out["tools"].append(event["name"])
            elif event["type"] == "action":
                out["proposals"].append(event["action"]["kind"])
            elif event["type"] == "error":
                out["errors"].append(event["message"])
            elif event["type"] == "done":
                out["usage"] = event["usage"]
        usage = out["usage"]
        out["cost_usd"] = settings.cost_usd(settings.model(), usage.get("input", 0), usage.get("output", 0),
                                            usage.get("cache_read", 0))
    finally:
        db.session.delete(conversation)
        db.session.commit()
    return out
