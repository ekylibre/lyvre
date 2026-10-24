"""Baux simples, dépôt de garantie, quittances et reçus de loyer (lot S5, décisions V8 et V16).

Un bail porte une facture récurrente de loyer (avis d'échéance) : ligne « Loyer {periode} — lot »
au compte de loyer, ligne « Provisions sur charges {periode} » au compte de charges refacturées
(comptes à valider avec l'expert-comptable : 706 / 708 par défaut). Le dépôt de garantie encaissé
passe au compte 165 (dépôts et cautionnements reçus) : banque ou caisse au débit.

Quittance : quand la facture de loyer d'une période est entièrement payée ; reçu du montant versé
si elle ne l'est qu'en partie. Le PDF est conservé (`ventes/quittances/`), envoyé à la demande.
"""
from __future__ import annotations

import string
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from flask import render_template

from app.extensions import db
from app.models import Account, BankAccount, Entity, Journal, Lease, LeaseItem, Recurrence, RentReceipt, Sale
from app.services import organization, recurrence, sale_entry
from app.services.attachments import instance_dir
from app.services.ledger import LedgerError, post_entry
from app.services.sale_entry import SaleError, parse_date, parse_decimal
from app.utils.money import euros, euros_in_words

DEPOSIT_ACCOUNT = ("165", "Dépôts et cautionnements reçus")
RENT_ACCOUNTS = ("706", "7083", "708")
CHARGES_ACCOUNTS = ("708", "7084", "706")
FIELDS = ("unit_label", "address_line1", "address_line2", "postal_code", "city", "notes", "premises_label",
          "signed_on_place")
KINDS = {"derogatory": "Bail dérogatoire commercial", "commercial": "Bail commercial 3-6-9",
         "residential": "Bail d'habitation", "rural": "Bail rural / prêt à usage"}
NATURES = {"building": "Bâtiment", "land": "Sol", "flat": "Forfait"}
UNITS = {"m2": "€ / m² / an", "ha": "€ / ha / an", "flat": "€ / an"}
DEFAULT_UNITS = {"building": "m2", "land": "ha", "flat": "flat"}
INDEXES = {"ILC": "Indice des loyers commerciaux (ILC)", "ILAT": "Indice des loyers des activités tertiaires (ILAT)",
           "IRL": "Indice de référence des loyers (IRL)", "FERMAGES": "Indice national des fermages"}
PER_YEAR = {"monthly": 12, "quarterly": 4, "yearly": 1}


def _account(code: str | None, defaults, field: str) -> Account | None:
    if code:
        account = Account.query.filter_by(code=code).first()
        if account is None or account.is_header or not code.startswith("7"):
            raise SaleError(f"Compte « {code} » invalide (compte de produit 7…).", field)
        return account
    for candidate in defaults:
        account = Account.query.filter_by(code=candidate, is_header=False).first()
        if account is not None:
            return account
    return sale_entry.default_sale_account()


def _cents(value, label, field, required=False) -> int:
    amount = parse_decimal(value, label, field, minimum=0)
    if amount is None:
        if required:
            raise SaleError(f"{label} obligatoire.", field)
        return 0
    return int(amount * 100)


# ------------------------------------------------------------------ bail (termes)

def _apply_terms(lease: Lease, data: dict) -> None:
    """Termes du bail (étape 1 de l'assistant) : locataire, désignation, adresse, dates, dépôt, type,
    lieu, révision."""
    for key in FIELDS:
        if key in data:
            value = str(data.get(key) or "").strip()
            setattr(lease, key, value or None)
    if not lease.unit_label:
        raise SaleError("Désignation du bail obligatoire.", "unit_label")
    entity_id = data.get("entity_id")
    if entity_id or data.get("new_client_name"):
        lease.entity = sale_entry._client(data)
    if lease.entity is None:
        raise SaleError("Choisissez le locataire.", "entity_id")
    lease.start_date = parse_date(data.get("start_date"), "Date d'effet", "start_date") or lease.start_date
    if lease.start_date is None:
        raise SaleError("Date d'effet obligatoire.", "start_date")
    if "end_date" in data:
        lease.end_date = parse_date(data.get("end_date"), "Fin", "end_date")
    if lease.end_date and lease.end_date < lease.start_date:
        raise SaleError("La fin précède la date d'effet.", "end_date")
    if "deposit" in data:
        lease.deposit_cents = _cents(data.get("deposit"), "Dépôt de garantie", "deposit")
    if "kind" in data:
        kind = str(data.get("kind") or "").strip() or None
        if kind is not None and kind not in KINDS:
            raise SaleError("Type de bail inconnu.", "kind")
        lease.kind = kind
    if "index_code" in data:
        code = str(data.get("index_code") or "").strip() or None
        if code is not None and code not in INDEXES:
            raise SaleError("Indice de révision inconnu.", "index_code")
        lease.index_code = code
    if "index_reference_period" in data:
        lease.index_reference_period = str(data.get("index_reference_period") or "").strip()[:10] or None
    if "index_reference_value" in data:
        lease.index_reference_value = parse_decimal(data.get("index_reference_value"), "Valeur de l'indice",
                                                    "index_reference_value", minimum=0)
    if "revision_months" in data:
        months = str(data.get("revision_months") or "").strip()
        if months and months not in ("12", "36"):
            raise SaleError("Révision annuelle (12 mois) ou triennale (36 mois).", "revision_months")
        lease.revision_months = int(months) if months else None
    if "revise_deposit" in data:
        lease.revise_deposit = bool(data.get("revise_deposit"))
    if lease.index_code is None:
        lease.revision_months = lease.next_revision_date = None
    elif lease.revision_months is None:
        lease.revision_months = 12


