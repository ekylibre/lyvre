from datetime import timedelta
from app.extensions import db
from app.models import BankTransaction, JournalLine, JournalEntry


def suggest_matches(bank_transaction_id, window_days=3):
    """
    Find unmatched journal lines that could match a bank transaction.
    Returns list of JournalLine ordered by match score (best first).
    """
    bt = BankTransaction.query.get_or_404(bank_transaction_id)
    target_cents = bt.amount_cents

    date_from = bt.transaction_date - timedelta(days=window_days)
    date_to = bt.transaction_date + timedelta(days=window_days)

    # For a debit on bank (negative amount), the journal line should be a credit on 512x
    # For a credit on bank (positive amount), the journal line should be a debit on 512x
    if target_cents < 0:
        candidates = (
            JournalLine.query
            .join(JournalEntry)
            .filter(
                JournalLine.credit_cents == abs(target_cents),
                JournalLine.bank_transaction == None,
                JournalEntry.entry_date.between(date_from, date_to),
            )
            .all()
        )
    else:
        candidates = (
            JournalLine.query
            .join(JournalEntry)
            .filter(
                JournalLine.debit_cents == target_cents,
                JournalLine.bank_transaction == None,
                JournalEntry.entry_date.between(date_from, date_to),
            )
            .all()
        )

    # Score: exact date match = 2, same week = 1
    def score(line):
        if line.entry.entry_date == bt.transaction_date:
            return 2
        return 1

    return sorted(candidates, key=score, reverse=True)


def reconcile(bank_transaction_id, journal_line_id, commit=True):
    """Link a bank transaction to a journal line.

    ``commit=False`` lets the caller include it in a larger transaction.
    """
    bt = BankTransaction.query.get_or_404(bank_transaction_id)
    JournalLine.query.get_or_404(journal_line_id)

    bt.journal_line_id = journal_line_id
    bt.reconciled = True
    if commit:
        db.session.commit()
    return bt


def unreconcile(bank_transaction_id):
    """Remove the link between a bank transaction and a journal line."""
    bt = BankTransaction.query.get_or_404(bank_transaction_id)
    bt.journal_line_id = None
    bt.reconciled = False
    db.session.commit()
    return bt


def auto_reconcile(bank_account_id):
    """
    Automatically reconcile transactions that have exactly one exact-date, exact-amount match.
    Returns number of reconciled transactions.
    """
    unreconciled = BankTransaction.query.filter_by(
        bank_account_id=bank_account_id, reconciled=False
    ).all()

    count = 0
    for bt in unreconciled:
        matches = suggest_matches(bt.id, window_days=0)
        if len(matches) == 1:
            reconcile(bt.id, matches[0].id)
            count += 1

    return count
