"""Garde des écritures (lot F1) et historique.

Au `before_flush` de toute session, quel que soit le chemin (saisie, encaissement, règlement, mode
simplifié, clôture, projets…) :

- une écriture **validée** (numéro déjà enregistré) ne se modifie ni ne se supprime ; ses lignes ne
  s'ajoutent, ne se suppriment ni ne changent, sauf les colonnes libres (`FREE_LINE_COLUMNS` :
  projet, tiers, lettrage) ;
- les colonnes de validation ne changent que dans le contexte `validation` (`allow("validation")`,
  ouvert par `app/services/validation.py` seulement).

Refus : `LedgerGuardError` (API 409, code `entry_validated`).

Historique (`entry_events`) : après chaque flush qui touche une écriture, son état complet
(en-tête et lignes) est enregistré ; dans une même transaction, création puis ajout des lignes
donnent un seul événement.
"""
import json
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime

from sqlalchemy import event, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from app.models import Account, EntryEvent, Journal, JournalEntry, JournalLine
from app.services.ledger_errors import LedgerGuardError

FREE_LINE_COLUMNS = frozenset({"project_id", "entity_id", "lettering_id"})
VALIDATION_COLUMNS = frozenset({"validation_number", "validated_at", "validation_batch_id"})
VALIDATED_MESSAGE = "Écriture validée : elle ne se modifie plus ; contrepassez-la pour la corriger."

_allowed: ContextVar[frozenset] = ContextVar("ledger_guard_allowed", default=frozenset())
_PENDING = "ledger_guard_pending"   # session.info : écritures à historiser après le flush
_EVENTS = "ledger_guard_events"     # session.info : {entry_id: (event_id, action)} de la transaction


@contextmanager
def allow(*names):
    """Ouvre un contexte (`validation`) pour le bloc ; réservé aux services concernés."""
    token = _allowed.set(_allowed.get() | frozenset(names))
    try:
        yield
    finally:
        _allowed.reset(token)


def _committed(obj, key):
    """Valeur en base d'un attribut (avant les changements de la session)."""
    history = sa_inspect(obj).attrs[key].history
    if history.deleted:
        return history.deleted[0]
    if history.unchanged:
        return history.unchanged[0]
    return None


def _changed(obj) -> set[str]:
    state = sa_inspect(obj)
    return {attr.key for attr in state.mapper.column_attrs if state.attrs[attr.key].history.has_changes()}


def _was_validated(entry) -> bool:
    if entry is None or sa_inspect(entry).pending or sa_inspect(entry).transient:
        return False
    return _committed(entry, "validation_number") is not None


def _entry_of(session, line):
    if line.entry is not None:
        return line.entry
    return session.get(JournalEntry, line.entry_id) if line.entry_id else None


@event.listens_for(Session, "before_flush")
def _guard(session, flush_context, instances):
    allowed = _allowed.get()
    pending = session.info.setdefault(_PENDING, {})
    with session.no_autoflush:
        deleted_entries = {id(o) for o in session.deleted if isinstance(o, JournalEntry)}
        for obj in session.new:
            if isinstance(obj, JournalEntry):
                pending[id(obj)] = (obj, "create", None)
            elif isinstance(obj, JournalLine):
                entry = _entry_of(session, obj)
                if _was_validated(entry):
                    raise LedgerGuardError(VALIDATED_MESSAGE)
                if entry is not None:
                    pending.setdefault(id(entry), (entry, "update", None))
        for obj in session.dirty:
            if isinstance(obj, JournalEntry):
                changed = _changed(obj)
                if not changed:
                    continue
                if changed & VALIDATION_COLUMNS and "validation" not in allowed:
                    raise LedgerGuardError("La numérotation de validation est attribuée par la validation des écritures.")
                if _was_validated(obj) and changed - VALIDATION_COLUMNS:
                    raise LedgerGuardError(VALIDATED_MESSAGE)
                before, after = _committed(obj, "validation_number"), obj.validation_number
                if before is None and after is not None:
                    action = "validate"
                elif before is not None and after is None:
                    action = "unvalidate"
                elif changed - VALIDATION_COLUMNS:
                    action = "update"
                else:
                    continue  # rattachement à un lot, sans changement de numéro
                if id(obj) not in pending or action != "update":
                    pending[id(obj)] = (obj, action, None)
            elif isinstance(obj, JournalLine):
                significant = _changed(obj) - FREE_LINE_COLUMNS
                if not significant:
                    continue
                entry = _entry_of(session, obj)
                if _was_validated(entry):
                    raise LedgerGuardError(VALIDATED_MESSAGE)
                if entry is not None:
                    pending.setdefault(id(entry), (entry, "update", None))
        for obj in session.deleted:
            if isinstance(obj, JournalEntry):
                if _was_validated(obj):
                    raise LedgerGuardError(VALIDATED_MESSAGE)
                pending[id(obj)] = (obj, "delete", _snapshot(session, obj.id))
            elif isinstance(obj, JournalLine):
                entry = _entry_of(session, obj)
                if entry is None or id(entry) in deleted_entries:
                    continue
                if _was_validated(entry):
                    raise LedgerGuardError(VALIDATED_MESSAGE)
                pending.setdefault(id(entry), (entry, "update", None))


