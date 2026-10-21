"""Règlement des factures d'achat : lien facture ↔ transaction, écriture 401 / 512.

Qonto indique pour chaque facture les transactions qui l'ont payée
(`matched_transactions[].transaction_id` = UUID = `BankTransaction.fitid`). Le lien
est mémorisé dans `purchase_payments`, que la transaction soit déjà importée ou
non. Une transaction liée à une facture comptabilisée et pas encore rapprochée
reçoit une écriture de règlement au journal BQ — débit 401xxx du fournisseur,
crédit banque (sens inverse pour un remboursement) — rapprochée dans la même
transaction SQL. Les règles de catégorisation ignorent les transactions liées.

Une transaction déjà passée par une règle (6xx / banque) avant l'arrivée de sa
facture compterait la charge deux fois : elle est listée « à remplacer »
(`to_replace`) et `replace_many` substitue un règlement à l'écriture de règle.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from app.extensions import db
from app.models import BankTransaction, Journal, JournalEntry, Purchase, PurchasePayment
from app.services.ledger import LedgerError, post_entry
from app.services.purchase_posting import fiscal_year_for, supplier_account
from app.services.reconciler import REVERSED_MESSAGE, reconcile

RULE_SOURCES = ("QONTO_IMPORT", "OFX_IMPORT")


def _transaction_ids(p: Purchase) -> list[str]:
    try:
        payload = json.loads(p.raw_payload) if p.raw_payload else {}
    except ValueError:
        return []
    ids = [m.get("transaction_id") for m in payload.get("matched_transactions") or []]
    return list(dict.fromkeys(i for i in ids if i))


def _qonto_transaction(qonto_id: str) -> BankTransaction | None:
    return BankTransaction.query.filter_by(fitid=qonto_id, source="qonto").first()


# ------------------------------------------------------------------ liens

def link_invoice(p: Purchase) -> None:
    """Aligne `purchase_payments` sur les transactions désignées par Qonto (sans commit)."""
    wanted = _transaction_ids(p)
    for payment in list(p.payments):
        if payment.qonto_transaction_id in wanted:
            continue
        if payment.journal_entry_id is None:
            p.payments.remove(payment)
        else:
            p.review_reason = ("Qonto ne rattache plus la transaction réglée "
                               f"{payment.qonto_transaction_id} à cette facture.")
    known = {payment.qonto_transaction_id for payment in p.payments}
    for qonto_id in wanted:
        if qonto_id not in known:
            p.payments.append(PurchasePayment(qonto_transaction_id=qonto_id))
    for payment in p.payments:
        if payment.bank_transaction_id is None:
            payment.bank_transaction = _qonto_transaction(payment.qonto_transaction_id)


def link_transactions(transactions) -> int:
    """Résout les liens en attente vers des transactions nouvellement importées (sans commit)."""
    by_fitid = {t.fitid: t for t in transactions if t.source == "qonto"}
    if not by_fitid:
        return 0
    pending = PurchasePayment.query.filter(
        PurchasePayment.bank_transaction_id.is_(None),
        PurchasePayment.qonto_transaction_id.in_(list(by_fitid)),
    ).all()
    for payment in pending:
        payment.bank_transaction = by_fitid[payment.qonto_transaction_id]
    return len(pending)


def linked_transaction_ids(transaction_ids) -> set[int]:
    """Transactions (parmi `transaction_ids`) liées à une facture d'achat."""
    ids = [i for i in transaction_ids if i is not None]
    if not ids:
        return set()
    rows = db.session.query(PurchasePayment.bank_transaction_id).filter(
        PurchasePayment.bank_transaction_id.in_(ids)).distinct()
    return {row[0] for row in rows}


# ------------------------------------------------------------------ règlement

def _payments_of(txn: BankTransaction) -> list[PurchasePayment]:
    return PurchasePayment.query.filter_by(bank_transaction_id=txn.id).all()


def _settle_one(txn: BankTransaction, payments) -> JournalEntry:
    """Écriture de règlement rapprochée (sans commit) ; LedgerError si impossible."""
    if txn.is_reversed:
        raise LedgerError(REVERSED_MESSAGE)
    purchases = [payment.purchase for payment in payments]
    entities = {p.entity_id for p in purchases}
    if len(entities) != 1 or None in entities:
        raise LedgerError("Transaction liée à des factures de fournisseurs différents.")
    entity = purchases[0].entity
    supplier = supplier_account(entity)
    fy = fiscal_year_for(txn.transaction_date)
    if fy is None:
        raise LedgerError(f"Aucun exercice ne couvre le {txn.transaction_date.strftime('%d/%m/%Y')}.")
    journal = Journal.query.filter_by(code="BQ").first()
    if journal is None:
        raise LedgerError("Journal « BQ » introuvable.")
    numbers = ", ".join(p.invoice_number or "sans numéro" for p in purchases)
    label = f"Règlement {entity.name} — {numbers}"[:255]
    amount = abs(txn.amount_cents)
    paid = txn.amount_cents < 0  # débit bancaire : paiement ; crédit : remboursement d'avoir
    bank_gl_id = txn.bank_account.account_id
    entry = post_entry(
        fiscal_year_id=fy.id, journal_id=journal.id, entry_date=txn.transaction_date,
        description=label[:500],
        lines=[
            {"account_id": supplier.id, "label": label,
             "debit_cents": amount if paid else 0, "credit_cents": 0 if paid else amount},
            {"account_id": bank_gl_id, "label": txn.label or label,
             "debit_cents": 0 if paid else amount, "credit_cents": amount if paid else 0},
        ],
        source="QONTO_IMPORT" if txn.source == "qonto" else "OFX_IMPORT",
        source_ref=f"PURCHASE_PAYMENT:{txn.fitid}", commit=False,
    )
    bank_line = next(line for line in entry.lines if line.account_id == bank_gl_id)
    reconcile(txn.id, bank_line.id, commit=False)
    for payment in payments:
        payment.journal_entry_id = entry.id
    if txn.entity_id is None:
        txn.entity_id = entity.id
    return entry


