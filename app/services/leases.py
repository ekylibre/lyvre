"""Baux simples, dépôt de garantie, quittances et reçus de loyer (lot S5, décisions V8 et V16).

Un bail porte une facture récurrente de loyer (avis d'échéance) : ligne « Loyer {periode} — lot »
au compte de loyer, ligne « Provisions sur charges {periode} » au compte de charges refacturées
(comptes à valider avec l'expert-comptable : 706 / 708 par défaut). Le dépôt de garantie encaissé
passe au compte 165 (dépôts et cautionnements reçus) : banque ou caisse au débit.

Quittance : quand la facture de loyer d'une période est entièrement payée ; reçu du montant versé
si elle ne l'est qu'en partie. Le PDF est conservé (`ventes/quittances/`), envoyé à la demande.
"""
from __future__ import annotations

from datetime import date, datetime

from flask import render_template

from app.extensions import db
from app.models import Account, BankAccount, Entity, Journal, Lease, Recurrence, RentReceipt, Sale
from app.services import organization, recurrence, sale_entry
from app.services.attachments import instance_dir
from app.services.ledger import LedgerError, post_entry
from app.services.sale_entry import SaleError, parse_date, parse_decimal
from app.utils.money import euros, euros_in_words

DEPOSIT_ACCOUNT = ("165", "Dépôts et cautionnements reçus")
RENT_ACCOUNTS = ("706", "7083", "708")
CHARGES_ACCOUNTS = ("708", "7084", "706")
FIELDS = ("unit_label", "address_line1", "address_line2", "postal_code", "city", "notes")


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


def _template_lines(lease: Lease, vat_rate: str) -> list[dict]:
    lines = [{"label": f"Loyer {{periode}} — {lease.unit_label}"[:300], "unit_price": f"{lease.rent_cents / 100:.2f}",
              "vat_rate": vat_rate, "account_code": lease.rent_account.code if lease.rent_account else ""}]
    if lease.charges_cents:
        lines.append({"label": "Provisions sur charges {periode}", "unit_price": f"{lease.charges_cents / 100:.2f}",
                      "vat_rate": vat_rate, "account_code": lease.charges_account.code if lease.charges_account else ""})
    return lines


def _apply(lease: Lease, data: dict) -> str:
    for key in FIELDS:
        if key in data:
            value = str(data.get(key) or "").strip()
            setattr(lease, key, value or None)
    if not lease.unit_label:
        raise SaleError("Désignation du lot obligatoire.", "unit_label")
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
    if "rent" in data or lease.rent_cents is None:
        lease.rent_cents = _cents(data.get("rent"), "Loyer hors charges", "rent", required=True)
    if "charges" in data:
        lease.charges_cents = _cents(data.get("charges"), "Provisions sur charges", "charges")
    if "deposit" in data:
        lease.deposit_cents = _cents(data.get("deposit"), "Dépôt de garantie", "deposit")
    if "due_day" in data:
        lease.due_day = int(data.get("due_day") or 1)
    lease.rent_account = _account(data.get("rent_account_code") or (lease.rent_account.code if lease.rent_account else None),
                                  RENT_ACCOUNTS, "rent_account_code")
    lease.charges_account = _account(data.get("charges_account_code") or (lease.charges_account.code if lease.charges_account else None),
                                     CHARGES_ACCOUNTS, "charges_account_code")
    return str(data.get("vat_rate") or "0")


def _recurrence_data(lease: Lease, data: dict, vat_rate: str) -> dict:
    return {"label": f"Loyer — {lease.unit_label} — {lease.entity.name}"[:200], "entity_id": lease.entity.id,
            "start_date": lease.start_date.isoformat(), "end_date": lease.end_date.isoformat() if lease.end_date else None,
            "frequency": data.get("frequency") or (lease.recurrence.frequency if lease.recurrence else "monthly"),
            "due_day": lease.due_day, "in_advance": data.get("in_advance", True),
            "qonto_emit": data.get("qonto_emit", lease.recurrence.qonto_emit if lease.recurrence else False),
            "active": lease.active and data.get("active", True), "operation_type": "services",
            "lines": _template_lines(lease, vat_rate)}


def create(data: dict) -> Lease:
    lease = Lease(due_day=1, charges_cents=0, deposit_cents=0)
    try:
        vat_rate = _apply(lease, data)
        db.session.add(lease)
        db.session.flush()
        rec = Recurrence(label="Loyer", frequency="monthly", due_day=lease.due_day)
        payload = _recurrence_data(lease, data, vat_rate)
        rec.label = payload["label"]
        recurrence._template(rec, payload)
        recurrence._schedule(rec, payload)
        db.session.add(rec)
        db.session.flush()
        lease.recurrence = rec
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return lease


def update(lease: Lease, data: dict) -> Lease:
    try:
        if "active" in data:
            lease.active = bool(data.get("active"))
        vat_rate = _apply(lease, data)
        payload = _recurrence_data(lease, data, vat_rate)
        if lease.recurrence is not None:
            lease.recurrence.label = payload["label"]
            recurrence._template(lease.recurrence, payload)
            recurrence._schedule(lease.recurrence, payload)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return lease


# ------------------------------------------------------------------ dépôt de garantie

def deposit(lease: Lease, paid_on: date, ba: BankAccount) -> None:
    """Encaissement du dépôt de garantie : banque (ou caisse) au débit, 165 au crédit."""
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
