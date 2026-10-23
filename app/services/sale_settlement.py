"""Encaissements des factures de vente (lot S2, claudedocs/design_ventes.md § 3.2).

Une transaction bancaire créditrice (OFX ou Qonto) paie une ou plusieurs factures d'un même
client : écriture au journal BQ — débit banque, crédit 411NNN — rapprochée de la transaction dans
la même transaction SQL. Un encaissement saisi (chèque, espèces) passe au journal BQ ou CA selon
le compte choisi, sans rapprochement (le relevé le rapprochera).

TVA à l'encaissement (`vat_mode = receipts`) : chaque encaissement vire de 44574 à 44571 la part de
TVA des prestations qu'il paie, au prorata du restant dû ; le dernier encaissement vire le solde.

Une transaction déjà passée par une règle de catégorisation (banque / 7… ou 411) est remplacée par
l'encaissement : l'écriture de règle est supprimée. `auto_match` lie une facture à une transaction
de même montant que son restant dû quand ce candidat est unique, et unique à elle seule.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func

from app.extensions import db
from app.models import BankAccount, BankTransaction, Journal, JournalEntry, PurchasePayment, Sale, SalePayment
from app.services.ledger import LedgerError, post_entry
from app.services.reconciler import REVERSED_MESSAGE, reconcile
from app.services.sale_entry import SaleError, fiscal_year_for
from app.services.sale_posting import VAT_COLLECTED, VAT_ON_RECEIPTS, customer_account, vat_account

SOURCE_SALE_PAYMENT = "SALE_PAYMENT"
RULE_SOURCES = ("QONTO_IMPORT", "OFX_IMPORT")
MATCH_DAYS_BEFORE = 5
MATCH_DAYS_AFTER = 90
OPEN_STATUSES = ("issued", "partially_paid")


# ------------------------------------------------------------------ restant dû, statut, TVA

def credited_cents(sale: Sale) -> int:
    return int(db.session.query(func.coalesce(func.sum(Sale.total_cents), 0)).filter(
        Sale.kind == "credit_note", Sale.invoice_id == sale.id, Sale.status != "draft").scalar() or 0)


def paid_cents(sale: Sale) -> int:
    return int(db.session.query(func.coalesce(func.sum(SalePayment.amount_cents), 0))
               .filter(SalePayment.sale_id == sale.id).scalar() or 0)


def due_cents(sale: Sale) -> int:
    """Restant dû d'une facture émise : TTC − avoirs émis − encaissements."""
    if sale.kind != "invoice" or sale.status in ("draft", "canceled"):
        return 0
    return max(sale.total_cents - credited_cents(sale) - paid_cents(sale), 0)


def refresh_status(sale: Sale) -> None:
    """Payée, payée en partie ou émise d'après les encaissements (sans commit)."""
    db.session.flush()
    sale.paid_cents = paid_cents(sale)
    if sale.kind != "invoice" or sale.status in ("draft", "canceled"):
        return
    if sale.paid_cents and due_cents(sale) == 0:
        sale.status = "paid"
    elif sale.paid_cents:
        sale.status = "partially_paid"
    else:
        sale.status = "issued"


def _services_vat(sale: Sale) -> int:
    return sum(l.vat_cents for l in sale.lines if l.nature != "goods")


def outstanding_vat(sale: Sale) -> int:
    """TVA des prestations encore en 44574 pour cette facture (TVA à l'encaissement)."""
    if sale.vat_mode != "receipts":
        return 0
    credited = sum(_services_vat(note) for note in Sale.query.filter(
        Sale.kind == "credit_note", Sale.invoice_id == sale.id, Sale.status != "draft"))
    released = int(db.session.query(func.coalesce(func.sum(SalePayment.vat_released_cents), 0))
                   .filter(SalePayment.sale_id == sale.id).scalar() or 0)
    return max(_services_vat(sale) - credited - released, 0)


