from datetime import date
from app.extensions import db
from app.models import (
    Account, AssociateExpense, BankTransaction, FiscalYear, Journal, JournalEntry, JournalLine, Purchase,
    PurchasePayment,
)
from app.models.journal_entry import MANAGED_SOURCES, SALE_LOCKED_MESSAGE, SOURCE_CANCELLATION, SOURCE_SALE
from app.services import projects, vat_codes
from app.services.ledger_errors import LedgerError, LedgerGuardError, period_locked  # noqa: F401 (réexportés)


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
    lines: [{account_id, label, debit_cents, credit_cents, project_id?}]}`` (amounts in
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
        try:
            project = projects.resolve(raw.get("project_id"))
        except ValueError as exc:
            errors[f"lines[{i}].project_id"] = str(exc)
            project = None
        # Lot F4 : période de service facultative (charges et produits constatés d'avance).
        period = []
        for key in ("service_start", "service_end"):
            try:
                period.append(date.fromisoformat(raw[key]) if raw.get(key) else None)
            except (TypeError, ValueError):
                errors[f"lines[{i}].{key}"] = "Date invalide (AAAA-MM-JJ)."
                period.append(None)
        if bool(period[0]) != bool(period[1]) or (period[0] and period[1] < period[0]):
            errors[f"lines[{i}].service_end"] = "Période : début et fin, la fin suivant le début."
        # Lot T2 : code de TVA et base HT (ligne de taxe), facultatifs.
        vat_code = (raw.get("vat_code") or "").strip() or None
        vat_base = _to_int(raw.get("vat_base_cents")) if raw.get("vat_base_cents") not in (None, "") else None
        if vat_code is not None and not vat_codes.is_known(vat_code):
            errors[f"lines[{i}].vat_code"] = f"Code de TVA inconnu : {vat_code}."
        if vat_base is not None and (vat_base < 0 or vat_code is None):
            errors[f"lines[{i}].vat_base_cents"] = "Base HT : un montant positif, avec un code de TVA."
        analytic = None
        if raw.get("analytic"):                                  # lot AG8.c : affectation analytique de la ligne
            from app.services.analytic import AnalyticError
            from app.services.analytic_allocation import parse_target
            try:
                analytic = parse_target(raw.get("analytic"))
            except AnalyticError as exc:
                errors[f"lines[{i}].analytic"] = exc.message
        lines.append({
            "index": i,
            "analytic": analytic,
            "account_id": account_id,
            "label": (raw.get("label") or "").strip(),
            "debit_cents": debit or 0,
            "credit_cents": credit or 0,
            "project_id": project.id if project else None,
            "service_start": period[0],
            "service_end": period[1],
            "vat_code": vat_code,
            "vat_base_cents": vat_base if vat_code else None,
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


def next_reference(journal_id, fy):
    """« AC-2026-0007 » : numéro suivant le plus grand du journal et de l'exercice
    (un compte des écritures redonnerait un numéro déjà pris après une suppression)."""
    journal = db.session.get(Journal, journal_id)
    prefix = f"{journal.code}-{fy.start_date.year}-"
    references = db.session.query(JournalEntry.reference).filter(
        JournalEntry.journal_id == journal_id, JournalEntry.fiscal_year_id == fy.id,
        JournalEntry.reference.like(f"{prefix}%"))
    numbers = [int(ref[len(prefix):]) for (ref,) in references if ref[len(prefix):].isdigit()]
    return f"{prefix}{max(numbers, default=0) + 1:04d}"


def shifted_date(fy, entry_date):
    """Pièce reçue datée dans une période verrouillée (lot F2, CO8) : (exercice, première date ouverte),
    dans l'exercice suivant si besoin ; LedgerGuardError si aucun exercice ouvert ne suit."""
    if fy.locked_until is None or entry_date > fy.locked_until:
        return fy, entry_date
    first = fy.first_open_date
    if first is not None:
        return fy, first
    following = (FiscalYear.query.filter(FiscalYear.start_date > fy.end_date, FiscalYear.closed.is_(False))
                 .order_by(FiscalYear.start_date).first())
    if following is None:
        raise period_locked(fy, entry_date)
    return shifted_date(following, following.start_date)


def post_entry(fiscal_year_id, journal_id, entry_date, description, lines, source="MANUAL", source_ref=None,
               reference=None, commit=True, auto_date=False):
    """
    Create a balanced journal entry.
    lines: list of dicts with keys: account_id, label, debit_cents, credit_cents
    Returns the created JournalEntry. ``commit=False`` only flushes, so the
    caller can include it in a larger transaction.

    Lot F2 : une date verrouillée est refusée (`period_locked`), sauf ``auto_date`` (pièce reçue,
    écriture automatique) : l'écriture passe à la première date ouverte, la date d'origine en tête
    du libellé.
    """
    fy = db.session.get(FiscalYear, fiscal_year_id)
    if fy is None:
        raise LedgerError("Exercice introuvable.")
    if fy.closed:
        raise LedgerError(f"L'exercice « {fy.label} » est clôturé.")
    if source not in MANAGED_SOURCES and fy.locked_until is not None and entry_date <= fy.locked_until:
        if not auto_date:
            raise period_locked(fy, entry_date)
        original = entry_date
        fy, entry_date = shifted_date(fy, entry_date)
        fiscal_year_id = fy.id
        description = f"[pièce du {original:%d/%m/%Y}] {description or ''}".strip()[:500]

    validate_lines(lines)

    if reference is None:
        reference = next_reference(journal_id, fy)

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

    created = []
    for l in lines:
        line = JournalLine(
            entry_id=entry.id,
            account_id=l["account_id"],
            label=l.get("label", ""),
            debit_cents=l.get("debit_cents", 0),
            credit_cents=l.get("credit_cents", 0),
            project_id=l.get("project_id"),
            entity_id=l.get("entity_id"),
            carried_from_line_id=l.get("carried_from_line_id"),
            service_start=l.get("service_start"),
            service_end=l.get("service_end"),
            vat_code=l.get("vat_code"),
            vat_base_cents=l.get("vat_base_cents"),
        )
        db.session.add(line)
        created.append((line, l))
    _attach_analytic(created)

    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return entry


def _attach_analytic(created) -> None:
    """Lot AG8.c : ventilation analytique des lignes passées avec une clé « analytic » (« activity:ID » / « key:ID »)."""
    wanted = [(line, l) for line, l in created if l.get("analytic")]
    if not wanted:
        return
    from app.services.analytic_allocation import attach
    db.session.flush()
    for line, l in wanted:
        row = attach(line, l["analytic"], l.get("analytic_origin", "manual"))
        if row is not None and l.get("analytic_campaign"):
            row.campaign_year = l["analytic_campaign"]


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
            if bank_transaction.is_reversed:
                from app.services.reconciler import REVERSED_MESSAGE
                raise LedgerError(REVERSED_MESSAGE)
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
    if entry.is_validated:
        raise LedgerGuardError(VALIDATED_MESSAGE)
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
        created = []
        for l in clean["lines"]:
            line = JournalLine(
                entry_id=entry.id,
                account_id=l["account_id"],
                label=l["label"],
                debit_cents=l["debit_cents"],
                credit_cents=l["credit_cents"],
                project_id=l.get("project_id"),
                service_start=l.get("service_start"),
                service_end=l.get("service_end"),
                vat_code=l.get("vat_code"),
                vat_base_cents=l.get("vat_base_cents"),
            )
            db.session.add(line)
            created.append((line, l))
        _attach_analytic(created)
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


VALIDATED_MESSAGE = "Écriture validée : elle ne se modifie plus ; contrepassez-la pour la corriger."


def open_fiscal_year_for(on_date):
    """Exercice non clôturé contenant la date, ou None."""
    return FiscalYear.query.filter(FiscalYear.closed.is_(False), FiscalYear.start_date <= on_date,
                                   FiscalYear.end_date >= on_date).first()


def _detach(entry):
    """L'écriture ne compte plus (supprimée ou contrepassée) : ses rapprochements sont défaits, la facture
    d'achat, le règlement ou la note de frais adossés redeviennent à comptabiliser, ses encaissements de
    vente disparaissent (sans commit)."""
    line_ids = [l.id for l in entry.lines]
    if line_ids:
        BankTransaction.query.filter(BankTransaction.journal_line_id.in_(line_ids)).update(
            {"journal_line_id": None, "reconciled": False}, synchronize_session="fetch")
        from app.services import lettering
        lettering.release(line_ids)  # lot F3 : lettrages des lignes défaits
    # SQLite n'applique pas les ON DELETE SET NULL.
    for model in (Purchase, PurchasePayment, AssociateExpense):
        model.query.filter(model.journal_entry_id == entry.id).update(
            {"journal_entry_id": None}, synchronize_session="fetch")
    from app.services.sale_settlement import forget_entry_payments
    forget_entry_payments(entry.id)


def reversal_of(entry):
    """Contrepassation de l'écriture, s'il y en a une."""
    return JournalEntry.query.filter_by(reverses_entry_id=entry.id, source=SOURCE_CANCELLATION).first()


def reverse(entry, on_date=None, reason=None, user_id=None, commit=True):
    """Contrepasse l'écriture (lot F1) : écriture inverse au même journal, liée par `reverses_entry_id`,
    datée du jour (ou de `on_date`) dans un exercice ouvert ; l'écriture d'origine est détachée
    (`_detach`). Renvoie la contrepassation."""
    if entry.source == SOURCE_SALE:
        raise LedgerError(SALE_LOCKED_MESSAGE)
    if entry.source in MANAGED_SOURCES:
        raise LedgerError("Écriture gérée par l'assistant de clôture : corrigez-la depuis l'assistant.")
    if entry.source == SOURCE_CANCELLATION:
        raise LedgerError("Cette écriture est une contrepassation.")
    if reversal_of(entry) is not None:
        raise LedgerError("Écriture déjà contrepassée.")
    if entry.fiscal_year.closed and on_date is None and open_fiscal_year_for(date.today()) is None:
        raise LedgerError("Exercice clôturé et aucun exercice ouvert aujourd'hui : contrepassation impossible.")
    on_date = on_date or date.today()
    fy = open_fiscal_year_for(on_date)
    if fy is None and not entry.fiscal_year.closed and on_date > entry.fiscal_year.end_date:
        fy, on_date = entry.fiscal_year, entry.fiscal_year.end_date
    if fy is None:
        raise LedgerError(f"Aucun exercice ouvert au {on_date:%d/%m/%Y} pour la contrepassation.")
    description = f"Contrepassation de {entry.reference or entry.id}"
    if (reason or "").strip():
        description += f" — {reason.strip()}"
    lines = [{"account_id": l.account_id, "label": l.label or "", "debit_cents": l.credit_cents,
              "credit_cents": l.debit_cents, "project_id": l.project_id,
              "vat_code": l.vat_code, "vat_base_cents": l.vat_base_cents} for l in entry.lines]
    try:
        reversal = post_entry(fy.id, entry.journal_id, on_date, description[:500], lines,
                              source=SOURCE_CANCELLATION, source_ref=f"entry:{entry.id}", commit=False)
        reversal.reverses_entry_id = entry.id
        for original, inverse in zip(sorted(entry.lines, key=lambda l: l.id),
                                     sorted(reversal.lines, key=lambda l: l.id)):
            inverse.entity_id = original.entity_id
        _detach(entry)
        # Lot F3 : chaque ligne de tiers lettrée avec sa ligne inverse.
        from app.services import lettering
        db.session.flush()
        for original, inverse in zip(sorted(entry.lines, key=lambda l: l.id),
                                     sorted(reversal.lines, key=lambda l: l.id)):
            if original.account.lettrable:
                lettering.letter([original, inverse], origin="reversal", user_id=user_id)
        from app.models import EntryEvent
        from app.services.ledger_guard import _author
        author, origin = _author()
        db.session.add(EntryEvent(entry_id=entry.id, fiscal_year_id=entry.fiscal_year_id, reference=entry.reference,
                                  action="reverse", user_id=user_id or author, origin=origin,
                                  snapshot_json=None))
        if commit:
            db.session.commit()
        else:
            db.session.flush()
    except Exception:
        if commit:
            db.session.rollback()
        raise
    return reversal


def reversed_entry_ids():
    """Requête des écritures contrepassées (à exclure de ce qui « compte encore »)."""
    return db.session.query(JournalEntry.reverses_entry_id).filter(
        JournalEntry.source == SOURCE_CANCELLATION, JournalEntry.reverses_entry_id.isnot(None))


def remove_entry(entry):
    """Retire l'écriture remplacée par une autre (écriture de règle remplacée par un règlement…) :
    supprimée en brouillard, contrepassée si validée (sans commit). Renvoie la contrepassation."""
    if entry.is_validated:
        return reverse(entry, commit=False)
    db.session.delete(entry)
    return None


def delete_entries(entry_ids, allow_managed=False, reverse_validated=False):
    """Delete entries in one transaction, undoing their bank reconciliations
    first (a deleted line must not stay linked to a bank transaction).

    Entries of a closed fiscal year are refused, and so are entries managed by
    the closing wizard unless ``allow_managed``. A validated entry is refused,
    or reversed when ``reverse_validated`` (services that redo a document's entry:
    purchase reposted, payment undone…). Returns
    ``[{entry_id, status, reference?, message?}]`` (status ``ok``, ``reversed`` or ``error``).
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
        if entry.source in MANAGED_SOURCES and not allow_managed:
            results.append({"entry_id": entry_id, "status": "error",
                            "message": "écriture gérée par l'assistant de clôture."})
            continue
        if entry.source == SOURCE_SALE:
            results.append({"entry_id": entry_id, "status": "error", "message": SALE_LOCKED_MESSAGE})
            continue
        fy = entry.fiscal_year
        if not entry.is_validated and fy.locked_until and entry.entry_date <= fy.locked_until \
                and entry.source not in MANAGED_SOURCES:
            results.append({"entry_id": entry_id, "status": "error",
                            "message": f"période verrouillée jusqu'au {fy.locked_until:%d/%m/%Y}."})
            continue
        if entry.is_validated:
            if not reverse_validated:
                results.append({"entry_id": entry_id, "status": "error",
                                "message": "écriture validée : contrepassez-la."})
                continue
            try:
                reversal = reverse(entry, commit=False)
            except LedgerError as exc:
                results.append({"entry_id": entry_id, "status": "error", "message": str(exc)})
                continue
            results.append({"entry_id": entry_id, "status": "reversed", "reference": entry.reference,
                            "reversal": reversal.reference})
            continue
        _detach(entry)
        results.append({"entry_id": entry_id, "status": "ok", "reference": entry.reference})
        db.session.delete(entry)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return results
