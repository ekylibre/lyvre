"""Verrouillage des périodes (lot F2).

Une **date de verrouillage** par exercice (`fiscal_years.locked_until`) : aucune écriture ne se crée,
ne se modifie ni ne se supprime à une date antérieure ou égale (garde des écritures), sauf celles
de l'assistant de clôture. Les pièces reçues (synchronisations, règles, encaissements rapprochés)
passent à la première date ouverte (`ledger.post_entry(auto_date=True)`).

- **Avancer** (trésorier ou administrateur) : les écritures en brouillard jusqu'à la date sont
  validées dans le même geste (lot `lock`) ; refus si l'une ne peut pas l'être.
- **Reculer** (administrateur, motif) : ne dévalide rien ; journalisé dans `closing_events`.
- Clôture provisoire : verrou au dernier jour ; réouverture : date d'avant la clôture rétablie.
"""
import json
from datetime import date

from app.extensions import db
from app.models import ClosingEvent, FiscalYear
from app.services import validation
from app.services.ledger_errors import LedgerError


class LockError(LedgerError):
    def __init__(self, message, field=None, problems=None):
        super().__init__(message)
        self.field = field
        self.problems = problems or []


def _log(fy, action, user_id, **details):
    db.session.add(ClosingEvent(fiscal_year_id=fy.id, step="lock", action=action, user_id=user_id,
                                details_json=json.dumps(details, default=str, ensure_ascii=False)))


def payload(fy: FiscalYear) -> dict:
    return {"locked_until": fy.locked_until.isoformat() if fy.locked_until else None,
            "first_open_date": fy.first_open_date.isoformat() if fy.first_open_date else None}


def _check_date(fy, until):
    if not isinstance(until, date):
        raise LockError("Date invalide.", "until")
    if fy.status != "open":
        raise LockError("Exercice clôturé : son verrou suit la clôture.")
    if not (fy.start_date <= until <= fy.end_date):
        raise LockError(f"Date hors de l'exercice ({fy.start_date:%d/%m/%Y} → {fy.end_date:%d/%m/%Y}).", "until")


def preview(fy: FiscalYear, until: date) -> dict:
    """Brouillards qui seront validés en verrouillant jusqu'à `until`, et ceux qui l'empêchent."""
    drafts = validation.drafts(fy, until).all()
    return {"drafts": len(drafts), "problems": validation.problems(drafts)[:20]}


def advance(fy: FiscalYear, until: date, user_id=None) -> int:
    """Verrouille jusqu'à `until` et valide les brouillards de la période (sans commit) ; renvoie leur nombre."""
    _check_date(fy, until)
    if fy.locked_until is not None and until <= fy.locked_until:
        raise LockError(f"Déjà verrouillé jusqu'au {fy.locked_until:%d/%m/%Y} : reculer la date est réservé à "
                        "l'administrateur.", "until")
    try:
        batch = validation.validate(fy, validation.drafts(fy, until).all(), "lock", user_id, until=until)
    except validation.ValidationError as exc:
        raise LockError(str(exc), problems=exc.problems) from None
    previous = fy.locked_until
    fy.locked_until = until
    _log(fy, "advance", user_id, previous=previous, until=until, validated=batch.entries if batch else 0)
    db.session.flush()
    return batch.entries if batch else 0


def rewind(fy: FiscalYear, until: date | None, reason: str, user_id=None) -> None:
    """Recule (ou retire, `until` None) la date de verrouillage ; motif obligatoire (sans commit)."""
    if not (reason or "").strip():
        raise LockError("Motif obligatoire.", "reason")
    if fy.status != "open":
        raise LockError("Exercice clôturé : rouvrez-le avec l'assistant de clôture.")
    if fy.locked_until is None:
        raise LockError("Exercice non verrouillé.")
    if until is not None:
        _check_date(fy, until)
        if until >= fy.locked_until:
            raise LockError("Pour avancer le verrou, utilisez « Verrouiller ».", "until")
    previous = fy.locked_until
    fy.locked_until = until
    _log(fy, "rewind", user_id, previous=previous, until=until, reason=reason.strip())
    db.session.flush()


def on_provisional_close(fy: FiscalYear) -> None:
    fy.lock_before_close = fy.locked_until
    fy.locked_until = fy.end_date


def on_reopen(fy: FiscalYear) -> None:
    fy.locked_until = fy.lock_before_close
    fy.lock_before_close = None