def _settleable(txn: BankTransaction, payments) -> bool:
    """Liée à des factures toutes comptabilisées, pas encore réglée ni rapprochée."""
    return (bool(payments) and not txn.reconciled and not txn.journal_line_id
            and not txn.is_reversed
            and all(p.journal_entry_id is None for p in payments)
            and all(p.purchase.journal_entry_id is not None for p in payments))


def settle(purchases=(), transactions=()) -> dict:
    """Passe les règlements possibles (une transaction SQL par transaction bancaire)."""
    candidates = {t.id: t for t in transactions}
    for p in purchases:
        for payment in p.payments:
            if payment.bank_transaction is not None:
                candidates[payment.bank_transaction.id] = payment.bank_transaction
    result = {"settled": 0, "errors": []}
    for txn in candidates.values():
        payments = _payments_of(txn)
        if not _settleable(txn, payments):
            continue
        try:
            _settle_one(txn, payments)
            db.session.commit()
            result["settled"] += 1
        except LedgerError as exc:
            db.session.rollback()
            result["errors"].append(f"Règlement {txn.label or txn.fitid} : {exc}")
    return result


# ------------------------------------------------------------------ écritures de règle

@dataclass
class Replacement:
    transaction: BankTransaction
    entry: JournalEntry
    purchases: list[Purchase]
    replaceable: bool  # écriture de règle (sinon : rapprochement manuel, signalé seulement)


def is_rule_entry(entry: JournalEntry, txn: BankTransaction) -> bool:
    """Écriture générée par une règle : 2 lignes, banque + compte 6xx, référence FITID."""
    if entry.source not in RULE_SOURCES or entry.source_ref != f"FITID:{txn.fitid}":
        return False
    codes = sorted(line.account.code for line in entry.lines)
    return len(codes) == 2 and any(code.startswith("6") for code in codes)


def to_replace() -> list[Replacement]:
    """Transactions liées à une facture comptabilisée mais rapprochées d'une autre écriture."""
    payments = (PurchasePayment.query
                .filter(PurchasePayment.bank_transaction_id.isnot(None),
                        PurchasePayment.journal_entry_id.is_(None)).all())
    by_txn: dict[int, list[PurchasePayment]] = {}
    for payment in payments:
        by_txn.setdefault(payment.bank_transaction_id, []).append(payment)
    rows = []
    for group in by_txn.values():
        txn = group[0].bank_transaction
        if not txn.reconciled or txn.journal_line is None:
            continue
        if any(p.purchase.journal_entry_id is None for p in group):
            continue
        entry = txn.journal_line.entry
        rows.append(Replacement(txn, entry, [p.purchase for p in group], is_rule_entry(entry, txn)))
    return sorted(rows, key=lambda r: (r.transaction.transaction_date, r.transaction.id))


def replace_many(transaction_ids) -> dict:
    """Remplace l'écriture de règle de chaque transaction par un règlement 401 / banque."""
    rows = {r.transaction.id: r for r in to_replace()}
    results = []
    for txn_id in transaction_ids:
        row = rows.get(txn_id)
        if row is None or not row.replaceable:
            results.append({"id": txn_id, "status": "error",
                            "message": "Aucune écriture de règle à remplacer pour cette transaction."})
            continue
        txn, entry = row.transaction, row.entry
        try:
            if entry.fiscal_year.closed:
                raise LedgerError("Exercice clôturé : l'écriture de règle ne peut pas être supprimée.")
            txn.journal_line_id = None
            txn.reconciled = False
            db.session.delete(entry)
            db.session.flush()
            new_entry = _settle_one(txn, _payments_of(txn))
            db.session.commit()
            results.append({"id": txn_id, "status": "ok", "removed": entry.reference,
                            "reference": new_entry.reference})
        except LedgerError as exc:
            db.session.rollback()
            results.append({"id": txn_id, "status": "error", "message": str(exc)})
    counters = {"ok": sum(r["status"] == "ok" for r in results),
                "error": sum(r["status"] == "error" for r in results)}
    return {"results": results, "counters": counters}
