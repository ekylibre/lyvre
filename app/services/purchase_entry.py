"""Saisie d'une facture d'achat dans l'application (`source = 'manual'`).

Parcours : le fichier déposé est mis en attente (`attachments.stage`) et lu
(`invoice_reader`) ; `form_from_extraction` prérempli le formulaire (fournisseur
reconnu, champs à vérifier, lignes proposées) ; à l'enregistrement,
`validate_header` puis `create` créent la facture, rangent la pièce et la
comptabilisent si elle est complète (cycle du lot 2a). Une remise déduite après
le total d'un ticket (points fidélité) devient une ligne négative au compte de
rabais obtenus (6098, à défaut 609) : le TTC de la facture est le montant payé.

`send_to_qonto` dépose la pièce dans Qonto (instances où l'intégration est
disponible) avec la clé d'idempotence de la facture ; l'échec est mémorisé
(`qonto_upload_status = failed`) et l'envoi peut être relancé sans doublon. Quand
Qonto renvoie la facture à la synchronisation, la saisie l'emporte
(`purchase_sync`, champs vides seulement).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date

from app.extensions import db
from app.models import Account, BankAccount, Entity, Purchase, PurchaseLine
from app.services import (
    attachments, catalog, external_config, invoice_reader, organization, purchase_posting,
    purchase_sync, qonto_client,
)
from app.services.counterparties import name_key
from app.services.ledger import LedgerError

DISCOUNT_ACCOUNTS = ("6098", "609")
DISCOUNT_LABEL = "Remise fidélité"
# Champ de l'extraction → champ du formulaire.
FORM_NAMES = {
    "supplier_name": "supplier_name", "vat_number": "supplier_vat", "siret": "supplier_siret",
    "iban": "supplier_iban", "invoice_number": "invoice_number", "issue_date": "issue_date",
    "due_date": "due_date", "is_credit_note": "is_credit_note", "total": "total",
    "untaxed": "untaxed", "tax": "tax",
}


def fmt_cents(cents) -> str:
    return "" if cents is None else f"{cents / 100:.2f}".replace(".", ",")


@dataclass
class EntryForm:
    """Valeurs du formulaire (chaînes), champs à vérifier, lignes proposées."""
    values: dict = field(default_factory=dict)
    checks: set = field(default_factory=set)
    rows: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    source: str = "none"


# ------------------------------------------------------------------ lecture → formulaire

def own_ibans() -> set[str]:
    return {purchase_sync.normalize_iban(b.iban) for b in BankAccount.query if b.iban}


HINT_PURCHASES = 10  # factures du fournisseur consultées pour sa mémoire


def supplier_hints(entity: Entity) -> invoice_reader.SupplierHints | None:
    """Mémoire d'un fournisseur d'après ses dernières factures : taux de TVA, absence de TVA,
    forme des numéros. Aide la lecture d'une nouvelle facture (montants, n° parmi plusieurs)."""
    purchases = (Purchase.query.filter_by(entity_id=entity.id)
                 .order_by(Purchase.issue_date.desc(), Purchase.id.desc()).limit(HINT_PURCHASES).all())
    if not purchases:
        return None
    rates = {line.vat_rate_bp for p in purchases for line in p.lines
             if line.vat_rate_bp and (line.untaxed_cents or 0) > 0}
    return invoice_reader.SupplierHints(
        rates=frozenset(rates),
        tax_free=all(p.tax_cents == 0 for p in purchases),
        number_shapes=frozenset(invoice_reader.number_shape(p.invoice_number)
                                for p in purchases if p.invoice_number),
    )


def _hints_for(ext: invoice_reader.Extraction) -> invoice_reader.SupplierHints | None:
    entity = purchase_sync.find_supplier(None, ext.value("vat_number"), ext.value("siret"),
                                         ext.value("iban"), ext.value("supplier_name"))
    return supplier_hints(entity) if entity is not None else None


def read_staged(token: str) -> invoice_reader.Extraction:
    """Lecture de la pièce déposée ; l'organisation (IBAN, SIREN, nom) est écartée des champs du
    fournisseur, la mémoire du fournisseur reconnu affine la lecture."""
    path, meta = attachments.staged(token)
    org = organization.get()
    return invoice_reader.read(path, meta["mime"], ignore_ibans=own_ibans(),
                               ignore_sirens=[org.siren] if org.siren else (),
                               ignore_names=[org.name] if org.name else (), hints_for=_hints_for)


def discount_account() -> Account | None:
    for code in DISCOUNT_ACCOUNTS:
        account = Account.query.filter_by(code=code, is_header=False).first()
        if account is not None:
            return account
    return None


