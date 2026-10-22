"""Phase A.2 : identité de la structure, statut d'exercice, exclusion des écritures de clôture
du rapprochement."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, BankAccount, BankTransaction, FiscalYear, Journal, Organization
from app.models.fiscal_year import FY_CLOSED, FY_OPEN, FY_PROVISIONAL
from app.services import organization, reconciler
from app.services.ledger import LedgerError, post_entry


def _error(resp, status):
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()["error"]


# ------------------------------------------------------------------ structure


def test_organization_created_with_instance_name(login_as):
    client = login_as(role="accountant")
    body = client.get("/api/v1/organization").get_json()["item"]
    assert body["name"] == "Test" and body["country"] == "France" and body["fec_ready"] is False
    assert Organization.query.count() == 1
    client.get("/api/v1/organization")
    assert Organization.query.count() == 1


def test_organization_update_by_instance_admin(login_as):
    client = login_as(role="admin")
    resp = client.put("/api/v1/organization", json={
        "name": "Seconde Nature", "siren": "732 829 320", "rna": "w751234567", "postal_code": "75011",
        "city": "Paris", "purpose": "Réemploi"})
    item = resp.get_json()["item"]
    assert item["siren"] == "732829320" and item["rna"] == "W751234567" and item["fec_ready"] is True
    err = _error(client.put("/api/v1/organization", json={"siren": "123456789", "rna": "751", "postal_code": "7501",
                                                           "name": ""}), 422)
    assert set(err["fields"]) == {"siren", "rna", "postal_code", "name"}
    assert organization.get().siren == "732829320"  # rien d'écrit en cas d'erreur
    # Hors de France, le code postal est libre.
    assert client.put("/api/v1/organization", json={"country": "Belgique", "postal_code": "1000"}).status_code == 200


def test_organization_update_refused_to_treasurer(login_as):
    _error(login_as().put("/api/v1/organization", json={"name": "X"}), 403)


def test_siren_luhn():
    assert organization.luhn_valid("732829320") and not organization.luhn_valid("732829321")
    assert organization.validate({"siren": "356000000"})[1] == {}  # La Poste


# ------------------------------------------------------------------ statut d'exercice


def _fy(**kw):
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), **kw)
    db.session.add(fy)
    db.session.commit()
    return fy


def test_status_and_lock_stay_in_sync(app):
    fy = _fy()
    assert (fy.status, fy.closed, fy.provisional_at) == (FY_OPEN, False, None)
    fy.closed = True  # ancien code et tests : verrou seul
    db.session.commit()
    assert fy.status == FY_PROVISIONAL and fy.provisional_at is not None
    fy.status = FY_OPEN
    db.session.commit()
    assert fy.closed is False
    fy.status = FY_CLOSED
    db.session.commit()
    assert fy.closed is True and fy.is_final and fy.status_label == "Clôturé"
    legacy = _fy(closed=True)
    assert legacy.status == FY_PROVISIONAL


def test_close_endpoint_is_provisional_and_locks(login_as, closing_ready):
    client = login_as()
    fy = _fy()
    db.session.add_all([Journal(code="OD", label="OD"), Account(code="6061", label="x", account_type="EXPENSE"),
                        Account(code="401", label="y", account_type="TIERS")])
    db.session.commit()
    closing_ready(fy)
    item = client.post(f"/api/v1/fiscal-years/{fy.id}/close").get_json()["item"]
    assert item["status"] == "provisional" and item["status_label"] == "Clôture provisoire" and item["closed"]
    journal = Journal.query.one()
    with pytest.raises(LedgerError):
        post_entry(fy.id, journal.id, date(2026, 3, 1), "x", [
            {"account_id": Account.query.filter_by(code="6061").one().id, "debit_cents": 100},
            {"account_id": Account.query.filter_by(code="401").one().id, "credit_cents": 100}])
    _error(client.post(f"/api/v1/fiscal-years/{fy.id}/close"), 409)


# ------------------------------------------------------------------ rapprochement


def test_closing_entries_never_suggested_for_reconciliation(app):
    fy = _fy()
    bank = Account(code="512100", label="Banque", account_type="ASSET")
    other = Account(code="110", label="RAN", account_type="EQUITY")
    journal = Journal(code="AN", label="À-nouveaux")
    db.session.add_all([bank, other, journal])
    db.session.flush()
    ba = BankAccount(label="Banque", account_id=bank.id)
    db.session.add(ba)
    db.session.flush()
    bt = BankTransaction(bank_account_id=ba.id, fitid="F1", transaction_date=date(2026, 1, 1), amount_cents=5000,
                         label="Solde")
    db.session.add(bt)
    db.session.commit()
    lines = [{"account_id": bank.id, "debit_cents": 5000}, {"account_id": other.id, "credit_cents": 5000}]
    post_entry(fy.id, journal.id, date(2026, 1, 1), "À-nouveaux", lines, source="OPENING")
    assert reconciler.suggest_matches(bt.id) == []
    manual = post_entry(fy.id, journal.id, date(2026, 1, 1), "Versement", lines)
    assert [line.entry_id for line in reconciler.suggest_matches(bt.id)] == [manual.id]
