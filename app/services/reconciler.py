"""Bank reconciliation: link a bank transaction to the journal line that records it.

A valid link: the journal line is on the bank account's ledger account, with
the same signed amount (debit for money in, credit for money out), and neither
the transaction nor the line is already reconciled. A transaction reversed by the
bank (``is_reversed``) can no longer be reconciled.
"""

REVERSED_MESSAGE = "Transaction annulée par la banque : elle ne peut pas être rapprochée."
from datetime import timedelta

from app.extensions import db
from app.models import BankTransaction, JournalEntry, JournalLine


def suggest_matches_scored(bank_transaction_id, window_days=3):
    """Unreconciled journal lines that could record the bank transaction.

    Candidates: lines on the bank account's ledger account, same signed amount,
    entry date within ``window_days``. Returns ``[(line, score)]`` best first
    (score 2 = same date, 1 = within the window).
    """
    bt = BankTransaction.query.get_or_404(bank_transaction_id)
    if bt.is_reversed:
        return []
    target = bt.amount_cents
    date_from = bt.transaction_date - timedelta(days=window_days)
    date_to = bt.transaction_date + timedelta(days=window_days)

    query = (
        JournalLine.query
        .join(JournalEntry)
        .filter(
            JournalLine.account_id == bt.bank_account.account_id,
            JournalLine.bank_transaction == None,  # noqa: E711
            JournalEntry.entry_date.between(date_from, date_to),
        )
    )
    if target < 0:
        query = query.filter(JournalLine.credit_cents == -target, JournalLine.debit_cents == 0)
    else:
        query = query.filter(JournalLine.debit_cents == target, JournalLine.credit_cents == 0)

    scored = [
        (line, 2 if line.entry.entry_date == bt.transaction_date else 1)
        for line in query.all()
    ]
    return sorted(
        scored,
        key=lambda pair: (-pair[1], abs((pair[0].entry.entry_date - bt.transaction_date).days),
                          pair[0].id),
    )


def suggest_matches(bank_transaction_id, window_days=3):
    """Candidate journal lines, best first (see suggest_matches_scored)."""
    return [line for line, _score in suggest_matches_scored(bank_transaction_id, window_days)]


def check_link(bt, line, lines_taken=()):
    """Error message if ``bt`` cannot be reconciled with ``line``, else None."""
    if bt is None:
        return "Transaction bancaire introuvable."
    if line is None:
        return "Ligne d'écriture introuvable."
    if bt.reconciled or bt.journal_line_id:
        return "Transaction déjà rapprochée."
    if bt.is_reversed:
        return REVERSED_MESSAGE
    if line.bank_transaction is not None or line.id in lines_taken:
        return "Ligne d'écriture déjà rapprochée."
    if line.account_id != bt.bank_account.account_id:
        return "La ligne n'est pas sur le compte comptable du compte bancaire."
    if line.debit_cents - line.credit_cents != bt.amount_cents:
        return "Montant différent de celui de la transaction."
    return None


def reconcile(bank_transaction_id, journal_line_id, commit=True):
    """Link a bank transaction to a journal line (no checks: see reconcile_many).

    ``commit=False`` lets the caller include it in a larger transaction.
    """
    bt = BankTransaction.query.get_or_404(bank_transaction_id)
    JournalLine.query.get_or_404(journal_line_id)

    bt.journal_line_id = journal_line_id
    bt.reconciled = True
    if commit:
        db.session.commit()
    return bt


def reconcile_many(pairs):
    """Reconcile ``[(bank_transaction_id, journal_line_id)]`` in one transaction.

    Each pair is checked (``check_link``); invalid pairs are reported and
    skipped. Returns ``[{bank_transaction_id, journal_line_id, status, message?}]``.
    """
    results = []
    taken = set()
    for bt_id, line_id in pairs:
        bt = db.session.get(BankTransaction, bt_id) if isinstance(bt_id, int) else None
        line = db.session.get(JournalLine, line_id) if isinstance(line_id, int) else None
        error = check_link(bt, line, taken)
        result = {"bank_transaction_id": bt_id, "journal_line_id": line_id}
        if error:
            results.append({**result, "status": "error", "message": error})
            continue
        bt.journal_line_id = line.id
        bt.reconciled = True
        taken.add(line.id)
        results.append({**result, "status": "ok"})
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return results


def unreconcile_many(bank_transaction_ids):
    """Undo the reconciliation of several transactions in one transaction.

    Returns ``[{bank_transaction_id, status, journal_line_id?, message?}]``;
    ``journal_line_id`` is the line that was linked (to redo the link).
    """
    results = []
    for bt_id in bank_transaction_ids:
        bt = db.session.get(BankTransaction, bt_id) if isinstance(bt_id, int) else None
        if bt is None:
            results.append({"bank_transaction_id": bt_id, "status": "error",
                            "message": "Transaction bancaire introuvable."})
            continue
        if not bt.reconciled:
            results.append({"bank_transaction_id": bt_id, "status": "error",
                            "message": "Transaction non rapprochée."})
            continue
        results.append({"bank_transaction_id": bt_id, "status": "ok",
                        "journal_line_id": bt.journal_line_id})
        bt.journal_line_id = None
        bt.reconciled = False
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return results


def auto_pairs(bank_account_id, bank_transaction_ids=None):
    """Unambiguous pairs: exactly one same-date candidate line, not claimed
    by another transaction of the batch."""
    query = BankTransaction.query.filter_by(bank_account_id=bank_account_id, reconciled=False,
                                            is_reversed=False)
    if bank_transaction_ids is not None:
        query = query.filter(BankTransaction.id.in_(bank_transaction_ids))
    pairs = []
    claimed = {}
    for bt in query.order_by(BankTransaction.transaction_date, BankTransaction.id).all():
        matches = suggest_matches(bt.id, window_days=0)
        if len(matches) == 1:
            claimed.setdefault(matches[0].id, []).append(bt.id)
            pairs.append((bt.id, matches[0].id))
    # A line matching several transactions is ambiguous: leave them all.
    return [(bt_id, line_id) for bt_id, line_id in pairs if len(claimed[line_id]) == 1]


def auto_reconcile(bank_account_id, bank_transaction_ids=None, dry_run=False):
    """Reconcile transactions with exactly one exact-date, exact-amount match.

    Returns the per-pair results (``dry_run``: the pairs found, nothing saved).
    """
    pairs = auto_pairs(bank_account_id, bank_transaction_ids)
    if dry_run:
        return [{"bank_transaction_id": bt_id, "journal_line_id": line_id, "status": "found"}
                for bt_id, line_id in pairs]
    return reconcile_many(pairs)