def line_rows(lines) -> list[dict]:
    """Lignes (`PurchaseLine`) → lignes du formulaire."""
    return [{
        "product_id": str(line.product_id or ""),
        "account_code": line.account.code if line.account else
        (db.session.get(Account, line.account_id).code if line.account_id else ""),
        "label": line.label or "",
        "untaxed": fmt_cents(line.untaxed_cents),
        "vat_rate": catalog.format_rate(line.vat_rate_bp).replace(" %", "")
        if line.vat_rate_bp is not None else "",
        "vat": fmt_cents(line.vat_cents),
        "project_id": str(line.project_id or ""),
        "analytic": line.analytic_target or "",
    } for line in lines]


def proposed_lines(entity, total, untaxed, taxes, discount=0) -> list[PurchaseLine]:
    """Lignes par défaut (produit du fournisseur, une par taux) et ligne de remise."""
    draft = Purchase(total_cents=total, untaxed_cents=untaxed)
    breakdown = sorted(((rate, vat) for rate, _, vat in taxes), key=lambda row: row[0] == 0)
    lines = purchase_sync.default_lines(draft, catalog.product_for(entity), breakdown)
    if discount:
        account = discount_account()
        lines.append(PurchaseLine(position=len(lines), account_id=account.id if account else None,
                                  label=DISCOUNT_LABEL, untaxed_cents=-discount, vat_rate_bp=0,
                                  vat_cents=0, total_cents=-discount))
    return lines


def form_from_extraction(ext: invoice_reader.Extraction) -> EntryForm:
    form = EntryForm(source=ext.source, warnings=list(ext.warnings))
    for name, form_name in FORM_NAMES.items():
        f = ext.fields.get(name)
        if f is None:
            continue
        value = f.value
        if isinstance(value, date):
            value = value.isoformat()
        elif name in ("total", "untaxed", "tax"):
            value = fmt_cents(value)
        form.values[form_name] = value
        if f.check:
            form.checks.add(form_name)

    entity = purchase_sync.find_supplier(None, ext.value("vat_number"), ext.value("siret"),
                                         ext.value("iban"), ext.value("supplier_name"))
    if entity is not None:
        form.values["entity_id"] = str(entity.id)
    elif ext.value("supplier_name"):
        form.values["entity_id"] = "new"
        form.values["new_name"] = ext.value("supplier_name")

    total, untaxed = ext.value("total"), ext.value("untaxed")
    discount = ext.value("discount") or 0
    if total:
        catalog.ensure_default_purchase_product()
        lines = proposed_lines(entity, total, untaxed, ext.taxes, discount)
        form.rows = line_rows(lines)
        if discount:
            form.values["total"] = fmt_cents(total - discount)
            if untaxed is not None:
                form.values["untaxed"] = fmt_cents(untaxed - discount)
            form.checks.update({"total", "untaxed"})
            form.warnings.append(f"Remise de {fmt_cents(discount)} € déduite après le total : "
                                 "ligne de rabais obtenu ajoutée, TTC = montant payé.")
    return form


# ------------------------------------------------------------------ validation

def _date(value, label, errors) -> date | None:
    if not (value or "").strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        errors.append(f"{label} invalide.")
        return None


def _cents(value, label, errors) -> int | None:
    try:
        return purchase_posting.parse_cents(value)
    except LedgerError:
        errors.append(f"{label} invalide : « {value} ».")
        return None


def validate_header(form) -> tuple[dict, list[str]]:
    """Champs d'en-tête nettoyés et erreurs. `entity_id` : id, « new » (créer) ou vide."""
    errors = []
    clean = {
        "supplier_name": (form.get("supplier_name") or "").strip()[:200] or None,
        "supplier_vat": purchase_sync.normalize_vat(form.get("supplier_vat")),
        "supplier_siret": purchase_sync.normalize_siret(form.get("supplier_siret")),
        "supplier_iban": purchase_sync.normalize_iban(form.get("supplier_iban")),
        "invoice_number": (form.get("invoice_number") or "").strip()[:100] or None,
        "issue_date": _date(form.get("issue_date"), "Date de facture", errors),
        "due_date": _date(form.get("due_date"), "Échéance", errors),
        "service_start": _date(form.get("service_start"), "Période du", errors),
        "service_end": _date(form.get("service_end"), "Période au", errors),
        "is_credit_note": bool(form.get("is_credit_note")),
        "total_cents": _cents(form.get("total"), "TTC", errors),
        "untaxed_cents": _cents(form.get("untaxed"), "HT", errors),
        "tax_cents": _cents(form.get("tax"), "TVA", errors),
    }
    if (form.get("supplier_siret") or "").strip() and clean["supplier_siret"] is None:
        errors.append("Le SIRET doit comporter 14 chiffres.")
    if bool(clean["service_start"]) != bool(clean["service_end"]):
        errors.append("Période : indiquez le début et la fin, ou aucune.")
    elif clean["service_start"] and clean["service_end"] < clean["service_start"]:
        errors.append("Période : la fin suit le début.")
    if clean["issue_date"] is None and not any("Date de facture" in e for e in errors):
        errors.append("La date de facture est obligatoire.")
    if clean["total_cents"] is not None and clean["total_cents"] <= 0:
        errors.append("Le TTC doit être positif (cochez « Avoir » pour un avoir).")
    elif clean["total_cents"] is None and not any(e.startswith("TTC") for e in errors):
        errors.append("Le montant TTC est obligatoire.")

    choice = (form.get("entity_id") or "").strip()
    clean["entity"], clean["new_name"], clean["new_entity"] = None, None, {}
    if choice == "new":
        clean["new_name"] = (form.get("new_name") or "").strip()[:200] or None
        if clean["new_name"] is None:
            errors.append("Indiquez le nom du fournisseur à créer.")
    elif choice:
        clean["entity"] = db.session.get(Entity, int(choice)) if choice.isdigit() else None
        if clean["entity"] is None:
            errors.append("Fournisseur introuvable.")
    return clean, errors


