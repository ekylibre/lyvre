"""Comptabilisation des ventes (lot S1, claudedocs/design_ventes.md § 3) au journal VE, à la date
d'émission :
    débit  411NNN du client                     TTC
    crédit compte de vente (7…) de chaque ligne HT
    crédit 44571 TVA collectée                  biens, ou services si TVA d'après les débits
    crédit 44574 TVA collectée à encaisser      services si TVA à l'encaissement
Un avoir produit l'écriture inverse. Le 411NNN est noté sur la fiche du client
(`Entity.customer_account_code`) et créé dans le plan s'il manque, comme le 401NNN des fournisseurs ;
44571 et 44574 sont créés sous 4457 s'ils manquent (le plan SCI n'a que 4457).

Lot T2 : dans un exercice soumis à TVA, une ligne de TVA par taux et par compte, codée `V<taux>` avec sa
base HT ; une vente sans TVA française (client de l'UE avec n° de TVA, client hors UE) porte son code
(`V_UE_S`, `V_UE_B`, `V_EXP`, `V_EXO`) sur ses lignes de produit.
"""
from __future__ import annotations

import re

from app.extensions import db
from app.models import Account, Entity, FiscalYear, Journal, Sale
from app.models.journal_entry import SOURCE_SALE
from app.services import vat_codes
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


def _collected_now(sale: Sale, line) -> bool:
    """TVA exigible à la facture (biens, ou option sur les débits) ; sinon à l'encaissement (44574)."""
    return sale.vat_mode == "debits" or line.nature == "goods"


def entry_lines(sale: Sale, customer: Account, coded: bool = False) -> list[dict]:
    """Lignes de l'écriture VE ; `coded` (exercice soumis à TVA) : codes et bases de TVA (lot T2)."""
    label = f"{sale.entity.name} — {sale.number}"[:255]
    credits: list[tuple] = []
    for line in sale.lines:
        if line.untaxed_cents:
            code = vat_codes.sale_exemption_code(sale, line.nature) if coded and not line.vat_cents else None
            credits.append((line.account_id, line.label[:255], line.untaxed_cents, line.project_id, code, None))
    taxes: dict[tuple[bool, int], list[int]] = {}
    for line in sale.lines:
        if line.vat_cents:
            totals = taxes.setdefault((_collected_now(sale, line), line.vat_rate_bp), [0, 0])
            totals[0] += line.vat_cents
            totals[1] += line.untaxed_cents
    for (now, rate), (tax, base) in sorted(taxes.items(), key=lambda item: (not item[0][0], -item[0][1])):
        account, text = (VAT_COLLECTED, "TVA") if now else (VAT_ON_RECEIPTS, "TVA à encaisser")
        code = vat_codes.sale_tax_code(rate) if coded else None
        credits.append((vat_account(account).id, f"{text} — {label}", tax, None, code, abs(base) if code else None))
    lines = [{"account_id": customer.id, "label": label, "debit_cents": sale.total_cents, "credit_cents": 0}]
    lines += [{"account_id": acc, "label": text, "debit_cents": max(-amount, 0), "credit_cents": max(amount, 0),
               "project_id": project_id, "vat_code": code, "vat_base_cents": base}
              for acc, text, amount, project_id, code, base in credits]
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
        lines=entry_lines(sale, customer_account(sale.entity), coded=fy.vat_liable), source=SOURCE_SALE,
        source_ref=f"SALE:{sale.id}", commit=False)
    sale.journal_entry = entry
    sale.journal_entry_id = entry.id
    # Pièce émise : écriture validée d'office (décision CO7), elle se corrige par un avoir.
    from app.services import validation
    validation.validate_issued(entry)
    return entry