def _connection(session):
    return session.connection(bind_arguments={"mapper": sa_inspect(JournalEntry)})


def _snapshot(session, entry_id):
    """État de l'écriture lu en base (requêtes directes : voit ce que le flush vient d'écrire)."""
    conn = _connection(session)
    entries, journals, lines, accounts = (JournalEntry.__table__, Journal.__table__, JournalLine.__table__,
                                          Account.__table__)
    head = conn.execute(
        select(entries.c.reference, entries.c.entry_date, entries.c.description, entries.c.source,
               entries.c.fiscal_year_id, entries.c.validation_number, journals.c.code)
        .select_from(entries.outerjoin(journals, journals.c.id == entries.c.journal_id))
        .where(entries.c.id == entry_id)).first()
    if head is None:
        return None
    rows = conn.execute(
        select(accounts.c.code, lines.c.label, lines.c.debit_cents, lines.c.credit_cents, lines.c.project_id)
        .select_from(lines.join(accounts, accounts.c.id == lines.c.account_id))
        .where(lines.c.entry_id == entry_id).order_by(lines.c.id)).all()
    return {
        "reference": head.reference, "entry_date": head.entry_date.isoformat() if head.entry_date else None,
        "journal": head.code, "description": head.description or "", "source": head.source,
        "fiscal_year_id": head.fiscal_year_id, "validation_number": head.validation_number,
        "lines": [{"account": r.code, "label": r.label or "", "debit_cents": r.debit_cents,
                   "credit_cents": r.credit_cents, "project_id": r.project_id} for r in rows],
    }


def _author():
    """(utilisateur, origine) de la requête en cours, sinon tâche de fond."""
    try:
        from flask import g, has_request_context, request
        if has_request_context():
            # Utilisateur déjà chargé par la requête seulement : le charger ici le figerait (anonyme)
            # dans `g` pour la suite du contexte d'application.
            user = getattr(g, "_login_user", None)
            user_id = user.id if user is not None and getattr(user, "is_authenticated", False) else None
            return user_id, f"api:{request.endpoint}"[:60]
    except Exception:  # pragma: no cover - hors application
        pass
    return None, "job"


@event.listens_for(Session, "after_flush")
def _history(session, flush_context):
    pending = session.info.pop(_PENDING, None)
    if not pending:
        return
    events = session.info.setdefault(_EVENTS, {})
    table = EntryEvent.__table__
    conn = _connection(session)
    user_id, origin = _author()
    now = datetime.utcnow()
    for obj, action, before in pending.values():
        entry_id = obj.id
        snapshot = before if action == "delete" else _snapshot(session, entry_id)
        if snapshot is None:
            continue
        known = events.get(entry_id)
        if known and action in ("update", "create") and known[1] in ("create", "update"):
            conn.execute(table.update().where(table.c.id == known[0]).values(snapshot_json=json.dumps(snapshot)))
            continue
        result = conn.execute(table.insert().values(
            entry_id=entry_id, fiscal_year_id=snapshot["fiscal_year_id"], reference=snapshot["reference"],
            action=action, snapshot_json=json.dumps(snapshot), user_id=user_id, origin=origin, at=now))
        events[entry_id] = (result.inserted_primary_key[0], action)


@event.listens_for(Session, "after_commit")
@event.listens_for(Session, "after_soft_rollback")
def _forget(session, *args):
    session.info.pop(_EVENTS, None)
    session.info.pop(_PENDING, None)
