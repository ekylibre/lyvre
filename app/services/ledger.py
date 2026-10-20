from datetime import date
from app.extensions import db
from app.models import Account, BankTransaction, FiscalYear, Journal, JournalEntry, JournalLine


class LedgerError(Exception):
    pass


def _to_int(value):
    """int for an integer-valued JSON number / numeric string, else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def validate_entry_payload(data):
    """Validate an entry submitted by the entry form / API.

    ``data``: ``{fiscal_year_id, journal_id, entry_date (ISO), description,
    lines: [{account_id, label, debit_cents, credit_cents}]}`` (amounts in
    cents). Completely empty lines (no account, no amount) are ignored.

    Returns ``(clean, errors)``: ``errors`` maps a field (``fiscal_year_id``,
    ``journal_id``, ``entry_date``, ``lines``, ``lines[i].account_id``,
    ``lines[i].amount``) to a message; ``clean`` holds the parsed values
    (``fiscal_year``, ``journal``, ``entry_date``, ``description``, ``lines``
    keeping the index ``i`` of each line in the submitted list).
    """
    errors = {}
    clean = {"description": (data.get("description") or "").strip()}

    fy_id = _to_int(data.get("fiscal_year_id"))
    fy = db.session.get(FiscalYear, fy_id) if fy_id is not None else None
    if fy is None:
        errors["fiscal_year_id"] = "Exercice obligatoire."
    elif fy.closed:
        errors["fiscal_year_id"] = f"L'exercice « {fy.label} » est clôturé."
    clean["fiscal_year"] = fy

    journal_id = _to_int(data.get("journal_id"))
    journal = db.session.get(Journal, journal_id) if journal_id is not None else None
    if journal is None:
        errors["journal_id"] = "Journal obligatoire."
    clean["journal"] = journal

    entry_date = None
    try:
        entry_date = date.fromisoformat(str(data.get("entry_date") or ""))
    except ValueError:
        errors["entry_date"] = "Date obligatoire (AAAA-MM-JJ)."
    if entry_date and fy and not (fy.start_date <= entry_date <= fy.end_date):
        errors["entry_date"] = (
            f"Date hors de l'exercice « {fy.label} » "
            f"({fy.start_date:%d/%m/%Y} → {fy.end_date:%d/%m/%Y})."
        )
    clean["entry_date"] = entry_date

    raw_lines = data.get("lines")
    if not isinstance(raw_lines, list):
        raw_lines = []
    lines = []
    for i, raw in enumerate(raw_lines):
        if not isinstance(raw, dict):
            continue
        account_id = _to_int(raw.get("account_id"))
        debit = _to_int(raw.get("debit_cents") or 0)
        credit = _to_int(raw.get("credit_cents") or 0)
        if account_id is None and not debit and not credit:
            continue  # empty line

        account = db.session.get(Account, account_id) if account_id is not None else None
        if account is None:
            errors[f"lines[{i}].account_id"] = "Compte obligatoire."
        elif account.is_header:
            errors[f"lines[{i}].account_id"] = (
                f"Le compte {account.code} est un compte de regroupement, non utilisable."
            )
        if debit is None or credit is None or debit < 0 or credit < 0:
            errors[f"lines[{i}].amount"] = "Montant invalide."
        elif bool(debit) == bool(credit):
            errors[f"lines[{i}].amount"] = "Saisir soit un débit, soit un crédit."
        lines.append({
            "index": i,
            "account_id": account_id,
            "label": (raw.get("label") or "").strip(),
            "debit_cents": debit or 0,
            "credit_cents": credit or 0,
        })
    clean["lines"] = lines

    if len(lines) < 2:
        errors["lines"] = "Une écriture doit avoir au moins deux lignes."
    else:
        total_debit = sum(l["debit_cents"] for l in lines)
        total_credit = sum(l["credit_cents"] for l in lines)
        if total_debit != total_credit:
            gap = abs(total_debit - total_credit) / 100
            errors["lines"] = f"Écriture déséquilibrée (écart de {gap:.2f} €)."
        elif total_debit == 0:
            errors["lines"] = "Le total de l'écriture ne peut pas être nul."
    return clean, errors


def entry_is_reconciled(entry):
    """True if one of the entry lines is linked to a bank transaction."""
    line_ids = [l.id for l in entry.lines]
    return bool(line_ids) and db.session.query(
        BankTransaction.query.filter(BankTransaction.journal_line_id.in_(line_ids)).exists()
    ).scalar()


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


def post_entry(fiscal_year_id, journal_id, entry_date, description, lines, source="MANUAL", source_ref=None, reference=None, commit=True):
    """
    Create a balanced journal entry.
    lines: list of dicts with keys: account_id, label, debit_cents, credit_cents
    Returns the created JournalEntry. ``commit=False`` only flushes, so the
    caller can include it in a larger transaction.
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

    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return entry


