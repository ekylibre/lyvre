"""Client Lexicon (OSFarm) côté serveur (lot AG3.e, décision AGD4) : fiche d'une entreprise par SIREN, avec les aides
PAC publiées par l'ASP année par année (`cap-by-year`, jeu `cap_beneficiaries`).

Route `GET /links/enterprises/<siren>.json`, réservée aux membres : clé `LEXICON_API_KEY` en
`Authorization: Bearer`, jamais transmise au navigateur. Montants publiés en euros (deux décimales), convertis en
centimes. Les réponses ne sont pas journalisées (un exploitant individuel peut y figurer sous son nom).
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

import requests
from flask import current_app

TIMEOUT = 15


class LexiconUnavailable(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def configured() -> bool:
    return bool(current_app.config.get("LEXICON_API_KEY"))


def _cents(value) -> int:
    try:
        return int((Decimal(str(value or 0)) * 100).quantize(Decimal(1)))
    except (InvalidOperation, ValueError):
        raise LexiconUnavailable("Lexicon : montant illisible dans la réponse.") from None


def cap_by_year(siren: str) -> list[dict] | None:
    """Aides publiées par année ({year, feaga_cents, feader_cents, cofinanced_cents, total_cents}), la plus récente
    d'abord ; None si le SIREN n'est pas connu de Lexicon."""
    key = current_app.config.get("LEXICON_API_KEY")
    if not key:
        raise LexiconUnavailable("Lexicon n'est pas configuré sur ce serveur (clé LEXICON_API_KEY).")
    if not (isinstance(siren, str) and len(siren) == 9 and siren.isdigit()):
        raise LexiconUnavailable("SIREN de neuf chiffres attendu (Configuration › Structure › Identité).")
    base = current_app.config.get("LEXICON_URL") or "https://lexicon.osfarm.org"
    try:
        response = requests.get(f"{base.rstrip('/')}/links/enterprises/{siren}.json", timeout=TIMEOUT,
                                headers={"Accept": "application/json", "Authorization": f"Bearer {key}"})
    except requests.RequestException:
        raise LexiconUnavailable("Lexicon ne répond pas : réessayez plus tard.") from None
    if response.status_code == 404:
        return None
    if response.status_code in (401, 403):
        raise LexiconUnavailable("Lexicon refuse la clé du serveur (clé absente, expirée ou sans accès membre).")
    if response.status_code == 429:
        raise LexiconUnavailable("Lexicon : trop de requêtes, réessayez dans une minute.")
    if response.status_code != 200:
        raise LexiconUnavailable(f"Lexicon : réponse inattendue ({response.status_code}).")
    try:
        rows = response.json().get("cap-by-year") or []
    except (ValueError, AttributeError):
        raise LexiconUnavailable("Lexicon : réponse illisible.") from None
    out = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("year"), int):
            continue
        out.append({"year": row["year"], "feaga_cents": _cents(row.get("feaga")), "feader_cents": _cents(row.get("feader")),
                    "cofinanced_cents": _cents(row.get("cofinanced")), "total_cents": _cents(row.get("total"))})
    return out