def vat_release(sale: Sale, amount: int) -> int:
    due, outstanding = due_cents(sale), outstanding_vat(sale)
    if not outstanding or not due:
        return 0
    return outstanding if amount >= due else round(outstanding * amount / due)


# ------------------------------------------------------------------ écriture

def _journal(ba: BankAccount) -> Journal:
    code, label = ("CA", "Caisse") if ba.kind == "cash" else ("BQ", "Banque")
    journal = Journal.query.filter_by(code=code).first()
    if journal is None:
        journal = Journal(code=code, label=label)
        db.session.add(journal)
        db.session.flush()
    return journal


def _check_allocations(allocations: list[tuple[Sale, int]]) -> None:
    if not allocations:
        raise SaleError("Aucune facture à encaisser.", "allocations")
    clients = {sale.entity_id for sale, _ in allocations}
    if len(clients) != 1:
        raise SaleError("Un encaissement porte sur les factures d'un seul client.", "allocations")
    for sale, amount in allocations:
        if sale.kind != "invoice" or sale.status not in OPEN_STATUSES:
            raise SaleError(f"La facture {sale.number or ''} n'attend pas d'encaissement.", status=409)
        if amount <= 0:
            raise SaleError("Montant d'encaissement invalide.", "amount")
        if amount > due_cents(sale):
            raise SaleError(f"Le montant dépasse le restant dû de la facture {sale.number}.", "amount")


def _post(allocations, when: date, ba: BankAccount, label: str, source: str, source_ref: str) -> JournalEntry:
    fy = fiscal_year_for(when)
    if fy is None:
        raise SaleError(f"Aucun exercice ne couvre le {when:%d/%m/%Y}.", status=409)
    entity = allocations[0][0].entity
    customer = customer_account(entity)
    total = sum(amount for _, amount in allocations)
    releases = [(sale, amount, vat_release(sale, amount)) for sale, amount in allocations]
    released = sum(r for _, _, r in releases)
    numbers = ", ".join(sale.number for sale, _ in allocations)
    text = f"Encaissement {entity.name} — {numbers}"[:255]
    lines = [{"account_id": ba.account_id, "label": label or text, "debit_cents": total, "credit_cents": 0},
             {"account_id": customer.id, "label": text, "debit_cents": 0, "credit_cents": total}]
    if released:
        lines += [{"account_id": vat_account(VAT_ON_RECEIPTS).id, "label": f"TVA encaissée — {numbers}"[:255],
                   "debit_cents": released, "credit_cents": 0},
                  {"account_id": vat_account(VAT_COLLECTED).id, "label": f"TVA encaissée — {numbers}"[:255],
                   "debit_cents": 0, "credit_cents": released}]
    try:
        entry = post_entry(fiscal_year_id=fy.id, journal_id=_journal(ba).id, entry_date=when, description=text[:500],
                           lines=lines, source=source, source_ref=source_ref, commit=False)
    except LedgerError as exc:
        raise SaleError(str(exc), status=409) from None
    entry._releases = releases  # noqa: SLF001 — transmis à l'appelant, sans persistance
    return entry


# ------------------------------------------------------------------ transaction bancaire

def _linked_sale_transactions() -> set[int]:
    return {row[0] for row in db.session.query(SalePayment.bank_transaction_id)
            .filter(SalePayment.bank_transaction_id.isnot(None)).distinct()}


def linked_transaction_ids(transaction_ids) -> set[int]:
    """Transactions (parmi `transaction_ids`) qui encaissent une facture de vente."""
    ids = [i for i in transaction_ids if i is not None]
    if not ids:
        return set()
    rows = db.session.query(SalePayment.bank_transaction_id).filter(SalePayment.bank_transaction_id.in_(ids)).distinct()
    return {row[0] for row in rows}


