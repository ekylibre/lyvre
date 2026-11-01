"""Codes de TVA des lignes d'écriture (lot T2, claudedocs/design_societe_tva.md § 3.2-3.3).

Lyvre choisit le code à la comptabilisation, d'après le taux, la nature (biens / services) et le
**régime TVA du tiers** (`fr`, `eu`, `world`) ; la déclaration (lot T3) se calcule ensuite depuis les
lignes codées du grand livre. Codes et mentions dans `data/vat_codes.json`.

Montants : `vat_base_cents` est la base HT d'une ligne de taxe, toujours positive ; son signe dans la
déclaration est celui de la ligne (une contrepassation ou un avoir inverse le sens, pas la base).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from app.extensions import db
from app.models import Account

DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "vat_codes.json"
# `fr_rc` : fournisseur non établi en France dont l'acheteur doit la TVA française (art. 283-1, ligne B4).
REGIMES = ("fr", "eu", "world", "fr_rc")
SALE_REGIMES = ("fr", "eu", "world")
IMPORT_CODES = {2000: "AL_I", 1000: "AL_I10", 550: "AL_I55", 210: "AL_I21"}
# Préfixes de TVA intracommunautaire des États membres (la Grèce : EL).
EU_PREFIXES = {"AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES", "FI", "FR", "HR", "HU", "IE", "IT",
               "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK"}
EU_COUNTRIES = {"allemagne", "autriche", "belgique", "bulgarie", "chypre", "croatie", "danemark", "espagne", "estonie",
                "finlande", "grece", "hongrie", "irlande", "italie", "lettonie", "lituanie", "luxembourg", "malte",
                "pays-bas", "pologne", "portugal", "republique tcheque", "tchequie", "roumanie", "slovaquie",
                "slovenie", "suede"}
# Comptes de TVA que Lyvre crée s'ils manquent (sous le regroupement le plus proche).
ACCOUNT_LABELS = {
    "4452": "TVA due intracommunautaire",
    "4453": "TVA due sur importations (autoliquidation)",
    "44562": "TVA sur immobilisations",
    "44566": "TVA sur autres biens et services",
    "44551": "TVA à décaisser",
    "44567": "Crédit de TVA à reporter",
    "44571": "TVA collectée",
    "44574": "TVA collectée à encaisser",
}


@lru_cache(maxsize=1)
def data() -> dict:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def codes() -> dict[str, dict]:
    return data()["codes"]


def is_known(code: str | None) -> bool:
    return code in codes()


def label(code: str | None) -> str:
    return codes().get(code or "", {}).get("label", "")


def regime_labels(sales: bool = False) -> dict[str, str]:
    """Régimes proposés ; une vente n'a pas le régime `fr_rc` (propre aux achats)."""
    return {k: v for k, v in data()["regimes"].items() if not sales or k in SALE_REGIMES}


def exemption(code: str | None) -> dict | None:
    """Mention de facture et catégorie Factur-X d'une vente sans TVA (`V_UE_S`, `V_EXP`…)."""
    return data()["sale_exemptions"].get(code or "")


# ------------------------------------------------------------------ régime du tiers

