"""Comptabilisation des ventes (lot S1, claudedocs/design_ventes.md § 3) au journal VE, à la date
d'émission :
    débit  411NNN du client                     TTC
    crédit compte de vente (7…) de chaque ligne HT
    crédit 44571 TVA collectée                  biens, ou services si TVA d'après les débits
    crédit 44574 TVA collectée à encaisser      services si TVA à l'encaissement
Un avoir produit l'écriture inverse. Le 411NNN est noté sur la fiche du client
(`Entity.customer_account_code`) et créé dans le plan s'il manque, comme le 401NNN des fournisseurs ;
44571 et 44574 sont créés sous 4457 s'ils manquent (le plan SCI n'a que 4457).
"""
from __future__ import annotations

import re

from app.extensions import db
from app.models import Account, Entity, FiscalYear, Journal, Sale
from app.models.journal_entry import SOURCE_SALE
from app.services.ledger import LedgerError, post_entry

CUSTOMER_PARENT = "411"
CUSTOMER_CODE = re.compile(r"^411(\d{3})$")
VAT_COLLECTED = ("44571", "TVA collectée")
VAT_ON_RECEIPTS = ("44574", "TVA collectée à encaisser")
VAT_PARENT = "4457"


def _journal() -> Journal:
    journal = Journal.query.filter_by(code="VE").first()
    if journal is None:
        journal = Journal(code="VE", label="Ventes")
        db.session.add(journal)
        db.session.flush()
    return journal


def next_customer_code() -> str:
    codes = [c for (c,) in db.session.query(Account.code).filter(Account.code.like("411%"))]
    codes += [c for (c,) in db.session.query(Entity.customer_account_code)
              .filter(Entity.customer_account_code.like("411%"))]
    numbers = [int(m.group(1)) for m in map(CUSTOMER_CODE.match, codes) if m]
    return f"411{max(numbers, default=0) + 1:03d}"


def customer_account(entity: Entity) -> Account:
    """Compte 411xxx du client, créé (et noté sur la fiche) au besoin ; sans commit."""
    code = entity.customer_account_code
    if code and not code.startswith("41"):
        raise LedgerError(f"Le compte client de « {entity.name} » ({code}) n'est pas un compte 41….")
    if not code:
        entity.customer_account_code = code = next_customer_code()
    account = Account.query.filter_by(code=code).first()
    if account is not None and account.is_header:
        raise LedgerError(f"Le compte client de « {entity.name} » ({code}) est un compte d'en-tête.")
    if account is None:
        parent = Account.query.filter_by(code=CUSTOMER_PARENT).first()
        account = Account(code=code, label=entity.name[:255], account_type="TIERS",
                          parent_id=parent.id if parent else None)
        db.session.add(account)
        db.session.flush()
    return account


def vat_account(code_label: tuple[str, str]) -> Account:
    code, label = code_label
    account = Account.query.filter_by(code=code, is_header=False).first()
    if account is None:
        parent = Account.query.filter_by(code=VAT_PARENT).first()
        account = Account(code=code, label=label, account_type="TIERS", parent_id=parent.id if parent else None)
        db.session.add(account)
        db.session.flush()
    return account


def entry_lines(sale: Sale, customer: Account) -> list[dict]:
    label = f"{sale.entity.name} — {sale.number}"[:255]
    credits: list[tuple[int, str, int, int | None]] = []
    for line in sale.lines:
        if line.untaxed_cents:
            credits.append((line.account_id, line.label[:255], line.untaxed_cents, line.project_id))
    collected = sum(l.vat_cents for l in sale.lines if l.nature == "goods" or sale.vat_mode == "debits")
    on_receipts = sale.tax_cents - collected if sale.vat_mode == "receipts" else 0
    if sale.vat_mode == "debits":
        collected = sale.tax_cents
    if collected:
        credits.append((vat_account(VAT_COLLECTED).id, f"TVA — {label}", collected, None))
    if on_receipts:
        credits.append((vat_account(VAT_ON_RECEIPTS).id, f"TVA à encaisser — {label}", on_receipts, None))
    lines = [{"account_id": customer.id, "label": label, "debit_cents": sale.total_cents, "credit_cents": 0}]
    lines += [{"account_id": acc, "label": text, "debit_cents": max(-amount, 0), "credit_cents": max(amount, 0),
               "project_id": project_id} for acc, text, amount, project_id in credits]
    if sale.kind == "credit_note":
        for line in lines:
            line["debit_cents"], line["credit_cents"] = line["credit_cents"], line["debit_cents"]
    return lines


def post(sale: Sale, fy: FiscalYear):
    """Écriture VE de la pièce émise (sans commit)."""
    missing = [str(i) for i, line in enumerate(sale.lines, start=1) if not line.account_id]
    if missing:
        raise LedgerError(f"Compte de vente manquant (ligne {', '.join(missing)}).")
    kind = "Avoir" if sale.kind == "credit_note" else "Facture"
    entry = post_entry(
        fiscal_year_id=fy.id, journal_id=_journal().id, entry_date=sale.issue_date,
        description=f"{kind} {sale.number} — {sale.entity.name}"[:500],
        lines=entry_lines(sale, customer_account(sale.entity)), source=SOURCE_SALE,
        source_ref=f"SALE:{sale.id}", commit=False)
    sale.journal_entry = entry
    sale.journal_entry_id = entry.id
    return entry
