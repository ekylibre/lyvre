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