def duplicates(entity_id, number, issue_date, total, supplier_name=None, exclude_id=None):
    """Factures déjà saisies ou reçues : même fournisseur et même n°, sinon même date et TTC."""
    query = Purchase.query.filter(Purchase.is_hidden.is_(False))
    if exclude_id is not None:
        query = query.filter(Purchase.id != exclude_id)
    if entity_id is not None:
        query = query.filter(Purchase.entity_id == entity_id)
    elif supplier_name:
        key = name_key(supplier_name)
        candidates = [p for p in query.filter(Purchase.entity_id.is_(None))
                      if name_key(p.supplier_name) == key]
        return [p for p in candidates if _same(p, number, issue_date, total)]
    else:
        return []
    return [p for p in query.all() if _same(p, number, issue_date, total)]


def _same(p: Purchase, number, issue_date, total) -> bool:
    if number:
        return (p.invoice_number or "").strip().casefold() == number.strip().casefold()
    return p.issue_date == issue_date and p.total_cents == total


# ------------------------------------------------------------------ enregistrement

# Fiche Sirene du fournisseur à créer (lot G4) : appliquée seulement à la création du tiers.
NEW_ENTITY_FIELDS = {"siren": 9, "address_line1": 200, "address_line2": 200, "postal_code": 10, "city": 100,
                     "country": 60, "naf_code": 8, "naf_nomenclature": 12, "person_kind": 12}


def clean_new_entity(data) -> dict:
    """Champs reconnus d'une proposition Sirene (le reste est ignoré)."""
    if not isinstance(data, dict):
        return {}
    out = {key: str(data[key]).strip()[:size] for key, size in NEW_ENTITY_FIELDS.items()
           if data.get(key) not in (None, "")}
    if out.get("person_kind") not in (None, "individual", "company"):
        out.pop("person_kind")
    if "naf_code" in out:
        out["naf_code"] = out["naf_code"].replace(".", "").upper()
    if "siren" in out and not (out["siren"].isdigit() and len(out["siren"]) == 9):
        out.pop("siren")
    return out


def chosen_supplier(clean) -> Entity | None:
    """Fournisseur choisi, ou homonyme existant du fournisseur à créer (sans rien créer)."""
    if clean["entity"] is not None or not clean["new_name"]:
        return clean["entity"]
    key = name_key(clean["new_name"])
    return next((e for e in Entity.query.order_by(Entity.id) if name_key(e.name) == key), None)


def _supplier(clean) -> Entity | None:
    """Fournisseur choisi, ou créé (un homonyme existant est repris) ; identifiants complétés."""
    entity = chosen_supplier(clean)
    if entity is None and clean["new_name"]:
        entity = Entity(name=clean["new_name"], entity_type="FOURNISSEUR")
        for key, value in clean.get("new_entity", {}).items():  # jamais sur un tiers existant (B19)
            setattr(entity, key, value)
        db.session.add(entity)
    if entity is not None:
        entity.vat_number = entity.vat_number or clean["supplier_vat"]
        entity.siret = entity.siret or clean["supplier_siret"]
        entity.iban = entity.iban or clean["supplier_iban"]
    return entity


HEADER_FIELDS = ("supplier_vat", "supplier_siret", "supplier_iban", "invoice_number", "issue_date",
                 "due_date", "service_start", "service_end", "is_credit_note", "total_cents", "untaxed_cents", "tax_cents")


def _apply(p: Purchase, clean) -> None:
    for name in HEADER_FIELDS:
        setattr(p, name, clean[name])
    entity = _supplier(clean)
    p.entity = entity
    p.supplier_name = clean["supplier_name"] or (entity.name if entity else None)


