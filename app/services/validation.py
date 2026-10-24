"""Validation des écritures (lot F1).

- Une écriture est **validée** quand elle a un numéro (`validation_number`), continu par journal et
  par exercice ; les numéros sont attribués **à la suite** des numéros existants, dans l'ordre
  (date, id) des écritures du lot, et ne changent plus (le FEC reste identique avant et après la
  clôture provisoire).
- Chaque validation forme un **lot** (`validation_batches`) : une sélection, « tout jusqu'au … »,
  la clôture provisoire (ce qui reste), les pièces émises (factures et avoirs de vente, décision
  CO7). Seul le **dernier lot** d'un exercice s'annule (administrateur, motif).
- Écritures en brouillard : comptées pour le tableau de bord et les contrôles de clôture (plus de
  3 mois : rappel).
"""
from datetime import date, datetime, timedelta

from sqlalchemy import func

from app.extensions import db
from app.models import FiscalYear, JournalEntry, ValidationBatch
from app.services import ledger_guard
from app.services.ledger_errors import LedgerError

OLD_DRAFT_DAYS = 90


class ValidationError(LedgerError):
    def __init__(self, message, problems=None):
        super().__init__(message)
        self.problems = problems or []


def drafts(fy: FiscalYear, until: date | None = None):
    query = JournalEntry.query.filter(JournalEntry.fiscal_year_id == fy.id, JournalEntry.validation_number.is_(None))
    if until is not None:
        query = query.filter(JournalEntry.entry_date <= until)
    return query


def problems(entries) -> list[str]:
    """Écritures qui ne peuvent pas être validées (déséquilibrées, sans ligne, hors exercice)."""
    found = []
    for entry in entries:
        label = entry.reference or f"écriture n° {entry.id}"
        debit, credit = entry.total_debit, entry.total_credit
        if not entry.lines:
            found.append(f"{label} : sans ligne.")
        elif debit != credit:
            found.append(f"{label} : déséquilibrée.")
        fy = entry.fiscal_year
        if not (fy.start_date <= entry.entry_date <= fy.end_date):
            found.append(f"{label} : datée hors de l'exercice.")
    return found


def assign(entries, at: datetime) -> int:
    """Numérote les écritures (brouillard) à la suite des numéros de leur journal ; sans lot."""
    todo = sorted((e for e in entries if e.validation_number is None),
                  key=lambda e: (e.fiscal_year_id, e.journal_id, e.entry_date, e.id))
    counters = {}
    with ledger_guard.allow("validation"):
        for entry in todo:
            key = (entry.fiscal_year_id, entry.journal_id)
            if key not in counters:
                counters[key] = db.session.query(func.coalesce(func.max(JournalEntry.validation_number), 0)).filter(
                    JournalEntry.fiscal_year_id == entry.fiscal_year_id,
                    JournalEntry.journal_id == entry.journal_id).scalar()
            counters[key] += 1
            entry.validation_number = counters[key]
            entry.validated_at = at
        db.session.flush()
    return len(todo)


def validate(fy: FiscalYear, entries, kind: str, user_id=None, until: date | None = None,
             at: datetime | None = None) -> ValidationBatch | None:
    """Valide les écritures (brouillard) de l'exercice en un lot ; sans commit. Aucune : None."""
    if fy.is_final:
        raise ValidationError("Exercice clôturé définitivement.")
    entries = [e for e in entries if e.validation_number is None]
    if any(e.fiscal_year_id != fy.id for e in entries):
        raise ValidationError("Les écritures d'un lot appartiennent au même exercice.")
    if not entries:
        return None
    found = problems(entries)
    if found:
        raise ValidationError(f"{len(found)} écriture(s) ne peuvent pas être validées.", found)
    at = at or datetime.utcnow()
    batch = ValidationBatch(fiscal_year_id=fy.id, kind=kind, until_date=until, entries=len(entries),
                            user_id=user_id, at=at)
    db.session.add(batch)
    db.session.flush()
    with ledger_guard.allow("validation"):
        for entry in entries:
            entry.validation_batch_id = batch.id
        assign(entries, at)
    return batch


