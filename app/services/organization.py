"""Identité de la structure (table `organization`, une ligne par base d'instance).

La ligne est créée à la première lecture, nommée d'après l'instance. SIREN contrôlé par la clé
de Luhn (exception : La Poste, dont les établissements ont un SIREN 356000000 hors clé), RNA au
format W + 9 chiffres.
"""
import re
from datetime import date

from flask import g

from app.extensions import db
from app.models import Organization

FIELDS = ("name", "siren", "rna", "address_line1", "address_line2", "postal_code", "city", "country", "purpose",
          "signatory_name", "signatory_title", "legal_form", "rcs_city", "vat_number", "naf_code", "naf_nomenclature")
MAX_LENGTHS = {"name": 200, "siren": 9, "rna": 10, "address_line1": 200, "address_line2": 200, "postal_code": 10,
               "city": 100, "country": 60, "signatory_name": 200, "signatory_title": 100, "legal_form": 100,
               "rcs_city": 100, "vat_number": 20, "naf_code": 8, "naf_nomenclature": 12}
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
    if clean.get("vat_number"):
        vat = re.sub(r"[\s.]", "", clean["vat_number"]).upper()
        if not re.fullmatch(r"[A-Z]{2}[0-9A-Z]{2,13}", vat):
            errors["vat_number"] = "N° de TVA : code pays et numéro (FR + 11 caractères)."
        elif vat.startswith("FR"):
            from stdnum.fr import tva
            if not tva.is_valid(vat):
                errors["vat_number"] = "N° de TVA français invalide (clé de contrôle)."
        clean["vat_number"] = vat
    if clean.get("naf_code"):
        naf = clean["naf_code"].replace(".", "").replace(" ", "").upper()
        if not re.fullmatch(r"\d{4}[A-Z]", naf):
            errors["naf_code"] = "Code NAF : 4 chiffres et une lettre (68.20B)."
        clean["naf_code"] = naf
    if "share_capital" in data:
        from app.services.sale_entry import SaleError, parse_decimal
        try:
            capital = parse_decimal(data.get("share_capital"), "Capital", "share_capital", minimum=0)
            clean["share_capital_cents"] = None if capital is None else int(capital * 100)
        except SaleError as exc:
            errors["share_capital"] = str(exc)
    country = (clean.get("country") or "France") if "country" in clean else None
    if clean.get("postal_code") and (country or "France").lower() == "france" \
            and not re.fullmatch(r"\d{5}", clean["postal_code"]):
        errors["postal_code"] = "Code postal français : 5 chiffres."
    if "country" in clean and not clean["country"]:
        clean["country"] = "France"
    if "jei_since" in data:
        text = str(data.get("jei_since") or "").strip()
        try:
            clean["jei_since"] = date.fromisoformat(text) if text else None
        except ValueError:
            errors["jei_since"] = "Date attendue (AAAA-MM-JJ)."
    if "vat_due_day" in data:  # lot T3 : échéance de la CA3 fixée par le SIE (15 à 24)
        text = str(data.get("vat_due_day") or "").strip()
        if not text:
            clean["vat_due_day"] = None
        elif text.isdigit() and 15 <= int(text) <= 24:
            clean["vat_due_day"] = int(text)
        else:
            errors["vat_due_day"] = "Jour du mois entre 15 et 24 (voir votre espace professionnel)."
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


def format_siren(siren: str | None) -> str:
    """« 840 968 499 » (groupes de trois chiffres)."""
    siren = siren or ""
    return f"{siren[:3]} {siren[3:6]} {siren[6:]}" if len(siren) == 9 else siren


def rcs_mention(org: Organization | None = None) -> str:
    """Mention d'immatriculation des factures et des baux : « 840 968 499 RCS Saintes », sinon
    « SIREN 840968499 » (structure non immatriculée au RCS), sinon vide."""
    org = org or get()
    if org.siren and org.rcs_city:
        return f"{format_siren(org.siren)} RCS {org.rcs_city}"
    return f"SIREN {org.siren}" if org.siren else ""


def share_capital_text(org: Organization) -> str:
    """Capital saisi tel qu'affiché dans le formulaire (« 1500,00 »), vide s'il n'est pas renseigné."""
    return "" if org.share_capital_cents is None else f"{org.share_capital_cents / 100:.2f}".replace(".", ",")