def create_draft(data: dict) -> Lease:
    """Étape 1 de l'assistant : bail en brouillon, sans loyer ni facture récurrente (commit)."""
    lease = Lease(status="draft", due_day=1, rent_cents=0, charges_cents=0, deposit_cents=0)
    try:
        _apply_terms(lease, data)
        db.session.add(lease)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return lease


def update(lease: Lease, data: dict) -> Lease:
    """Termes du bail ; bail validé : sa facture récurrente suit (libellés, dates, état)."""
    try:
        if "active" in data:
            lease.active = bool(data.get("active"))
        _apply_terms(lease, data)
        if lease.status == "active":
            _sync_recurrence(lease, {"active": lease.active} if "active" in data else {})
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return lease


def delete_draft(lease: Lease) -> None:
    if lease.status != "draft":
        raise SaleError("Seul un bail en brouillon se supprime.", status=409)
    db.session.delete(lease)
    db.session.commit()


# ------------------------------------------------------------------ lignes (biens loués)

def item_title(item: LeaseItem) -> str:
    return f"{item.letter} {item.label}" if item.letter else item.label


def hectares(area_m2: int) -> Decimal:
    """Surface en hectares arrondie à l'are (0,01 ha), comme dans les baux : 4 940 m² → 0,49 ha."""
    return (Decimal(area_m2) / 10000).quantize(Decimal("0.01"), ROUND_HALF_UP)


def annual_of(item: LeaseItem) -> int:
    """Montant annuel : surface × prix au m², hectares (à l'are) × prix à l'hectare, ou forfait."""
    if item.billing_unit == "m2":
        return item.area_m2 * item.unit_price_cents
    if item.billing_unit == "ha":
        return _round(hectares(item.area_m2) * item.unit_price_cents)
    return item.unit_price_cents


def _next_letter(lease: Lease) -> str:
    used = {i.letter for i in lease.items}
    return next((c for c in string.ascii_uppercase if c not in used), "")


def _int(value, label, field) -> int:
    amount = parse_decimal(value, label, field, minimum=0)
    return int(amount) if amount is not None else 0


def _refs(value) -> list[str]:
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, list):
        return []
    return [str(v).strip()[:30] for v in value if str(v).strip()][:50]


