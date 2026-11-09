"""Profil des démarches d'une exploitation (lot AG9a, claudedocs/design_echeancier_agricole.md § 3 E5) : activités
et obligations hors fiscalité qui décident des échéances applicables (PAC, MSA, employeur, phyto, irrigation, baux…).

Stocké en JSON dans `organization.agri_profile`. Une valeur absente vaut « non renseigné » : l'échéancier pose alors
la question plutôt que de supposer.
"""
from __future__ import annotations

import json
import re
from datetime import date

from app.extensions import db

BOOLEANS = {
    "pac": "Demandeur des aides PAC",
    "employer": "Employeur de salariés",
    "irrigation": "Irrigant (prélèvements d'eau)",
    "vulnerable_zone": "En zone vulnérable (directive nitrates)",
    "plant_protection": "Utilisateur de produits phytosanitaires",
    "bonded_warehouse": "Entrepositaire agréé (viticulture)",
    "young_farmer": "Jeune agriculteur (DJA, plan d'entreprise en cours)",
    "non_agricultural": "Activités non agricoles (gîte, transformation, négoce, méthanisation, travaux pour tiers)",
    "msa_monthly": "Cotisations MSA mensualisées",
    # Lot CG5.d (Q8) : choix du dossier ; fiscalement, les façons culturales des jeunes plantations sont des avances aux
    # cultures (BOI-BA-BASE-20-30-10-20 § 170 et 180).
    "plantation_costs_capitalized": "Jeunes plantations : façons culturales immobilisées (production immobilisée)",
}
DATES = {
    "certiphyto_expires_on": "Fin de validité du Certiphyto",
    "young_farmer_since": "Date d'installation aidée (JA)",
}
PRODUCTIONS = {
    "field_crops": "Grandes cultures", "cattle": "Bovins", "sheep_goats": "Ovins, caprins", "pigs": "Porcins",
    "poultry": "Volailles", "viticulture": "Viticulture", "market_gardening": "Maraîchage",
    "arboriculture": "Arboriculture", "organic": "Agriculture biologique",
}
MSA_FUNDS = {"nord_pas_de_calais": "MSA Nord-Pas-de-Calais", "cotes_normandes": "MSA Côtes normandes",
             "other": "Autre caisse"}
LEASE_ROLES = {"tenant": "Preneur (je paie le fermage)", "landlord": "Bailleur (je perçois le fermage)"}
# Drapeaux lus par les conditions des fiches (`applies.flags`) : booléens et drapeaux dérivés. `msa_collaborator` ne se
# saisit pas : il est calculé par l'échéancier (une personne suivie dans /msa/ au statut de collaborateur).
DERIVED_FLAGS = ("leases", "msa_collaborator")
FLAGS = (*BOOLEANS, *DERIVED_FLAGS)
_MONTH_DAY = re.compile(r"(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])")


class ProfileError(Exception):
    def __init__(self, message, field=None):
        super().__init__(message)
        self.message, self.field = message, field


def _org():
    from app.services import organization
    return organization.get()


def get() -> dict:
    raw = _org().agri_profile
    try:
        data = json.loads(raw) if raw else {}
    except ValueError:
        data = {}
    return data if isinstance(data, dict) else {}


def flag(profile: dict, name: str) -> bool | None:
    """Valeur d'un drapeau : True, False, ou None s'il n'est pas renseigné."""
    if name == "leases":
        return None if "leases" not in profile else bool(profile["leases"])
    value = profile.get(name)
    return value if isinstance(value, bool) else None


