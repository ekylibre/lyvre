"""Réglages de facturation (lot S1) : mentions légales du vendeur, coordonnées bancaires, conditions
de paiement, logo, modèle d'email d'envoi. Une ligne `billing_settings` par instance."""
from __future__ import annotations

from pathlib import Path

from app.extensions import db
from app.models import BillingSettings
from app.services import organization
from app.services.attachments import instance_dir
from app.services.sale_entry import SaleError

LOGO_MAX = 500 * 1024
LOGO_TYPES = {b"\x89PNG": ".png", b"\xff\xd8\xff": ".jpg"}
DEFAULT_SEND_SUBJECT = "{type} n° {numero} — {organisation}"
DEFAULT_SEND_BODY = """Bonjour,

Veuillez trouver ci-joint {article} {type_minuscule} n° {numero} du {date}, d'un montant de {montant}.
{echeance}
Bien cordialement,
{organisation}"""
DEFAULT_REMINDER_SUBJECT = "Relance : facture n° {numero} — {organisation}"
DEFAULT_REMINDER_BODY = """Bonjour,

Sauf erreur de notre part, notre facture n° {numero} du {date}, arrivée à échéance le {date_echeance}, reste impayée : {restant} restent dus.

Merci de procéder à son règlement, ou de nous indiquer s'il a déjà été effectué. La facture est jointe à ce message.

Bien cordialement,
{organisation}"""
DEFAULT_LATE_PENALTY = ("En cas de retard de paiement, pénalités au taux d'intérêt de la BCE majoré de 10 points.")
TEXT_FIELDS = {"legal_form": 100, "rcs": 100, "vat_number": 20, "iban": 34, "bic": 11, "send_subject": 255,
               "late_penalty_text": None, "discount_text": None, "footer": None, "send_body": None,
               "reminder_subject": 255, "reminder_body": None}


def get() -> BillingSettings:
    settings = db.session.query(BillingSettings).first()
    if settings is None:
        settings = BillingSettings(payment_terms_days=30, recovery_fee=True)
        db.session.add(settings)
        db.session.flush()
    return settings


def logo_file(settings: BillingSettings | None = None) -> Path | None:
    settings = settings or get()
    if not settings.logo_path:
        return None
    path = (instance_dir() / settings.logo_path).resolve()
    return path if path.is_relative_to(instance_dir().resolve()) and path.is_file() else None


def readiness(settings: BillingSettings | None = None, vat_liable: bool = False) -> list[dict]:
    """Mentions obligatoires du vendeur : présentes ou non (une facture ne s'émet pas sans elles)."""
    settings = settings or get()
    org = organization.get()
    rows = [
        {"key": "name", "label": "Dénomination (Configuration › Structure)", "ok": bool(org.name)},
        {"key": "address", "label": "Adresse (Configuration › Structure)", "ok": bool(org.address_line1 and org.postal_code and org.city)},
        {"key": "siren", "label": "SIREN (Configuration › Structure)", "ok": bool(org.siren)},
    ]
    if vat_liable:
        rows.append({"key": "vat_number", "label": "N° de TVA intracommunautaire (Facturation)", "ok": bool(settings.vat_number)})
    return rows


def payload(settings: BillingSettings | None = None) -> dict:
    settings = settings or get()
    return {
        **{key: getattr(settings, key) or "" for key in TEXT_FIELDS},
        "share_capital": "" if settings.share_capital_cents is None else f"{settings.share_capital_cents / 100:.2f}".replace(".", ","),
        "payment_terms_days": settings.payment_terms_days, "recovery_fee": settings.recovery_fee,
        "has_logo": logo_file(settings) is not None,
        "defaults": {"send_subject": DEFAULT_SEND_SUBJECT, "send_body": DEFAULT_SEND_BODY,
                     "reminder_subject": DEFAULT_REMINDER_SUBJECT, "reminder_body": DEFAULT_REMINDER_BODY,
                     "late_penalty_text": DEFAULT_LATE_PENALTY},
        "readiness": readiness(settings, vat_liable=True),
    }


def save(data: dict) -> BillingSettings:
    from app.services.sale_entry import parse_decimal

    settings = get()
    for key, size in TEXT_FIELDS.items():
        if key in data:
            value = str(data.get(key) or "").strip()
            setattr(settings, key, (value[:size] if size else value) or None)
    if settings.iban:
        settings.iban = settings.iban.replace(" ", "").upper()
        from stdnum import iban
        if not iban.is_valid(settings.iban):
            db.session.rollback()
            raise SaleError("IBAN invalide.", "iban")
    if settings.vat_number:
        settings.vat_number = settings.vat_number.replace(" ", "").upper()
    if "share_capital" in data:
        capital = parse_decimal(data.get("share_capital"), "Capital", "share_capital", minimum=0)
        settings.share_capital_cents = None if capital is None else int(capital * 100)
    if "payment_terms_days" in data:
        try:
            days = int(data.get("payment_terms_days") or 0)
        except (TypeError, ValueError):
            days = -1
        if not 0 <= days <= 120:
            db.session.rollback()
            raise SaleError("Délai de paiement : de 0 à 120 jours.", "payment_terms_days")
        settings.payment_terms_days = days
    if "recovery_fee" in data:
        settings.recovery_fee = bool(data.get("recovery_fee"))
    db.session.commit()
    return settings


def save_logo(file_storage) -> None:
    if file_storage is None or not file_storage.filename:
        raise SaleError("Aucun fichier.", "logo")
    body = file_storage.stream.read(LOGO_MAX + 1)
    if len(body) > LOGO_MAX:
        raise SaleError("Image trop volumineuse (500 Ko au plus).", "logo")
    suffix = next((ext for magic, ext in LOGO_TYPES.items() if body.startswith(magic)), None)
    if suffix is None:
        raise SaleError("Image PNG ou JPEG attendue.", "logo")
    folder = instance_dir() / "ventes"
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("logo.*"):
        old.unlink()
    (folder / f"logo{suffix}").write_bytes(body)
    get().logo_path = f"ventes/logo{suffix}"
    db.session.commit()


def delete_logo() -> None:
    settings = get()
    path = logo_file(settings)
    if path is not None:
        path.unlink()
    settings.logo_path = None
    db.session.commit()