def save_item(lease: Lease, data: dict, item: LeaseItem | None = None) -> LeaseItem:
    """Ajoute ou modifie une ligne (commit) ; bail validé : facture récurrente mise à jour."""
    try:
        if item is None:
            item = LeaseItem(position=max((i.position for i in lease.items), default=-1) + 1)
            lease.items.append(item)
            if "letter" not in data:
                item.letter = _next_letter(lease) or None
        if "letter" in data:
            letter = str(data.get("letter") or "").strip().upper()[:3] or None
            if letter and any(i.letter == letter for i in lease.items if i is not item):
                raise SaleError(f"La lettre {letter} est déjà utilisée dans ce bail.", "letter")
            item.letter = letter
        if "label" in data:
            item.label = str(data.get("label") or "").strip()[:200]
        if not item.label:
            raise SaleError("Désignation de la ligne obligatoire.", "label")
        if "nature" in data:
            if data.get("nature") not in NATURES:
                raise SaleError("Nature : bâtiment, sol ou forfait.", "nature")
            item.nature = data["nature"]
        item.nature = item.nature or "flat"
        if "area_m2" in data:
            item.area_m2 = _int(data.get("area_m2"), "Surface", "area_m2")
        if "built_m2" in data:
            item.built_m2 = _int(data.get("built_m2"), "Dont surface bâtie", "built_m2")
        item.area_m2, item.built_m2 = item.area_m2 or 0, item.built_m2 or 0
        if item.nature == "building" and "built_m2" not in data and not item.built_m2:
            item.built_m2 = item.area_m2  # bâtiment : la surface louée est bâtie, sauf indication contraire
        if "billing_unit" in data:
            if data.get("billing_unit") not in UNITS:
                raise SaleError("Unité : m², hectare ou forfait.", "billing_unit")
            item.billing_unit = data["billing_unit"]
        elif item.billing_unit is None or item.id is None:
            item.billing_unit = DEFAULT_UNITS[item.nature]
        if "unit_price" in data:
            item.unit_price_cents = _cents(data.get("unit_price"), "Prix annuel", "unit_price")
        item.unit_price_cents = item.unit_price_cents or 0
        if "cadastral_refs" in data:
            item.cadastral_refs = _refs(data.get("cadastral_refs")) or None
        if "partial" in data:
            item.partial = bool(data.get("partial"))
        item.annual_cents = annual_of(item)
        if lease.status == "active":
            _sync_recurrence(lease)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return item


def delete_item(item: LeaseItem) -> None:
    lease = item.lease
    try:
        lease.items.remove(item)
        if lease.status == "active":
            if not lease.items:
                raise SaleError("Un bail validé garde au moins une ligne.", status=409)
            _sync_recurrence(lease)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


# ------------------------------------------------------------------ loyer et facturation

def annual_total(lease: Lease) -> int:
    return sum(i.annual_cents for i in lease.items)


def period_amounts(lease: Lease, frequency: str) -> list[tuple[LeaseItem, int]]:
    """Montant d'échéance de chaque ligne facturée (annuel ÷ échéances par an) ; l'écart d'arrondi
    va sur la dernière ligne, pour que le total soit l'annuel divisé et arrondi."""
    per_year = PER_YEAR[frequency]
    billed = [i for i in lease.items if i.annual_cents]
    if not billed:
        return []
    total = _round(Decimal(annual_total(lease)) / per_year)
    amounts = [_round(Decimal(i.annual_cents) / per_year) for i in billed]
    amounts[-1] += total - sum(amounts)
    return list(zip(billed, amounts))


def _round(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), ROUND_HALF_UP))


def _vat_rate(lease: Lease) -> str:
    """Taux de TVA de la facture récurrente actuelle (« 0 » sans facture)."""
    template = lease.recurrence.template if lease.recurrence else None
    line = template.lines[0] if template is not None and template.lines else None
    return str(Decimal(line.vat_rate_bp) / 100) if line is not None and line.vat_rate_bp is not None else "0"


def _template_lines(lease: Lease, frequency: str, vat_rate: str) -> list[dict]:
    rent_account = lease.rent_account.code if lease.rent_account else ""
    lines = [{"label": f"Loyer {{periode}} — {item_title(item)}"[:300], "unit_price": f"{amount / 100:.2f}",
              "vat_rate": vat_rate, "account_code": rent_account}
             for item, amount in period_amounts(lease, frequency)]
    if lease.charges_cents:
        lines.append({"label": "Provisions sur charges {periode}", "unit_price": f"{lease.charges_cents / 100:.2f}",
                      "vat_rate": vat_rate, "account_code": lease.charges_account.code if lease.charges_account else ""})
    return lines


def _apply_billing(lease: Lease, data: dict) -> None:
    """Facturation (étape 3) : charges, échéance, comptes."""
    if "charges" in data:
        lease.charges_cents = _cents(data.get("charges"), "Provisions sur charges", "charges")
    if "due_day" in data:
        lease.due_day = int(data.get("due_day") or 1)
    lease.rent_account = _account(data.get("rent_account_code") or (lease.rent_account.code if lease.rent_account else None),
                                  RENT_ACCOUNTS, "rent_account_code")
    lease.charges_account = _account(data.get("charges_account_code") or (lease.charges_account.code if lease.charges_account else None),
                                     CHARGES_ACCOUNTS, "charges_account_code")


