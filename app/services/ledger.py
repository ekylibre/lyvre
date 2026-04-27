from datetime import date
from app.extensions import db
from app.models import Account, JournalEntry, JournalLine, FiscalYear


class LedgerError(Exception):
    pass


def validate_lines(lines):
    """Raise LedgerError if lines don't balance or are empty."""
    if not lines:
        raise LedgerError("Une écriture doit avoir au moins deux lignes.")
    total_debit = sum(l.get("debit_cents", 0) for l in lines)
    total_credit = sum(l.get("credit_cents", 0) for l in lines)
    if total_debit != total_credit:
        raise LedgerError(
            f"Écriture déséquilibrée : débit {total_debit} ≠ crédit {total_credit} (en centimes)."
        )
    if total_debit == 0:
        raise LedgerError("Le total de l'écriture ne peut pas être nul.")


def post_entry(fiscal_year_id, journal_id, entry_date, description, lines, source="MANUAL", source_ref=None, reference=None):
    """
    Create a balanced journal entry.
    lines: list of dicts with keys: account_id, label, debit_cents, credit_cents
    Returns the created JournalEntry.
    """
    fy = FiscalYear.query.get(fiscal_year_id)
    if fy is None:
        raise LedgerError("Exercice introuvable.")
    if fy.closed:
        raise LedgerError(f"L'exercice « {fy.label} » est clôturé.")

    validate_lines(lines)

    if reference is None:
        from app.models import Journal
        journal = Journal.query.get(journal_id)
        count = JournalEntry.query.filter_by(journal_id=journal_id, fiscal_year_id=fiscal_year_id).count()
        reference = f"{journal.code}-{fy.start_date.year}-{count + 1:04d}"

    entry = JournalEntry(
        fiscal_year_id=fiscal_year_id,
        journal_id=journal_id,
        entry_date=entry_date,
        reference=reference,
        description=description,
        is_balanced=True,
        source=source,
        source_ref=source_ref,
    )
    db.session.add(entry)
    db.session.flush()

    for l in lines:
        db.session.add(JournalLine(
            entry_id=entry.id,
            account_id=l["account_id"],
            label=l.get("label", ""),
            debit_cents=l.get("debit_cents", 0),
            credit_cents=l.get("credit_cents", 0),
        ))

    db.session.commit()
    return entry


def account_balance(account_id, start_date=None, end_date=None):
    """Returns (debit_cents, credit_cents) totals for an account."""
    q = db.session.query(
        db.func.coalesce(db.func.sum(JournalLine.debit_cents), 0),
        db.func.coalesce(db.func.sum(JournalLine.credit_cents), 0),
    ).join(JournalEntry).filter(JournalLine.account_id == account_id)
    if start_date:
        q = q.filter(JournalEntry.entry_date >= start_date)
    if end_date:
        q = q.filter(JournalEntry.entry_date <= end_date)
    return q.one()


def trial_balance(fiscal_year_id):
    """
    Returns list of dicts:
      {account, debit_cents, credit_cents, balance_debit, balance_credit}
    Only accounts with movements are included.
    """
    fy = FiscalYear.query.get_or_404(fiscal_year_id)
    rows = (
        db.session.query(
            Account,
            db.func.coalesce(db.func.sum(JournalLine.debit_cents), 0).label("debit"),
            db.func.coalesce(db.func.sum(JournalLine.credit_cents), 0).label("credit"),
        )
        .join(JournalLine, JournalLine.account_id == Account.id)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .filter(JournalEntry.fiscal_year_id == fiscal_year_id)
        .group_by(Account.id)
        .order_by(Account.code)
        .all()
    )
    result = []
    for account, debit, credit in rows:
        net = debit - credit
        result.append({
            "account": account,
            "debit_cents": debit,
            "credit_cents": credit,
            "balance_debit": net if net > 0 else 0,
            "balance_credit": -net if net < 0 else 0,
        })
    return result, fy


def general_ledger(account_id, fiscal_year_id):
    """Returns all journal lines for an account in a fiscal year, with running balance."""
    account = Account.query.get_or_404(account_id)
    lines = (
        JournalLine.query
        .join(JournalEntry)
        .filter(JournalLine.account_id == account_id, JournalEntry.fiscal_year_id == fiscal_year_id)
        .order_by(JournalEntry.entry_date, JournalEntry.id)
        .all()
    )
    running = 0
    rows = []
    for line in lines:
        running += line.debit_cents - line.credit_cents
        rows.append({
            "line": line,
            "entry": line.entry,
            "running_cents": running,
        })
    return account, rows