def validate_until(fy: FiscalYear, until: date, user_id=None) -> ValidationBatch | None:
    return validate(fy, drafts(fy, until).all(), "until", user_id, until=until)


def validate_remaining(fy: FiscalYear, kind="closing", user_id=None, at=None) -> int:
    """Clôture provisoire : valide ce qui reste ; renvoie le nombre d'écritures numérotées de l'exercice."""
    validate(fy, drafts(fy).all(), kind, user_id, until=fy.end_date, at=at)
    return JournalEntry.query.filter_by(fiscal_year_id=fy.id).count()


def validate_issued(entry: JournalEntry, user_id=None) -> None:
    """Écriture d'une pièce émise (facture ou avoir de vente) : validée d'office (CO7). Le dernier lot
    `auto` du jour est complété s'il est encore le dernier lot de l'exercice."""
    fy = entry.fiscal_year
    last = last_batch(fy)
    if last is not None and last.kind == "auto" and last.at.date() == datetime.utcnow().date():
        with ledger_guard.allow("validation"):
            entry.validation_batch_id = last.id
            last.entries += 1
            assign([entry], datetime.utcnow())
        return
    validate(fy, [entry], "auto", user_id)


def last_batch(fy: FiscalYear) -> ValidationBatch | None:
    return (ValidationBatch.query.filter_by(fiscal_year_id=fy.id, undone_at=None)
            .order_by(ValidationBatch.id.desc()).first())


def batches(fy: FiscalYear) -> list[ValidationBatch]:
    return ValidationBatch.query.filter_by(fiscal_year_id=fy.id).order_by(ValidationBatch.id.desc()).all()


def undo_last_batch(fy: FiscalYear, reason: str, user_id=None, kind: str | None = None,
                    allow_locked: bool = False) -> ValidationBatch:
    """Dévalide le dernier lot (administrateur, motif) ; sans commit. `kind` : n'annule que ce type.
    Refusé si une écriture du lot est dans la période verrouillée (sauf réouverture : `allow_locked`)."""
    if fy.is_final:
        raise ValidationError("Exercice clôturé définitivement : la validation est figée.")
    if not (reason or "").strip():
        raise ValidationError("Motif obligatoire.")
    batch = last_batch(fy)
    if batch is None or (kind and batch.kind != kind):
        raise ValidationError("Aucun lot de validation à annuler.")
    if not allow_locked and fy.locked_until is not None and JournalEntry.query.filter(
            JournalEntry.validation_batch_id == batch.id, JournalEntry.entry_date <= fy.locked_until).first():
        raise ValidationError(f"Le lot contient des écritures de la période verrouillée (jusqu'au "
                              f"{fy.locked_until:%d/%m/%Y}) : reculez d'abord le verrou.")
    with ledger_guard.allow("validation"):
        for entry in JournalEntry.query.filter_by(validation_batch_id=batch.id):
            entry.validation_number = None
            entry.validated_at = None
            entry.validation_batch_id = None
        batch.undone_at, batch.undone_by, batch.undo_reason = datetime.utcnow(), user_id, reason.strip()
        db.session.flush()
    return batch


def draft_counts(fy: FiscalYear | None = None, today: date | None = None) -> dict:
    """Brouillards (exercices ouverts, ou un exercice) et ceux de plus de 3 mois."""
    today = today or date.today()
    query = JournalEntry.query.join(FiscalYear).filter(JournalEntry.validation_number.is_(None))
    query = query.filter(JournalEntry.fiscal_year_id == fy.id) if fy else query.filter(FiscalYear.closed.is_(False))
    return {"drafts": query.count(),
            "old": query.filter(JournalEntry.entry_date < today - timedelta(days=OLD_DRAFT_DAYS)).count()}


def batch_payload(batch: ValidationBatch, last_id: int | None = None) -> dict:
    return {"id": batch.id, "kind": batch.kind, "until_date": batch.until_date.isoformat() if batch.until_date else None,
            "entries": batch.entries, "at": batch.at.isoformat(), "user_id": batch.user_id,
            "undone_at": batch.undone_at.isoformat() if batch.undone_at else None,
            "undo_reason": batch.undo_reason, "undoable": batch.id == last_id}