def _sync_recurrence(lease: Lease, data: dict | None = None) -> None:
    """Crée ou met à jour la facture récurrente du bail : une ligne par ligne de bail facturée, plus
    la provision sur charges ; `rent_cents` = loyer d'une échéance (sans commit)."""
    data = data or {}
    rec = lease.recurrence
    frequency = data.get("frequency") or (rec.frequency if rec else "monthly")
    if frequency not in PER_YEAR:
        raise SaleError("Périodicité inconnue.", "frequency")
    if not period_amounts(lease, frequency):
        raise SaleError("Saisissez le prix d'au moins une ligne : le loyer annuel est nul.", "items")
    vat_rate = str(data["vat_rate"]) if data.get("vat_rate") not in (None, "") else _vat_rate(lease)
    payload = {"label": f"Loyer — {lease.unit_label} — {lease.entity.name}"[:200], "entity_id": lease.entity.id,
               "start_date": lease.start_date.isoformat(), "end_date": lease.end_date.isoformat() if lease.end_date else None,
               "frequency": frequency, "due_day": lease.due_day, "operation_type": "services",
               "in_advance": data.get("in_advance", rec.in_advance if rec else True),
               "qonto_emit": data.get("qonto_emit", rec.qonto_emit if rec else False),
               "active": lease.active, "lines": _template_lines(lease, frequency, vat_rate)}
    created = rec is None
    if created:
        rec = Recurrence(label=payload["label"], frequency=frequency, due_day=lease.due_day)
    rec.label = payload["label"]
    with db.session.no_autoflush:
        recurrence._template(rec, payload)
        recurrence._schedule(rec, payload)
    if created:
        db.session.add(rec)
        lease.recurrence = rec
    db.session.flush()
    lease.rent_cents = sum(amount for _item, amount in period_amounts(lease, frequency))


def activate(lease: Lease, data: dict) -> Lease:
    """Étape 3 « Valider » : facturation et facture récurrente ; brouillon → bail validé (commit). Sur
    un bail déjà validé : enregistre la facturation."""
    try:
        if not lease.items:
            raise SaleError("Ajoutez au moins un bien loué.", "items")
        _apply_billing(lease, data)
        _sync_recurrence(lease, data)
        if lease.status == "draft" and lease.index_code and lease.revision_months:
            lease.next_revision_date = recurrence.add_months(lease.start_date, lease.revision_months, lease.start_date.day)
        lease.status = "active"
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return lease


def create(data: dict) -> Lease:
    """Bail en une fois (loyer d'échéance unique, forme d'avant l'assistant) : une ligne forfaitaire."""
    rent = _cents(data.get("rent"), "Loyer hors charges", "rent", required=True)
    lease = create_draft(data)
    frequency = data.get("frequency") or "monthly"
    if frequency not in PER_YEAR:
        raise SaleError("Périodicité inconnue.", "frequency")
    try:
        lease.items.append(LeaseItem(position=0, label=lease.unit_label, nature="flat", billing_unit="flat",
                                     unit_price_cents=rent * PER_YEAR[frequency],
                                     annual_cents=rent * PER_YEAR[frequency]))
        db.session.flush()
    except Exception:
        db.session.rollback()
        raise
    try:
        return activate(lease, data)
    except Exception:
        db.session.delete(lease)
        db.session.commit()
        raise


# ------------------------------------------------------------------ dépôt de garantie

def deposit(lease: Lease, paid_on: date, ba: BankAccount) -> None:
    """Encaissement du dépôt de garantie : banque (ou caisse) au débit, 165 au crédit."""
    if lease.status != "active":
        raise SaleError("Validez le bail avant d'encaisser le dépôt de garantie.", status=409)
    if lease.deposit_entry_id:
        raise SaleError("Dépôt de garantie déjà encaissé.", status=409)
    if not lease.deposit_cents:
        raise SaleError("Montant du dépôt de garantie non renseigné sur le bail.", "deposit")
    fy = sale_entry.fiscal_year_for(paid_on)
    if fy is None:
        raise SaleError(f"Aucun exercice ne couvre le {paid_on:%d/%m/%Y}.", status=409)
    code, label = DEPOSIT_ACCOUNT
    account = Account.query.filter_by(code=code, is_header=False).first()
    if account is None:
        account = Account(code=code, label=label, account_type="PASSIF")
        db.session.add(account)
        db.session.flush()
    jcode, jlabel = ("CA", "Caisse") if ba.kind == "cash" else ("BQ", "Banque")
    journal = Journal.query.filter_by(code=jcode).first() or Journal(code=jcode, label=jlabel)
    db.session.add(journal)
    db.session.flush()
    text = f"Dépôt de garantie — {lease.unit_label} — {lease.entity.name}"[:255]
    try:
        entry = post_entry(fy.id, journal.id, paid_on, text, [
            {"account_id": ba.account_id, "label": text, "debit_cents": lease.deposit_cents, "credit_cents": 0},
            {"account_id": account.id, "label": text, "debit_cents": 0, "credit_cents": lease.deposit_cents},
        ], source="LEASE_DEPOSIT", source_ref=f"LEASE:{lease.id}", commit=False)
    except LedgerError as exc:
        db.session.rollback()
        raise SaleError(str(exc), status=409) from None
    lease.deposit_entry_id = entry.id
    db.session.commit()