def is_rule_entry(entry: JournalEntry, txn: BankTransaction) -> bool:
    """Écriture d'une règle de catégorisation : 2 lignes, banque + produit (7…) ou client (411…)."""
    if entry.source not in RULE_SOURCES or entry.source_ref != f"FITID:{txn.fitid}":
        return False
    codes = [line.account.code for line in entry.lines]
    return len(codes) == 2 and any(code.startswith(("7", "411")) for code in codes)


def _free(txn: BankTransaction) -> bool:
    if txn.is_reversed or txn.amount_cents <= 0:
        return False
    if not txn.reconciled and txn.journal_line_id is None:
        return True
    return txn.journal_line is not None and is_rule_entry(txn.journal_line.entry, txn)


def candidates(sale: Sale, limit: int = 20) -> list[BankTransaction]:
    """Crédits bancaires libres pouvant encaisser la facture : montant égal au restant dû d'abord,
    puis même client, puis date la plus proche de l'échéance."""
    due = due_cents(sale)
    if not due or sale.issue_date is None:
        return []
    reference = sale.due_date or sale.issue_date
    start = sale.issue_date - timedelta(days=MATCH_DAYS_BEFORE)
    end = max(reference, date.today()) + timedelta(days=MATCH_DAYS_AFTER)
    taken = _linked_sale_transactions() | {row[0] for row in db.session.query(PurchasePayment.bank_transaction_id)
                                            .filter(PurchasePayment.bank_transaction_id.isnot(None))}
    rows = (BankTransaction.query.filter(BankTransaction.amount_cents > 0,
                                         BankTransaction.transaction_date.between(start, end))
            .all())
    rows = [t for t in rows if t.id not in taken and _free(t)]
    return sorted(rows, key=lambda t: (t.amount_cents != due, t.entity_id != sale.entity_id,
                                       abs((t.transaction_date - reference).days), t.id))[:limit]


def match(txn: BankTransaction, allocations: list[tuple[Sale, int]]) -> JournalEntry:
    """Encaisse les factures par la transaction (sommes égales) ; commit ; SaleError sinon."""
    if txn.is_reversed:
        raise SaleError(REVERSED_MESSAGE, status=409)
    if txn.amount_cents <= 0:
        raise SaleError("Seul un crédit bancaire encaisse une facture.", status=409)
    if txn.id in linked_transaction_ids([txn.id]) or PurchasePayment.query.filter_by(bank_transaction_id=txn.id).first():
        raise SaleError("Transaction déjà rattachée à une facture.", status=409)
    if not _free(txn):
        raise SaleError("Transaction déjà rapprochée d'une autre écriture : défaites d'abord ce rapprochement.", status=409)
    _check_allocations(allocations)
    if sum(amount for _, amount in allocations) != txn.amount_cents:
        raise SaleError("La somme encaissée doit être égale au montant de la transaction.", "allocations")
    try:
        if txn.journal_line is not None:  # écriture de règle remplacée
            rule_entry = txn.journal_line.entry
            if rule_entry.fiscal_year.closed:
                raise SaleError("Exercice clôturé : l'écriture de règle ne peut pas être remplacée.", status=409)
            txn.journal_line_id, txn.reconciled = None, False
            db.session.delete(rule_entry)
            db.session.flush()
        entry = _post(allocations, txn.transaction_date, txn.bank_account, txn.label or "",
                      SOURCE_SALE_PAYMENT, f"SALE_PAYMENT:{txn.fitid}")
        bank_line = next(line for line in entry.lines if line.account_id == txn.bank_account.account_id)
        reconcile(txn.id, bank_line.id, commit=False)
        for sale, amount, released in entry._releases:  # noqa: SLF001
            db.session.add(SalePayment(sale=sale, amount_cents=amount, paid_on=txn.transaction_date, origin="bank",
                                       method="transfer", bank_transaction_id=txn.id, bank_account_id=txn.bank_account_id,
                                       journal_entry_id=entry.id, vat_released_cents=released))
        if txn.entity_id is None:
            txn.entity_id = allocations[0][0].entity_id
        for sale, _ in allocations:
            refresh_status(sale)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return entry