def _lines(p: Purchase, rows) -> list[PurchaseLine]:
    lines = purchase_posting.build_lines(rows or [])
    if lines:
        return lines
    return purchase_sync.default_lines(p, catalog.product_for(p.entity), [])


def create(clean, rows, token=None, bank_transaction=None) -> tuple[Purchase, dict]:
    """Crée la facture, range la pièce, comptabilise si elle est prête. LedgerError sur les lignes.
    `bank_transaction` : transaction Qonto dont la facture vient (justificatif), reliée avant la
    comptabilisation pour que le règlement porte sur elle."""
    p = Purchase(source="manual", lines_edited=True, currency="EUR",
                 idempotency_key=str(uuid.uuid4()))
    db.session.add(p)
    with db.session.no_autoflush:
        _apply(p, clean)
        p.lines = _lines(p, rows)
        catalog.remember_supplier_product(p.entity, p.lines)
    db.session.flush()
    if token:
        attachments.store(p, token)
    if bank_transaction is not None:
        from app.services import transaction_invoice
        transaction_invoice.link(p, bank_transaction)
    db.session.commit()
    return p, purchase_posting.post_ready([p])


def update(p: Purchase, clean, token=None) -> dict:
    """Modifie l'en-tête d'une facture saisie non comptabilisée (pièce remplaçable si non envoyée)."""
    if p.source != "manual":
        raise LedgerError("Seule une facture saisie dans l'application se modifie ici.")
    if p.journal_entry_id is not None:
        raise LedgerError("Facture comptabilisée : annulez la comptabilisation pour la modifier.")
    if token and p.qonto_upload_status == "sent":
        raise LedgerError("Pièce déjà envoyée à Qonto : elle ne peut plus être remplacée.")
    _apply(p, clean)
    if token:
        attachments.store(p, token)
    db.session.commit()
    return purchase_posting.post_ready([p])


def header_values(p: Purchase) -> dict:
    """Valeurs du formulaire d'en-tête pour une facture existante."""
    return {
        "entity_id": str(p.entity_id or ""), "supplier_name": p.supplier_name or "",
        "supplier_vat": p.supplier_vat or "", "supplier_siret": p.supplier_siret or "",
        "supplier_iban": p.supplier_iban or "", "invoice_number": p.invoice_number or "",
        "issue_date": p.issue_date.isoformat() if p.issue_date else "",
        "due_date": p.due_date.isoformat() if p.due_date else "",
        "service_start": p.service_start.isoformat() if p.service_start else "",
        "service_end": p.service_end.isoformat() if p.service_end else "",
        "is_credit_note": p.is_credit_note, "total": fmt_cents(p.total_cents),
        "untaxed": fmt_cents(p.untaxed_cents), "tax": fmt_cents(p.tax_cents),
    }


# ------------------------------------------------------------------ envoi à Qonto

def qonto_upload_available() -> bool:
    """L'instance utilise Qonto : intégration activée et configurée."""
    return external_config.scope_available("qonto", "purchases")


def can_send_to_qonto(p: Purchase) -> bool:
    return (p.source == "manual" and bool(p.attachment_path) and p.qonto_upload_status != "sent"
            and p.qonto_id is None)


def send_to_qonto(p: Purchase, client=None) -> bool:
    """Dépose la pièce de la facture dans Qonto ; mémorise l'identifiant ou l'échec (commit).

    Ne lève jamais d'exception : le message d'échec est dans `qonto_upload_error`.
    """
    if not can_send_to_qonto(p):
        return p.qonto_upload_status == "sent"
    try:
        path = attachments.path_of(p)
        if path is None:
            raise qonto_client.QontoError("Pièce introuvable dans le dossier de l'instance.")
        if not p.idempotency_key:
            p.idempotency_key = str(uuid.uuid4())
            db.session.commit()  # clé gardée même si l'envoi échoue : le renvoi la réutilise
        client = client or qonto_client.from_app_config()
        invoice = client.create_supplier_invoice(path.read_bytes(), p.attachment_name or path.name,
                                                 p.attachment_mime or "application/pdf",
                                                 p.idempotency_key)
    except (qonto_client.QontoError, OSError, ValueError) as exc:
        db.session.rollback()
        p.qonto_upload_status, p.qonto_upload_error = "failed", str(exc)[:1000]
        db.session.commit()
        return False
    except Exception as exc:  # noqa: BLE001 — réseau (requests) : la vue ne doit pas échouer
        db.session.rollback()
        p.qonto_upload_status = "failed"
        p.qonto_upload_error = f"Envoi impossible : {exc}"[:1000]
        db.session.commit()
        return False
    p.qonto_id = invoice["id"]
    p.qonto_status = (invoice.get("status") or "")[:20] or None
    p.qonto_upload_status, p.qonto_upload_error = "sent", None
    db.session.commit()
    return True
