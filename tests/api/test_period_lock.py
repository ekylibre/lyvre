"""Lot F2 : verrouillage des périodes (date de verrouillage, validation des brouillards, décalage des
pièces reçues, recul par l'administrateur, clôture et réouverture)."""
from datetime import date

import pytest

from app.extensions import db
from app.models import (
    Account, BankAccount, BankTransaction, ClosingEvent, FiscalYear, Journal, JournalEntry, ValidationBatch,
)
from app.services import closing, period_lock, validation
from app.services.ledger import LedgerGuardError, post_entry, shifted_date


def _error(resp, status):
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()["error"]


@pytest.fixture()
def books(app, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "instance_path", str(tmp_path))
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    accounts = [Account(code=c, label=f"Compte {c}", account_type="OTHER") for c in ("512100", "6061", "706")]
    db.session.add_all([fy, Journal(code="BQ", label="Banque"), *accounts])
    db.session.commit()
    return fy


def _entry(fy, day, cents=1000, desc="Vente", **kw):
    a = {x.code: x.id for x in Account.query.all()}
    return post_entry(fy.id, Journal.query.one().id, day, desc, [
        {"account_id": a["512100"], "debit_cents": cents}, {"account_id": a["706"], "credit_cents": cents}], **kw)


def test_advance_validates_drafts_and_locks(books, login_as):
    march = _entry(books, date(2026, 3, 1), desc="mars")
    _entry(books, date(2026, 5, 1), desc="mai")
    client = login_as()
    base = f"/api/v1/fiscal-years/{books.id}/period-lock"
    assert client.get(f"{base}?until=2026-03-31").get_json()["preview"] == {"drafts": 1, "problems": []}
    resp = client.post(base, json={"until": "2026-03-31"})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["item"]["locked_until"] == "2026-03-31"
    assert resp.get_json()["item"]["first_open_date"] == "2026-04-01"
    db.session.refresh(march)
    assert march.is_validated and ValidationBatch.query.one().kind == "lock"
    assert JournalEntry.query.filter_by(description="mai").one().validation_number is None
    # Reculer avec « Verrouiller » : refusé ; date hors exercice : refusée.
    assert "administrateur" in _error(client.post(base, json={"until": "2026-02-01"}), 422)["message"]
    _error(client.post(base, json={"until": "2027-01-15"}), 422)
    assert ClosingEvent.query.filter_by(step="lock", action="advance").count() == 1


def test_locked_period_refuses_every_change(books, login_as):
    _entry(books, date(2026, 3, 1))
    period_lock.advance(books, date(2026, 3, 31))
    db.session.commit()
    with pytest.raises(LedgerGuardError) as exc:
        _entry(books, date(2026, 3, 15))
    assert exc.value.code == "period_locked" and exc.value.first_open_date == date(2026, 4, 1)
    db.session.rollback()
    client = login_as()
    a = {x.code: x.id for x in Account.query.all()}
    payload = {"fiscal_year_id": books.id, "journal_id": Journal.query.one().id, "entry_date": "2026-03-20",
               "lines": [{"account_id": a["512100"], "debit_cents": 500}, {"account_id": a["706"], "credit_cents": 500}]}
    error = _error(client.post("/api/v1/entries", json=payload), 409)
    assert "01/04/2026" in error["message"]
    # Brouillard d'avril déplacé en mars : refusé (nouvelle date verrouillée).
    april = _entry(books, date(2026, 4, 2))
    april.entry_date = date(2026, 3, 30)
    with pytest.raises(LedgerGuardError):
        db.session.flush()
    db.session.rollback()
    assert client.get(f"/api/v1/entries/{april.id}").get_json()["locked_until"] is None


def test_received_documents_shift_to_first_open_date(books):
    period_lock.advance(books, date(2026, 3, 31))
    db.session.commit()
    entry = _entry(books, date(2026, 2, 10), desc="Facture EDF", auto_date=True)
    assert entry.entry_date == date(2026, 4, 1) and entry.description == "[pièce du 10/02/2026] Facture EDF"
    # Exercice entièrement verrouillé : exercice suivant ouvert, sinon refus.
    period_lock.advance(books, date(2026, 12, 31))
    db.session.commit()
    with pytest.raises(LedgerGuardError):
        shifted_date(books, date(2026, 6, 1))
    following = FiscalYear(label="2027", start_date=date(2027, 1, 1), end_date=date(2027, 12, 31))
    db.session.add(following)
    db.session.commit()
    assert shifted_date(books, date(2026, 6, 1)) == (following, date(2027, 1, 1))


def test_bank_rule_on_locked_transaction(books):
    a = {x.code: x for x in Account.query.all()}
    ba = BankAccount(label="Banque", account_id=a["512100"].id)
    db.session.add(ba)
    db.session.flush()
    txn = BankTransaction(bank_account_id=ba.id, fitid="T1", transaction_date=date(2026, 2, 3), amount_cents=-4200,
                          label="PRLV EDF")
    db.session.add(txn)
    db.session.commit()
    period_lock.advance(books, date(2026, 2, 28))
    db.session.commit()
    from app.services import rules_engine
    bank_line = rules_engine._post_entry_for_transaction(txn, "6061", "Électricité")  # noqa: SLF001
    assert bank_line.entry.entry_date == date(2026, 3, 1)
    assert bank_line.entry.description.startswith("[pièce du 03/02/2026]")


def test_rewind_admin_only_with_reason(books, login_as):
    period_lock.advance(books, date(2026, 3, 31))
    db.session.commit()
    base = f"/api/v1/fiscal-years/{books.id}/period-lock/rewind"
    _error(login_as().post(base, json={"until": "2026-01-31", "reason": "x"}), 403)


def test_rewind_by_admin(books, login_as):
    early = _entry(books, date(2026, 1, 10))
    period_lock.advance(books, date(2026, 3, 31))
    db.session.commit()
    admin = login_as(is_admin=True)
    base = f"/api/v1/fiscal-years/{books.id}/period-lock/rewind"
    assert _error(admin.post(base, json={"until": "2026-01-31"}), 422)["fields"]["reason"]
    resp = admin.post(base, json={"until": "2026-01-31", "reason": "Facture d'avril antidatée"})
    assert resp.get_json()["item"]["locked_until"] == "2026-01-31"
    db.session.refresh(early)
    assert early.is_validated  # reculer ne dévalide rien
    assert admin.post(base, json={"until": None, "reason": "Tout rouvrir"}).get_json()["item"]["locked_until"] is None
    assert ClosingEvent.query.filter_by(step="lock", action="rewind").count() == 2


def test_undo_batch_refused_in_locked_period(books):
    entry = _entry(books, date(2026, 3, 1))
    validation.validate(books, [entry], "manual")
    books.locked_until = date(2026, 3, 31)
    db.session.commit()
    with pytest.raises(validation.ValidationError):
        validation.undo_last_batch(books, "essai")


def test_provisional_close_locks_and_reopen_restores(books):
    period_lock.advance(books, date(2026, 3, 31))
    _entry(books, date(2026, 6, 1))
    for step in closing.DECIDED_BEFORE_CLOSE:
        closing.set_step(books, step, "skipped", note="test de verrouillage")
    closing.close_provisional(books)
    assert books.locked_until == date(2026, 12, 31) and books.lock_before_close == date(2026, 3, 31)
    closing.reopen(books, reason="facture oubliée")
    assert books.locked_until == date(2026, 3, 31) and books.lock_before_close is None
    assert JournalEntry.query.filter(JournalEntry.entry_date == date(2026, 6, 1)).one().validation_number is None