def clean(data: dict) -> dict:
    """Profil validé (ProfileError rattachée au champ fautif) ; les clés inconnues sont refusées."""
    if not isinstance(data, dict):
        raise ProfileError("Profil attendu.")
    known = {*BOOLEANS, *DATES, "productions", "msa_fund", "pacage", "leases"}
    unknown = set(data) - known
    if unknown:
        raise ProfileError(f"Champ inconnu : {sorted(unknown)[0]}.", sorted(unknown)[0])
    out: dict = {}
    for key in BOOLEANS:
        if key in data and data[key] is not None:
            if not isinstance(data[key], bool):
                raise ProfileError("Oui ou non attendu.", key)
            out[key] = data[key]
    for key in DATES:
        if data.get(key):
            try:
                out[key] = date.fromisoformat(str(data[key])[:10]).isoformat()
            except ValueError:
                raise ProfileError("Date attendue (AAAA-MM-JJ).", key) from None
    if "productions" in data and data["productions"] is not None:
        values = data["productions"]
        if not isinstance(values, list) or any(v not in PRODUCTIONS for v in values):
            raise ProfileError("Production inconnue.", "productions")
        out["productions"] = sorted(set(values))
    if data.get("msa_fund"):
        if data["msa_fund"] not in MSA_FUNDS:
            raise ProfileError("Caisse MSA inconnue.", "msa_fund")
        out["msa_fund"] = data["msa_fund"]
    if data.get("pacage"):
        pacage = str(data["pacage"]).strip()
        if not re.fullmatch(r"\d{9}", pacage):
            raise ProfileError("Numéro PACAGE : 9 chiffres.", "pacage")
        out["pacage"] = pacage
    if "leases" in data and data["leases"] is not None:
        if not isinstance(data["leases"], list) or len(data["leases"]) > 50:
            raise ProfileError("Liste de baux attendue.", "leases")
        leases = []
        for lease in data["leases"]:
            if not isinstance(lease, dict):
                raise ProfileError("Bail invalide.", "leases")
            label = str(lease.get("label") or "").strip()[:120]
            due = str(lease.get("due") or "").strip()
            role = lease.get("role") or "tenant"
            if not label:
                raise ProfileError("Libellé du bail obligatoire.", "leases")
            if not _MONTH_DAY.fullmatch(due):
                raise ProfileError("Échéance du bail : jour et mois (MM-JJ, ex. 11-11).", "leases")
            if role not in LEASE_ROLES:
                raise ProfileError("Rôle du bail inconnu.", "leases")
            leases.append({"label": label, "due": due, "role": role})
        out["leases"] = leases
    return out


def save(data: dict) -> dict:
    profile = clean(data)
    _org().agri_profile = json.dumps(profile, ensure_ascii=False) if profile else None
    db.session.commit()
    return profile


def meta() -> dict:
    options = lambda d: [{"value": k, "label": v} for k, v in d.items()]  # noqa: E731
    return {"booleans": options(BOOLEANS), "dates": options(DATES), "productions": options(PRODUCTIONS),
            "msa_funds": options(MSA_FUNDS), "lease_roles": options(LEASE_ROLES)}


# ------------------------------------------------------------------ indices de la comptabilité et usages (essai 09/11/2026)

# Comptes qui laissent présumer une réponse « oui » (préfixes, sens attendu : produit au crédit, charge au débit).
EVIDENCE_ACCOUNTS = {
    "pac": (("742", "743", "744", "745"), "credit"),
    "employer": (("641", "645"), "debit"),
    "plant_protection": (("60113", "31113"), "debit"),
}
ANIMAL_PRODUCTIONS = {"cattle", "sheep_goats", "pigs", "poultry"}
PLANT_PRODUCTIONS = {"field_crops", "viticulture", "market_gardening", "arboriculture"}


def _euros(cents: int) -> str:
    return f"{cents / 100:,.0f} €".replace(",", " ")


def _balances():
    """Soldes par compte du dernier exercice, hors à-nouveaux : (fy, {code: débit − crédit}) ou (None, {})."""
    from sqlalchemy import func

    from app.models import Account, FiscalYear, JournalEntry, JournalLine
    from app.models.journal_entry import SOURCE_OPENING

    fy = FiscalYear.query.order_by(FiscalYear.start_date.desc()).first()
    if fy is None:
        return None, {}
    rows = (db.session.query(Account.code, func.sum(JournalLine.debit_cents - JournalLine.credit_cents))
            .join(JournalLine, JournalLine.account_id == Account.id).join(JournalEntry)
            .filter(JournalEntry.fiscal_year_id == fy.id, JournalEntry.source != SOURCE_OPENING)
            .group_by(Account.code).all())
    return fy, {code: total or 0 for code, total in rows}


