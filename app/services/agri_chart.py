"""Plan « Exploitation agricole » : reprise des numéros de l'ancien plan comptable agricole (PCGA 1986), tels que
les cabinets les utilisent encore (FEC Isacompta sur 8 chiffres), vers le plan agri (titre 5 du Recueil PCG 2026).
Lot AG1.b ; utilisé par le jeu d'essai (AG1.f) et l'import des dossiers (AG10.6).

Règle, sur le numéro débarrassé des zéros de fin (`60110000` → `6011`) :
1. correspondance exacte de `data/agri_pcga1986_map.json` ;
2. sinon la correspondance du plus long préfixe (les sous-comptes de culture sont repliés : `70117111` → `7011`) ;
3. sinon le plus long préfixe existant dans le plan agri (le numéro n'a pas changé).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data"


@lru_cache(maxsize=1)
def _mapping() -> tuple[dict[str, str], dict[str, str]]:
    data = json.loads((DATA / "agri_pcga1986_map.json").read_text(encoding="utf-8"))
    return data["map"], data.get("unmapped") or {}


@lru_cache(maxsize=1)
def chart_codes() -> frozenset[str]:
    return frozenset(a["code"] for a in json.loads((DATA / "plan_comptable_agri.json").read_text(encoding="utf-8")))


def normalize(code: str) -> str:
    """`60110000` → `6011` ; garde au moins trois chiffres (`40100000` → `401`)."""
    code = (code or "").strip()
    stripped = code.rstrip("0")
    return stripped if len(stripped) >= 3 else code[:3]


def map_pcga1986(code: str) -> str | None:
    """Compte du plan agri pour un numéro de l'ancien plan ; None si aucun (numéro hors plan ou sans correspondance,
    à choisir à la main)."""
    old = normalize(code)
    mapping, unmapped = _mapping()
    for n in range(len(old), 1, -1):
        prefix = old[:n]
        if prefix in unmapped:
            return None
        if prefix in mapping:
            return mapping[prefix]
    codes = chart_codes()
    return next((old[:n] for n in range(len(old), 1, -1) if old[:n] in codes), None)