def _plain(text: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn").strip()


def guess_regime(vat_number: str | None, country: str | None) -> str:
    """Régime proposé d'après le n° de TVA (préfixe) ou, à défaut, le pays."""
    prefix = re.sub(r"[\s.]", "", vat_number or "").upper()[:2]
    if prefix == "FR":
        return "fr"
    if prefix in EU_PREFIXES:
        return "eu"
    name = _plain(country or "")
    if name in ("", "france"):
        return "fr"
    return "eu" if name in EU_COUNTRIES else "world"


def regime_of(entity) -> str:
    return (getattr(entity, "vat_regime", None) if entity is not None else None) or "fr"


def sale_regime(sale) -> str:
    """Régime d'une vente : celui du document, sinon de la facture d'un avoir, sinon du client."""
    if sale.vat_regime:
        return sale.vat_regime
    invoice = getattr(sale, "invoice", None)
    if sale.kind == "credit_note" and invoice is not None and invoice.vat_regime:
        return invoice.vat_regime
    return regime_of(sale.entity)


def purchase_regime(purchase) -> str:
    return purchase.vat_regime or regime_of(purchase.entity)


# ------------------------------------------------------------------ choix du code

def _rate_code(prefix: str, rate_bp: int) -> str | None:
    for code, spec in codes().items():
        if code.startswith(prefix) and spec["on"] == "tax" and spec["rate_bp"] == rate_bp \
                and spec["side"] == ("sale" if prefix == "V" else "purchase") and not code.startswith("AL"):
            return code
    return None


def sale_tax_code(rate_bp: int) -> str | None:
    """Vente imposable en France : `V20`, `V10`… (None pour un taux sans code)."""
    return _rate_code("V", rate_bp)


def sale_exemption_code(sale, nature: str) -> str | None:
    """Code d'une vente **sans TVA française** selon le régime du client, None si la vente est imposable
    en France. Un client de l'UE sans n° de TVA (particulier) reste imposé en France."""
    regime = sale_regime(sale)
    if regime == "eu":
        vat_number = (sale.client or {}).get("vat_number")
        if not vat_number:
            return None
        return "V_UE_B" if nature == "goods" else "V_UE_S"
    if regime == "world":
        return "V_EXP" if nature == "goods" else "V_EXO"
    return None


def purchase_code(regime: str, nature: str, rate_bp: int) -> str | None:
    """Achat : TVA déductible française (`D20`…) ou autoliquidation auprès d'un fournisseur non établi en
    France — services (`AL_S`, A3), biens de l'UE (`AL_B`, B2), biens importés hors UE (`AL_I…`, A4 et
    I1–I5 selon le taux), achats de l'article 283-1 (`AL_FR`, B4)."""
    if regime == "fr":
        return _rate_code("D", rate_bp)
    if regime == "fr_rc":
        return "AL_FR"
    if nature == "goods":
        return "AL_B" if regime == "eu" else IMPORT_CODES.get(rate_bp, "AL_I")
    return "AL_S"


def due_account_code(code: str | None) -> str:
    """Compte de la TVA autoliquidée due : 4453 pour une importation, 4452 sinon."""
    return "4453" if (code or "").startswith("AL_I") else "4452"


# ------------------------------------------------------------------ comptes

def account(code: str) -> Account:
    """Compte de TVA du plan, créé sous son regroupement le plus proche s'il manque (sans commit)."""
    found = Account.query.filter_by(code=code, is_header=False).first()
    if found is not None:
        return found
    parent = None
    for size in range(len(code) - 1, 1, -1):
        parent = Account.query.filter_by(code=code[:size]).first()
        if parent is not None:
            break
    created = Account(code=code, label=ACCOUNT_LABELS.get(code, code), account_type="TIERS",
                      parent_id=parent.id if parent else None)
    db.session.add(created)
    db.session.flush()
    return created


# ------------------------------------------------------------------ tiers créés par les synchronisations

def _guess_on_insert(_mapper, _connection, entity) -> None:
    """Fournisseur créé par une synchronisation (Qonto, saisie de facture) avec un n° de TVA étranger :
    régime proposé d'après ce numéro. Un régime déjà choisi (autre que France) est conservé."""
    if getattr(entity, "_vat_regime_chosen", False):  # choisi dans la fiche du tiers
        return
    if (entity.vat_regime or "fr") == "fr" and entity.vat_number:
        entity.vat_regime = guess_regime(entity.vat_number, entity.country)


def _register() -> None:
    from sqlalchemy import event

    from app.models import Entity
    if not event.contains(Entity, "before_insert", _guess_on_insert):
        event.listen(Entity, "before_insert", _guess_on_insert)


_register()
