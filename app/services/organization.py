"""Identité de la structure (table `organization`, une ligne par base d'instance).

La ligne est créée à la première lecture, nommée d'après l'instance. SIREN contrôlé par la clé
de Luhn (exception : La Poste, dont les établissements ont un SIREN 356000000 hors clé), RNA au
format W + 9 chiffres.
"""
import re

from flask import g

from app.extensions import db
from app.models import Organization

FIELDS = ("name", "siren", "rna", "address_line1", "address_line2", "postal_code", "city", "country", "purpose",
          "signatory_name", "signatory_title", "legal_form", "rcs_city")
MAX_LENGTHS = {"name": 200, "siren": 9, "rna": 10, "address_line1": 200, "address_line2": 200, "postal_code": 10,
               "city": 100, "country": 60, "signatory_name": 200, "signatory_title": 100, "legal_form": 100,
               "rcs_city": 100}
LA_POSTE_SIREN = "356000000"


def get() -> Organization:
    """Identité de la structure, créée au besoin avec le nom de l'instance courante."""
    org = db.session.query(Organization).order_by(Organization.id).first()
    if org is None:
        instance = getattr(g, "current_instance", None)
        org = Organization(name=instance.label if instance is not None else "Structure", country="France")
        db.session.add(org)
        db.session.commit()
    return org


def luhn_valid(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def normalize_siren(value: str) -> str:
    return re.sub(r"[\s.]", "", value or "")


def validate(data: dict) -> tuple[dict, dict]:
    """Valeurs nettoyées et erreurs par champ (dictionnaires vides si tout est bon)."""
    clean, errors = {}, {}
    for key in FIELDS:
        if key not in data:
            continue
        value = str(data.get(key) or "").strip()
        if key in MAX_LENGTHS and len(value) > MAX_LENGTHS[key] and key != "siren":
            errors[key] = f"{MAX_LENGTHS[key]} caractères au plus."
        clean[key] = value or None
    if "name" in clean and not clean["name"]:
        errors["name"] = "La raison sociale est obligatoire."
    if clean.get("siren"):
        siren = normalize_siren(clean["siren"])
        if not re.fullmatch(r"\d{9}", siren):
            errors["siren"] = "Le SIREN compte 9 chiffres."
        elif siren != LA_POSTE_SIREN and not luhn_valid(siren):
            errors["siren"] = "SIREN invalide (clé de contrôle)."
        clean["siren"] = siren
    if clean.get("rna"):
        rna = clean["rna"].upper().replace(" ", "")
        if not re.fullmatch(r"W\d{9}", rna):
            errors["rna"] = "Le numéro RNA s'écrit W suivi de 9 chiffres."
        clean["rna"] = rna
    country = (clean.get("country") or "France") if "country" in clean else None
    if clean.get("postal_code") and (country or "France").lower() == "france" \
            and not re.fullmatch(r"\d{5}", clean["postal_code"]):
        errors["postal_code"] = "Code postal français : 5 chiffres."
    if "country" in clean and not clean["country"]:
        clean["country"] = "France"
    if "associate_interest_rate" in data:
        from app.services.associates import AssociateError, parse_rate
        try:
            clean["associate_interest_rate_bp"] = parse_rate(data.get("associate_interest_rate")) or 0
        except AssociateError as exc:
            errors["associate_interest_rate"] = str(exc)
    return clean, errors


def update(data: dict) -> tuple[Organization, dict]:
    clean, errors = validate(data)
    org = get()
    if errors:
        return org, errors
    for key, value in clean.items():
        setattr(org, key, value)
    db.session.commit()
    return org, {}
