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

Factures saisies payées hors Qonto (OFX) : `match_candidates` cherche les débits
de même montant autour de la date ; `auto_match` lie un candidat **unique**
(`origin = match`), `link_manual` un débit choisi sur la fiche (`origin = manual`),
`unlink` défait un tel lien et son règlement.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta

from app.extensions import db
from app.models import (
    BankAccount, BankTransaction, Journal, JournalEntry, Purchase, PurchasePayment,
)
from app.services.ledger import LedgerError, delete_entries, post_entry, remove_entry
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
        if payment.origin != "qonto" or payment.qonto_transaction_id in wanted:
            continue  # un lien hors Qonto (OFX) ne dépend pas de Qonto
        if payment.journal_entry_id is None:
            p.payments.remove(payment)
        else:
            p.review_reason = ("Qonto ne rattache plus la transaction réglée "
                               f"{payment.qonto_transaction_id} à cette facture.")
    known = {payment.qonto_transaction_id for payment in p.payments}
    for qonto_id in wanted:
        if qonto_id not in known:
            p.payments.append(PurchasePayment(qonto_transaction_id=qonto_id, origin="qonto"))
    for payment in p.payments:
        if payment.bank_transaction_id is None and payment.qonto_transaction_id:
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
            remove_entry(entry)
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


# ------------------------------------------------------------------ hors Qonto (OFX)

MATCH_DAYS_BEFORE = 5
MATCH_DAYS_AFTER = 60


def _expected_amount(p: Purchase) -> int:
    """Montant bancaire attendu : débit du TTC (net à payer s'il est connu), crédit pour un avoir."""
    amount = p.payable_cents or p.total_cents
    return amount if p.is_credit_note else -amount


def _free_for_matching(txn: BankTransaction) -> bool:
    """Ni annulée, ni rapprochée autrement que par une écriture de règle (alors à remplacer)."""
    if txn.is_reversed:
        return False
    if not txn.reconciled and txn.journal_line_id is None:
        return True
    return txn.journal_line is not None and is_rule_entry(txn.journal_line.entry, txn)


def awaiting_payment(p: Purchase) -> bool:
    """Facture saisie, comptabilisée, sans aucun lien de paiement."""
    return (p.source == "manual" and p.journal_entry_id is not None and not p.is_hidden
            and not p.payments)


def match_window(p: Purchase):
    """(début, fin) : date − 5 jours ; échéance (à défaut date) + 60 jours."""
    reference = max(p.due_date or p.issue_date, p.issue_date)
    return (p.issue_date - timedelta(days=MATCH_DAYS_BEFORE),
            reference + timedelta(days=MATCH_DAYS_AFTER))


def match_candidates(p: Purchase) -> list[BankTransaction]:
    """Transactions hors Qonto pouvant payer la facture, même tiers puis date la plus proche."""
    if p.issue_date is None:
        return []
    reference = p.due_date or p.issue_date
    start, end = match_window(p)
    linked = db.session.query(PurchasePayment.bank_transaction_id).filter(
        PurchasePayment.bank_transaction_id.isnot(None))
    rows = (BankTransaction.query.join(BankAccount, BankTransaction.bank_account_id == BankAccount.id)
            .filter(BankAccount.qonto_account_id.is_(None),
                    BankTransaction.amount_cents == _expected_amount(p),
                    BankTransaction.transaction_date.between(start, end),
                    BankTransaction.id.notin_(linked))
            .all())
    rows = [t for t in rows if _free_for_matching(t)]
    return sorted(rows, key=lambda t: (t.entity_id != p.entity_id if p.entity_id else True,
                                       abs((t.transaction_date - reference).days), t.id))


def auto_match(purchases=None) -> dict:
    """Lie chaque facture en attente à son candidat s'il est unique, et unique à elle seule.

    `purchases` : factures à traiter (défaut : toutes celles en attente). Un débit candidat de
    plusieurs factures en attente n'est jamais lié automatiquement (choix sur la fiche).
    """
    pending = [p for p in Purchase.query.filter(Purchase.source == "manual",
                                                Purchase.journal_entry_id.isnot(None),
                                                Purchase.is_hidden.is_(False))
               if awaiting_payment(p)]
    targets = {p.id for p in (purchases if purchases is not None else pending) if awaiting_payment(p)}
    candidates = {p.id: match_candidates(p) for p in pending}
    claims: dict[int, int] = {}
    for found in candidates.values():
        for txn in found:
            claims[txn.id] = claims.get(txn.id, 0) + 1
    linked = []
    for p in pending:
        found = candidates[p.id]
        if p.id in targets and len(found) == 1 and claims[found[0].id] == 1:
            p.payments.append(PurchasePayment(bank_transaction=found[0], origin="match"))
            linked.append(p)
    db.session.commit()
    result = settle(purchases=linked) if linked else {"settled": 0, "errors": []}
    return {"matched": len(linked), "settled": result["settled"], "errors": result["errors"]}


def link_manual(p: Purchase, bank_transaction_id: int) -> dict:
    """Règle la facture par une transaction choisie parmi ses candidats ; LedgerError sinon."""
    if not awaiting_payment(p):
        raise LedgerError("Cette facture n'attend pas de règlement.")
    txn = next((t for t in match_candidates(p) if t.id == bank_transaction_id), None)
    if txn is None:
        raise LedgerError("Cette transaction ne peut pas régler la facture.")
    p.payments.append(PurchasePayment(bank_transaction=txn, origin="manual"))
    db.session.commit()
    return settle(purchases=[p])


def unlink(payment: PurchasePayment) -> None:
    """Défait un règlement hors Qonto : écriture supprimée, rapprochement défait, lien retiré."""
    if payment.origin == "qonto":
        raise LedgerError("Un paiement désigné par Qonto ne se défait pas ici.")
    if payment.journal_entry_id is not None:
        (outcome,) = delete_entries([payment.journal_entry_id], reverse_validated=True)
        if outcome["status"] not in ("ok", "reversed"):
            raise LedgerError(outcome["message"])
    db.session.delete(payment)
    db.session.commit()