def record_manual(sale: Sale, amount: int, paid_on: date, ba: BankAccount, method: str) -> JournalEntry:
    """Encaissement saisi (chèque, espèces…) : écriture banque ou caisse / 411, non rapprochée."""
    if paid_on > date.today():
        raise SaleError("Date d'encaissement à venir.", "paid_on")
    _check_allocations([(sale, amount)])
    try:
        entry = _post([(sale, amount)], paid_on, ba, "", SOURCE_SALE_PAYMENT, f"SALE_PAYMENT:manual:{sale.id}")
        (_, _, released), = entry._releases  # noqa: SLF001
        db.session.add(SalePayment(sale=sale, amount_cents=amount, paid_on=paid_on, origin="manual", method=method,
                                   bank_account_id=ba.id, journal_entry_id=entry.id, vat_released_cents=released))
        refresh_status(sale)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return entry


def auto_match() -> dict:
    """Factures ouvertes au candidat unique (montant = restant dû), lui-même candidat d'elle seule."""
    pending = Sale.query.filter(Sale.kind == "invoice", Sale.status.in_(OPEN_STATUSES)).all()
    exact = {}
    for sale in pending:
        due = due_cents(sale)
        exact[sale.id] = [t for t in candidates(sale) if t.amount_cents == due]
    claims: dict[int, int] = {}
    for found in exact.values():
        for txn in found:
            claims[txn.id] = claims.get(txn.id, 0) + 1
    matched, errors = 0, []
    for sale in pending:
        found = exact[sale.id]
        if len(found) == 1 and claims[found[0].id] == 1:
            try:
                match(found[0], [(sale, found[0].amount_cents)])
                matched += 1
            except SaleError as exc:
                errors.append(f"{sale.number} : {exc.message}")
    return {"matched": matched, "errors": errors}


def unlink(payment: SalePayment) -> None:
    """Défait un encaissement : son écriture (et celles des autres factures qu'elle encaisse) est
    supprimée, le rapprochement défait, les statuts recalculés."""
    from app.services.ledger import delete_entries

    if payment.journal_entry_id is None:
        sale = payment.sale
        db.session.delete(payment)
        refresh_status(sale)
        db.session.commit()
        return
    (outcome,) = delete_entries([payment.journal_entry_id])
    if outcome["status"] != "ok":
        raise SaleError(outcome["message"], status=409)


def forget_entry_payments(entry_id: int) -> None:
    """Écriture d'encaissement supprimée (écran Écritures, `unlink`) : ses encaissements disparaissent
    et le statut des factures est recalculé (sans commit)."""
    payments = SalePayment.query.filter_by(journal_entry_id=entry_id).all()
    sales = {p.sale for p in payments}
    for payment in payments:
        db.session.delete(payment)
    for sale in sales:
        refresh_status(sale)


# ------------------------------------------------------------------ tableau de bord

def receivables_summary(start: date | None = None, end: date | None = None) -> dict:
    """Chiffre d'affaires facturé HT (factures − avoirs émis) sur la période, encours clients et
    factures échues."""
    issued = Sale.query.filter(Sale.kind.in_(("invoice", "credit_note")), Sale.status != "draft")
    if start:
        issued = issued.filter(Sale.issue_date >= start)
    if end:
        issued = issued.filter(Sale.issue_date <= end)
    revenue = sum(s.untaxed_cents * (-1 if s.kind == "credit_note" else 1) for s in issued)
    open_invoices = Sale.query.filter(Sale.kind == "invoice", Sale.status.in_(OPEN_STATUSES)).all()
    today = date.today()
    overdue = [s for s in open_invoices if s.due_date and s.due_date < today]
    return {"revenue_cents": revenue, "receivable_cents": sum(due_cents(s) for s in open_invoices),
            "overdue_count": len(overdue), "overdue_cents": sum(due_cents(s) for s in overdue),
            "has_sales": Sale.query.filter(Sale.kind == "invoice").first() is not None}
