"""Activités proposées à la reprise d'un dossier (lot AG10.a, claudedocs/design_efacturation_agricole.md § 7, AGD27).

Les cabinets tiennent un sous-compte de vente par production (`70117111` « MAIS GRAINS », `70142000` « ASPERGES »).
Repris sous 7011 à 7014 (`fec_import`, ancien plan agricole), ils deviennent des **activités** d'AG8 :
- un sous-compte de ventes de produits sans règle analytique est proposé ;
- son libellé est rapproché d'une production Lexicon (mots identiques, accents et pluriels ignorés) ; à défaut,
  l'activité garde le libellé du compte et la famille se déduit du compte (7011 végétaux, 7012 et 7014 animaux,
  7013 produits transformés) ;
- une activité existante de même production ou de même nom est reprise plutôt que doublée ;
- à la création : un atelier par famille (repris s'il existe), l'activité, et la règle « compte → activité ».

Les variations de stock (713) restent hors analytique (`analytic_allocation.EXCLUDED_PREFIXES`) : pas de règle.
"""
from __future__ import annotations

import re
import unicodedata

from app.extensions import db
from app.models import Account, Activity, AnalyticRule, Workshop
from app.models.analytic import ACTIVITY_FAMILIES

PARENTS = {"7011": "plant_farming", "7012": "animal_farming", "7013": "processing", "7014": "animal_farming"}
STOP = {"de", "d", "du", "des", "la", "le", "les", "et", "a", "au", "en", "ve", "vte", "vtes", "vente", "ventes"}


class ImportActivityError(Exception):
    def __init__(self, message, field=None, status=422):
        super().__init__(message)
        self.message, self.field, self.status = message, field, status


def _words(text: str) -> frozenset[str]:
    raw = unicodedata.normalize("NFKD", re.sub(r"[’'`]", " ", text or "")).encode("ascii", "ignore").decode().lower()
    words = set()
    for w in re.split(r"[^a-z0-9]+", raw):
        if not w or w in STOP or w.isdigit():
            continue
        words.add(w[:-1] if len(w) > 3 and w.endswith(("s", "x")) else w)
    return frozenset(words)


def match_production(label: str) -> dict | None:
    """Production Lexicon du libellé : mêmes mots ; sinon la plus précise dont tous les mots sont dans le libellé ;
    sinon la seule dont le nom contient tous les mots d'un libellé d'au moins deux mots. None si rien ou ambigu."""
    from app.services import analytic
    words = _words(label)
    if not words:
        return None
    productions = [(p, _words(p["name"])) for p in analytic._lexicon()["productions"]]
    exact = [p for p, w in productions if w == words]
    if exact:
        return exact[0]
    inside = sorted(((p, w) for p, w in productions if w and w <= words), key=lambda x: -len(x[1]))
    if inside and (len(inside) == 1 or len(inside[0][1]) > len(inside[1][1])):
        return inside[0][0]
    if len(words) < 2:                                   # un seul mot (« MATERIEL ») : trop vague
        return None
    around = [p for p, w in productions if words <= w]
    return around[0] if len(around) == 1 else None


def _family_parent(account: Account) -> str | None:
    return next((PARENTS[p] for p in sorted(PARENTS, key=len, reverse=True) if account.code.startswith(p)), None)


def _existing_activity(name: str, reference: str | None) -> Activity | None:
    if reference:
        found = Activity.query.filter_by(lexicon_reference=reference, archived=False).first()
        if found is not None:
            return found
    words = _words(name)
    return next((a for a in Activity.query.filter_by(archived=False).all() if _words(a.name) == words), None)


def proposals() -> list[dict]:
    """Sous-comptes de ventes de produits (7011 à 7014, hors comptes du plan) sans règle analytique."""
    from app.services import agri_chart
    from app.services.analytic_allocation import _rules, rule_for
    chart, rules, out = agri_chart.chart_codes(), _rules(), []
    for account in Account.query.filter(Account.code.like("701%")).order_by(Account.code):
        family = _family_parent(account)
        if family is None or account.code in chart or account.is_header or rule_for(account.code, rules):
            continue
        production = match_production(account.label)
        name = production["name"] if production else account.label.strip().capitalize()[:120]
        existing = _existing_activity(name, production["reference"] if production else None)
        out.append({"account_id": account.id, "code": account.code, "label": account.label,
                    "name": existing.name if existing else name,
                    "lexicon_reference": production["reference"] if production else None,
                    "lexicon_name": production["name"] if production else None,
                    "family": production["family"] if production and production["family"] in ACTIVITY_FAMILIES else family,
                    "activity_id": existing.id if existing else None})
    return out


def _workshop(family: str) -> Workshop:
    from app.services import analytic
    found = Workshop.query.filter_by(family=family, archived=False).order_by(Workshop.position, Workshop.id).first()
    if found is not None:
        return found
    name = ACTIVITY_FAMILIES[family]
    if Workshop.query.filter_by(name=name).first() is not None:
        name = f"{name} (reprise)"
    return analytic.save_workshop(None, {"name": name, "family": family})


def create(items: list) -> dict:
    """Crée les activités choisies et leurs règles. `items` : `{account_id, name?}` pris parmi les propositions."""
    from app.services import analytic, analytic_allocation
    if not isinstance(items, list) or not items:
        raise ImportActivityError("Aucune activité choisie.", "items")
    offered = {p["account_id"]: p for p in proposals()}
    created = rules = 0
    for item in items:
        account_id = item.get("account_id") if isinstance(item, dict) else None
        proposal = offered.get(account_id)
        if proposal is None:
            raise ImportActivityError("Compte sans proposition (déjà ventilé ou hors ventes de produits).", "items", 409)
        activity = db.session.get(Activity, proposal["activity_id"]) if proposal["activity_id"] else None
        if activity is None:
            name = str(item.get("name") or proposal["name"]).strip()[:120] or proposal["name"]
            activity = _existing_activity(name, proposal["lexicon_reference"])
        if activity is None:
            workshop = _workshop(proposal["family"])
            data = {"workshop_id": workshop.id, "name": name}
            if proposal["lexicon_reference"]:
                data["lexicon_reference"] = proposal["lexicon_reference"]
            activity = analytic.save_activity(None, data)
            created += 1
        analytic_allocation.save_rule({"account_prefix": proposal["code"], "activity_id": activity.id})
        rules += 1
    db.session.flush()
    return {"activities": created, "rules": rules}