# ------------------------------------------------------------------ quittances

def split(sale: Sale, lease: Lease) -> tuple[int, int]:
    """(loyer, charges) TTC de la facture : lignes au compte de charges du bail = charges."""
    charges = sum(l.total_cents for l in sale.lines if lease.charges_account_id and l.account_id == lease.charges_account_id)
    return sale.total_cents - charges, charges


def receipt(sale: Sale) -> RentReceipt:
    """Quittance (période soldée) ou reçu (paiement partiel) de la facture de loyer ; PDF conservé.
    Réutilise la pièce déjà produite pour le même montant payé."""
    lease = db.session.get(Lease, sale.lease_id) if sale.lease_id else None
    if lease is None or sale.kind != "invoice":
        raise SaleError("Quittance : facture de loyer d'un bail seulement.", status=409)
    if not sale.paid_cents:
        raise SaleError("Aucun paiement : pas de quittance ni de reçu.", status=409)
    kind = "quittance" if sale.status == "paid" else "recu"
    existing = RentReceipt.query.filter_by(sale_id=sale.id, kind=kind, paid_cents=sale.paid_cents).first()
    if existing is not None and receipt_file(existing) is not None:
        return existing
    rent, charges = split(sale, lease)
    paid_on = max((p.paid_on for p in sale.payments), default=None)
    row = existing or RentReceipt(lease=lease, sale=sale, kind=kind)
    row.period_start, row.period_end = sale.service_start, sale.service_end
    row.rent_cents, row.charges_cents, row.paid_cents, row.paid_on = rent, charges, sale.paid_cents, paid_on
    db.session.add(row)
    db.session.flush()
    folder = instance_dir() / "ventes" / "quittances"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{kind}-{sale.number}-{row.id}.pdf"
    path.write_bytes(render_pdf(row))
    row.pdf_path = str(path.relative_to(instance_dir()))
    db.session.commit()
    return row


def receipt_file(row: RentReceipt):
    if not row.pdf_path:
        return None
    path = (instance_dir() / row.pdf_path).resolve()
    return path if path.is_relative_to(instance_dir().resolve()) and path.is_file() else None


def render_pdf(row: RentReceipt) -> bytes:
    from weasyprint import HTML

    org = organization.get()
    lease = row.lease
    html = render_template("sales/rent_receipt.html", row=row, lease=lease, org=org, tenant=lease.entity,
                           sale=row.sale, money=euros, words=euros_in_words(row.paid_cents),
                           date=lambda d: d.strftime("%d/%m/%Y") if d else "", today=date.today())
    return HTML(string=html).write_pdf()


def send_receipt(row: RentReceipt, to: list[str]) -> None:
    from app.services.membership_reminders import _build_message, _open_smtp, smtp_settings

    path = receipt_file(row)
    if path is None or not to:
        raise SaleError("Quittance introuvable ou destinataire manquant.", status=409)
    org = organization.get()
    title = "Quittance de loyer" if row.kind == "quittance" else "Reçu de paiement"
    period = f"du {row.period_start:%d/%m/%Y} au {row.period_end:%d/%m/%Y}" if row.period_start and row.period_end else ""
    settings = smtp_settings()
    message = _build_message(settings["sender"], ", ".join(to), f"{title} {period} — {lease_label(row.lease)}"[:255],
                             f"<p>Bonjour,</p><p>Veuillez trouver ci-joint votre {title.lower()} {period}.</p>"
                             f"<p>Bien cordialement,<br>{org.name}</p>")
    message.add_attachment(path.read_bytes(), maintype="application", subtype="pdf", filename=path.name)
    server = _open_smtp(settings)
    try:
        server.send_message(message)
    finally:
        try:
            server.quit()
        except Exception:  # noqa: BLE001
            pass
    row.sent_at = datetime.utcnow()
    db.session.commit()


def lease_label(lease: Lease) -> str:
    return f"{lease.unit_label} ({lease.entity.name})"


def tenant_options():
    return [{"value": str(e.id), "label": e.name} for e in Entity.query.order_by(Entity.name)]
