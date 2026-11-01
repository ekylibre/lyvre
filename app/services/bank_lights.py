"""Feu d'une transaction bancaire et catégorie affichée (lot TX1, claudedocs/design_ecran_transactions.md § 2).

- **Feu** : `red` (anomalie) › `orange` (à traiter) › `green` (à jour), avec ses motifs ; les motifs
  orange s'ajoutent aux rouges pour l'infobulle. Une transaction annulée par la banque et non rapprochée
  est verte (rien à faire, pas de justificatif attendu).
- **Catégorie affichée** : celle de Lyvre (posée par une règle) d'abord, sinon la catégorie Qonto
  (sous-catégorie de trésorerie, catégorie de trésorerie, code traduit).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

GREEN, ORANGE, RED = "green", "orange", "red"
LIGHTS = (GREEN, ORANGE, RED)
LIGHT_LABELS = {GREEN: "À jour", ORANGE: "À traiter", RED: "Anomalie"}
CATEGORIES_FILE = Path(__file__).resolve().parents[2] / "data" / "qonto_categories.json"


def light(bt, *, rule_default_tiers: bool = False, has_invoice: bool = False) -> tuple[str, list[str]]:
    """(couleur, motifs) ; `rule_default_tiers` : passée par une règle et restée sans tiers ; `has_invoice` :
    une facture d'achat ou de vente est liée à la transaction. Facture liée **et** écriture passée : à jour
    (la facture tient lieu de justificatif), sauf annulée encore rapprochée."""
    red, orange = [], []
    if bt.is_reversed and bt.reconciled:
        red.append("Annulée par la banque mais encore rapprochée")
    if has_invoice and bt.journal_line_id is not None and not red:
        return GREEN, ["Facture liée et écriture passée"]
    if bt.attachment_lost:
        red.append("Justificatif perdu")
    if not bt.reconciled and not bt.is_reversed:
        orange.append("À rapprocher")
    if bt.attachment_count == 0 and bt.attachment_required and not bt.attachment_lost and not bt.is_reversed:
        orange.append("Justificatif manquant")
    if rule_default_tiers:
        orange.append("Tiers par défaut")
    if red:
        return RED, red + orange
    if orange:
        return ORANGE, orange
    return GREEN, ["Annulée par la banque" if bt.is_reversed else "Rapprochée"]


@lru_cache(maxsize=1)
def _labels() -> dict[str, str]:
    return json.loads(CATEGORIES_FILE.read_text(encoding="utf-8"))["labels"]


def qonto_code_label(code: str | None) -> str | None:
    if not code:
        return None
    return _labels().get(code) or code.replace("_", " ").strip().capitalize() or None


def category_display(bt) -> dict | None:
    """`{label, source}` : catégorie Lyvre, sinon Qonto ; None si aucune."""
    if bt.category:
        return {"label": bt.category, "source": "lyvre"}
    label = (bt.qonto_cashflow_subcategory or bt.qonto_cashflow_category
             or qonto_code_label(bt.qonto_category))
    return {"label": label, "source": "qonto"} if label else None