def _sum(balances: dict, prefixes, side: str) -> tuple[int, list[str]]:
    total, codes = 0, []
    for code, amount in balances.items():
        if code.startswith(tuple(prefixes)):
            value = -amount if side == "credit" else amount
            if value > 0:
                total += value
                codes.append(code)
    return total, sorted(codes)


def hints(profile: dict | None = None) -> dict:
    """Indices tirés de la comptabilité, par question : {clé: {"text", "suggested", "conflict"}}. Jamais une réponse :
    l'utilisateur confirme (le profil reste « non renseigné » tant qu'il n'a pas répondu)."""
    from app.models import Account
    from app.models.aid import Aid

    profile = get() if profile is None else profile
    fy, balances = _balances()
    out: dict = {}

    def add(key, text, suggested=True):
        answer = flag(profile, key) if key in FLAGS else None
        out[key] = {"text": text, "suggested": suggested, "conflict": answer is not None and answer != suggested}

    where = f" (exercice {fy.label})" if fy is not None else ""
    for key, (prefixes, side) in EVIDENCE_ACCOUNTS.items():
        total, codes = _sum(balances, prefixes, side)
        if total:
            add(key, f"{'Comptes' if len(codes) > 1 else 'Compte'} {', '.join(codes)} "
                     f"mouvementé{'s' if len(codes) > 1 else ''} : {_euros(total)}{where}.")
    schemes = {a.scheme for a in Aid.query.all()}
    if schemes and "pac" not in out:
        add("pac", "Aides saisies dans le registre des aides.")
    if "dja" in schemes:
        add("young_farmer", "DJA saisie dans le registre des aides.")
    accessory = {a.code for a in Account.query.filter_by(ba_income_class="accessory")}
    total, codes = _sum(balances, tuple(accessory), "credit") if accessory else (0, [])
    if total:
        add("non_agricultural", f"Revenus accessoires repérés (Structure › Fiscalité) : {', '.join(codes)}, "
                                f"{_euros(total)}{where}.")
    rent, _ = _sum(balances, ("6131",), "debit")
    if rent:
        text = f"Fermages payés (6131) : {_euros(rent)}{where}."
        leases = profile.get("leases")
        tenant = isinstance(leases, list) and any(l.get("role") == "tenant" for l in leases)
        out["leases"] = {"text": text + ("" if tenant else " Ajoutez les baux pour leurs échéances."),
                         "suggested": True, "conflict": isinstance(leases, list) and not tenant}
    productions = profile.get("productions")
    notes = []
    animals, _ = _sum(balances, ("7012", "7014"), "credit")
    plants, _ = _sum(balances, ("7011",), "credit")
    if animals and (productions is None or not set(productions) & ANIMAL_PRODUCTIONS):
        notes.append(f"ventes d'animaux ou de produits animaux {_euros(animals)} sans production animale")
    if plants and (productions is None or not set(productions) & PLANT_PRODUCTIONS):
        notes.append(f"ventes de produits végétaux {_euros(plants)} sans production végétale")
    if notes:
        out["productions"] = {"text": f"Comptabilité{where} : " + " ; ".join(notes) + ".", "suggested": True,
                              "conflict": productions is not None}
    return out


def uses() -> dict:
    """Échéances qui dépendent de chaque question : {clé: [titres]} (conditions de la fiche ou de ses événements)."""
    from app.services import deadlines

    out: dict = {}
    for fiche in deadlines.fiches():
        keys: set = set()
        for conditions in [fiche.get("applies"), *(e.get("applies") for e in fiche.get("events", []))]:
            conditions = conditions or {}
            keys.update(conditions.get("flags") or [])
            if "production" in conditions:
                keys.add("productions")
        for key in keys:
            out.setdefault(key, []).append(f"{fiche['id']} {fiche['title']}")
    return out
