"""À-nouveaux calculés d'une restauration Ekylibre (lot RE2, claudedocs/design_restauration_ekylibre.md § 5).

Ekylibre n'a jamais clôturé les exercices des sauvegardes visées : aucune écriture de report n'existe. L'écriture
d'ouverture est donc calculée au premier jour repris :
- comptes de bilan (classes 1 à 5) : solde cumulé de toutes les lignes antérieures, compte par compte (le détail
  par tiers est conservé : un compte par tiers dans Ekylibre) ;
- résultats antérieurs (autres classes), jamais affectés, regroupés selon la forme juridique (D-R1) :
  entreprise individuelle → 108 ; société → résultat de l'exercice précédent en 120 / 129, plus anciens en
  110 / 119 ; forme inconnue → 12 pour le tout, signalé.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import timedelta

from app.services.ekylibre.data import EkyData

INDIVIDUAL_FORMS = {"EI", "EIRL", "ME", "AE", "EXPLOITANT", "INDIVIDUAL"}
RESULT_LABELS = {"108": "Compte de l'exploitant", "110": "Report à nouveau - solde créditeur",
                 "119": "Report à nouveau - solde débiteur", "12": "Résultat de l'exercice",
                 "120": "Résultat de l'exercice - bénéfice", "129": "Résultat de l'exercice – perte"}


def describe(amount: int) -> str:
    """Solde des comptes de résultat (débit − crédit) en mots : crédit = bénéfice, débit = perte."""
    return f"{'perte' if amount > 0 else 'bénéfice'} de {abs(amount) / 100:,.2f} €".replace(",", " ").replace(".", ",")


def _balance_sheet(number: str | None) -> bool:
    return bool(number) and number[0] in "12345"


@dataclass
class Opening:
    balances: Counter = field(default_factory=Counter)   # numéro Ekylibre → solde (classes 1 à 5, non nuls)
    results: list = field(default_factory=list)          # (code Lyvre, libellé, montant signé)
    legal_form: str = ""
    notes: list = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(self.balances.values()) + sum(amount for _c, _l, amount in self.results)


def needed(data: EkyData, profile) -> bool:
    """Profil standard, antériorité dans la sauvegarde, et pas d'écriture de report d'Ekylibre au premier jour."""
    from app.services.ekylibre.checks import opening_entries
    return (profile is not None and not profile.is_sci and data.has_history_before(data.start)
            and not opening_entries(data))


def compute(data: EkyData) -> Opening:
    before = data.balances_before(data.start)
    opening = Opening(balances=Counter({n: v for n, v in before.items() if _balance_sheet(n) and v}))
    result = sum(v for n, v in before.items() if not _balance_sheet(n))
    company = data.own_company() or {}
    legal = (company.get("legal_position_code") or "").strip().upper()
    opening.legal_form = legal
    if not result:
        return opening
    if legal in INDIVIDUAL_FORMS:
        opening.results.append(("108", RESULT_LABELS["108"], result))
        opening.notes.append(f"Résultats antérieurs ({describe(result)}) portés au compte de l'exploitant (108), "
                             "entreprise individuelle (D-R1).")
    elif legal:
        previous = data.fiscal_year(data.start - timedelta(days=1))
        last = sum(v for n, v in data.balances_before(data.start, previous["id"]).items()
                   if not _balance_sheet(n)) if previous else 0
        older = result - last
        if last:
            code = "120" if last < 0 else "129"
            opening.results.append((code, RESULT_LABELS[code], last))
        if older:
            code = "110" if older < 0 else "119"
            opening.results.append((code, RESULT_LABELS[code], older))
        opening.notes.append(f"Résultats antérieurs de la société ({legal}) : exercice précédent en 120 / 129 "
                             f"({describe(last)}), plus anciens en report à nouveau ({describe(older)}), à affecter (D-R1).")
    else:
        opening.results.append(("12", RESULT_LABELS["12"], result))
        opening.notes.append(f"Forme juridique absente dans Ekylibre : résultats antérieurs non affectés "
                             f"({describe(result)}) portés en 12, à affecter avec l'expert-comptable (D-R1).")
    return opening


def account_ids(data: EkyData, opening: Opening) -> set[str]:
    numbers = set(opening.balances)
    return {a["id"] for a in data.rows["accounts"] if a["number"] in numbers}