def post_validated_entry(clean, bank_transaction=None):
    """Create the entry from ``validate_entry_payload`` output.

    With ``bank_transaction``, the entry line on the bank account is reconciled
    with it **in the same transaction**: if the entry has no matching bank line
    (same account, same amount and direction), nothing is saved.
    """
    from app.services.reconciler import reconcile

    try:
        entry = post_entry(
            clean["fiscal_year"].id, clean["journal"].id, clean["entry_date"],
            clean["description"], clean["lines"], commit=False,
        )
        if bank_transaction is not None:
            if bank_transaction.reconciled:
                raise LedgerError("La transaction bancaire est déjà rapprochée.")
            account_id = bank_transaction.bank_account.account_id
            bank_line = next(
                (l for l in entry.lines
                 if l.account_id == account_id
                 and l.debit_cents - l.credit_cents == bank_transaction.amount_cents),
                None,
            )
            if bank_line is None:
                raise LedgerError(
                    "L'écriture doit contenir une ligne sur le compte bancaire "
                    "du même montant que la transaction."
                )
            reconcile(bank_transaction.id, bank_line.id, commit=False)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return entry


def update_entry(entry, clean):
    """Replace an entry header and lines with ``validate_entry_payload`` output.

    Refused (LedgerError) if the entry belongs to a closed fiscal year or is
    reconciled with a bank transaction.
    """
    if entry.fiscal_year.closed:
        raise LedgerError("Impossible de modifier une écriture d'un exercice clôturé.")
    if entry_is_reconciled(entry):
        raise LedgerError(
            "Cette écriture est rapprochée à une transaction bancaire. "
            "Annulez le rapprochement avant de la modifier."
        )
    try:
        for line in list(entry.lines):
            db.session.delete(line)
        db.session.flush()

        entry.fiscal_year_id = clean["fiscal_year"].id
        entry.journal_id = clean["journal"].id
        entry.entry_date = clean["entry_date"]
        entry.description = clean["description"]
        entry.is_balanced = True
        for l in clean["lines"]:
            db.session.add(JournalLine(
                entry_id=entry.id,
                account_id=l["account_id"],
                label=l["label"],
                debit_cents=l["debit_cents"],
                credit_cents=l["credit_cents"],
            ))
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
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


def delete_entries(entry_ids):
    """Delete entries in one transaction, undoing their bank reconciliations
    first (a deleted line must not stay linked to a bank transaction).

    Entries of a closed fiscal year are refused. Returns
    ``[{entry_id, status, reference?, message?}]``.
    """
    results = []
    for entry_id in entry_ids:
        entry = db.session.get(JournalEntry, entry_id) if isinstance(entry_id, int) else None
        if entry is None:
            results.append({"entry_id": entry_id, "status": "error",
                            "message": "Écriture introuvable."})
            continue
        if entry.fiscal_year.closed:
            results.append({"entry_id": entry_id, "status": "error",
                            "message": "Exercice clôturé : suppression impossible."})
            continue
        line_ids = [l.id for l in entry.lines]
        if line_ids:
            BankTransaction.query.filter(BankTransaction.journal_line_id.in_(line_ids)).update(
                {"journal_line_id": None, "reconciled": False}, synchronize_session="fetch")
        results.append({"entry_id": entry_id, "status": "ok", "reference": entry.reference})
        db.session.delete(entry)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return results
