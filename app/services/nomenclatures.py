"""Nomenclatures de l'INSEE (lot G3) : libellés des catégories juridiques et des codes NAF.

Fichiers `data/insee/*.json` produits par `scripts/build_insee_nomenclatures.py` depuis les fichiers
publiés par l'INSEE, versionnés, chargés à la première demande. Un code inconnu (ou un fichier
absent) renvoie le code lui-même. Codes NAF sans point, comme Sirene (« 6820B »).
"""
import json
from functools import cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "insee"
NAF_FILES = {"NAFRev2": "naf_rev2.json", "NAF2025": "naf_2025.json"}


@cache
def _load(name: str) -> dict[str, str]:
    path = DATA_DIR / name
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("codes", {})


def legal_form_label(code: str | None) -> str:
    """« 6540 » → « Société civile immobilière »."""
    if not code:
        return ""
    return _load("categories_juridiques.json").get(code, code)


def naf_label(code: str | None, nomenclature: str | None = "NAFRev2") -> str:
    """« 6820B » → « Location de terrains et d'autres biens immobiliers »."""
    if not code:
        return ""
    code = code.replace(".", "")
    return _load(NAF_FILES.get(nomenclature or "NAFRev2", NAF_FILES["NAFRev2"])).get(code, code)
