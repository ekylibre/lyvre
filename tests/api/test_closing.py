"""Phase A.4 : assistant de clôture (contrôles, inventaire, résultat, FEC à blanc, clôture
provisoire / définitive, réouverture, droits, audit)."""
from datetime import date

import pytest

from app.extensions import db
from app.models import (
    Account, BankAccount, BankTransaction, ClosingEvent, FiscalYear, Journal, JournalEntry, JournalLine, Purchase,
)
from app.services import closing, organization
from app.services.ledger import post_entry


def _error(resp, status):
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()["error"]


@pytest.fixture()
def books(app, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "instance_path", str(tmp_path))
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    accounts = {c: Account(code=c, label=f"Compte {c}", account_type="OTHER")
                for c in ("512100", "6061", "706", "408", "4686", "486", "487", "4687", "471")}
    db.session.add_all([fy, Journal(code="BQ", label="Banque"), *accounts.values()])
    db.session.commit()
    bq = Journal.query.filter_by(code="BQ").one()
    post_entry(fy.id, bq.id, date(2026, 3, 1), "Vente", [
        {"account_id": accounts["512100"].id, "debit_cents": 10000},
        {"account_id": accounts["706"].id, "credit_cents": 10000}])
    post_entry(fy.id, bq.id, date(2026, 4, 1), "Achat", [
        {"account_id": accounts["6061"].id, "debit_cents": 3000},
        {"account_id": accounts["512100"].id, "credit_cents": 3000}])
    return fy


def _siren():
    org = organization.get()
    org.siren = "732829320"
    db.session.commit()


# ------------------------------------------------------------------ contrôles et résultat


def test_checks_detect_anomalies(books):
    assert closing.checks(books) == []
    account = Account.query.filter_by(code="512100").one()
    ba = BankAccount(label="CIC", account_id=account.id)
    db.session.add(ba)
    db.session.flush()
    db.session.add(BankTransaction(bank_account_id=ba.id, fitid="T1", transaction_date=date(2026, 5, 2),
                                   amount_cents=-500, label="CB"))
    entry = JournalEntry(fiscal_year_id=books.id, journal_id=Journal.query.one().id, entry_date=date(2026, 6, 1),
                         reference="BQ-X", description="Bancale")
    db.session.add(entry)
    db.session.flush()
    db.session.add(JournalLine(entry_id=entry.id, account_id=Account.query.filter_by(code="471").one().id,
                               debit_cents=700, credit_cents=0))
    db.session.add(Purchase(source="manual", invoice_number="F-1", issue_date=date(2026, 7, 1), total_cents=100))
    db.session.commit()
    found = {c.key.split("_")[0] if c.key.startswith(("unreconciled", "suspense")) else c.key: c
             for c in closing.checks(books)}
    assert found["unreconciled"].count == 1 and found["unreconciled"].url == f"/reconciliation/?bank_account_id={ba.id}"
    assert found["unbalanced"].count == 1 and found["purchases_not_posted"].count == 1
    assert "471" in found["suspense"].label
    assert all(c.severity == "anomaly" for c in found.values())


def test_bank_credit_balance_detected(books):
    bq = Journal.query.one()
    post_entry(books.id, bq.id, date(2026, 9, 1), "Gros achat", [
        {"account_id": Account.query.filter_by(code="6061").one().id, "debit_cents": 20000},
        {"account_id": Account.query.filter_by(code="512100").one().id, "credit_cents": 20000}])
    assert [c.key for c in closing.checks(books)] == ["credit_512100"]


def test_result(books):
    assert closing.result(books) == {"income_cents": 10000, "expense_cents": 3000, "result_cents": 7000}


# ------------------------------------------------------------------ étapes


def test_step_rules(books, login_as):
    client = login_as()
    url = f"/api/v1/fiscal-years/{books.id}/closing"
    assert _error(client.post(f"{url}/checks", json={"state": "skipped"}), 422)["message"].startswith("Motif")
    steps = client.post(f"{url}/checks", json={"state": "done"}).get_json()["steps"]
    assert steps[0]["state"] == "done"
    _error(client.post(f"{url}/fec", json={"state": "done"}), 422)  # SIREN manquant
    _siren()
    assert client.post(f"{url}/fec", json={"state": "done"}).status_code == 200
    _error(client.post(f"{url}/opening", json={"state": "done"}), 422)
    _error(client.post(f"{url}/checks", json={"state": "peut-être"}), 422)


def test_checks_done_refused_with_anomalies(books, login_as):
    db.session.add(Purchase(source="manual", invoice_number="F-1", issue_date=date(2026, 7, 1), total_cents=100))
    db.session.commit()
    client = login_as()
    url = f"/api/v1/fiscal-years/{books.id}/closing/checks"
    assert "anomalie" in _error(client.post(url, json={"state": "done"}), 422)["message"]
    assert client.post(url, json={"state": "skipped", "note": "Facture traitée en 2027"}).status_code == 200


# ------------------------------------------------------------------ inventaire


def test_inventory_entries(books, login_as):
    client = login_as()
    url = f"/api/v1/fiscal-years/{books.id}/inventory"
    resp = client.post(url, json={"kind": "accrued_expense", "account_code": "6061", "amount_cents": 1500,
                                  "label": "Électricité décembre"})
    assert resp.status_code == 201
    entry = JournalEntry.query.filter_by(source="INVENTORY").one()
    assert entry.entry_date == date(2026, 12, 31) and entry.inventory_kind == "accrued_expense"
    assert entry.journal.code == "OD"
    lines = {line.account.code: (line.debit_cents, line.credit_cents) for line in entry.lines}
    assert lines == {"6061": (1500, 0), "408": (0, 1500)}
    client.post(url, json={"kind": "deferred_income", "account_code": "706", "amount_cents": 400, "label": "Cotis 2027"})
    pca = JournalEntry.query.filter_by(inventory_kind="deferred_income").one()
    assert {l.account.code: (l.debit_cents, l.credit_cents) for l in pca.lines} == {"706": (400, 0), "487": (0, 400)}
    assert "classe 6" in _error(client.post(url, json={"kind": "accrued_expense", "account_code": "706",
                                                         "amount_cents": 1}), 422)["message"]
    _error(client.post(url, json={"kind": "accrued_expense", "account_code": "6061", "amount_cents": 1,
                                  "counterpart_code": "486"}), 422)
    _error(client.post(url, json={"kind": "prepaid_expense", "account_code": "6061", "amount_cents": -5}), 422)
    body = client.get(f"/api/v1/fiscal-years/{books.id}/closing").get_json()
    assert [i["amount_cents"] for i in body["inventory"]] == [1500, 400]
    assert [c["value"] for c in body["inventory_options"]["accrued_expense"]["counterparts"]] == ["408", "4686"]
    assert client.delete(f"{url}/{entry.id}").status_code == 200
    assert JournalEntry.query.filter_by(source="INVENTORY").count() == 1
    _error(client.delete(f"{url}/{pca.id + 999}"), 404)


# ------------------------------------------------------------------ clôture et réouverture


def test_provisional_final_and_reopen(books, login_as, closing_ready):
    _siren()
    treasurer = login_as()
    base = f"/api/v1/fiscal-years/{books.id}"
    assert "Étapes à terminer" in _error(treasurer.post(f"{base}/close", json={}), 422)["message"]
    closing_ready(books)
    assert treasurer.post(f"{base}/close", json={}).get_json()["item"]["status"] == "provisional"
    assert {e.validation_number for e in JournalEntry.query.all()} == {1, 2}
    _error(treasurer.post(f"{base}/closing/checks", json={"state": "todo"}), 409)
    _error(treasurer.post(f"{base}/inventory", json={"kind": "accrued_expense", "account_code": "6061",
                                                       "amount_cents": 1}), 409)
    _error(treasurer.post(f"{base}/close", json={"final": True}), 403)
    _error(treasurer.post(f"{base}/reopen", json={"reason": "x"}), 403)


def test_admin_reopen_and_final(books, login_as, closing_ready):
    _siren()
    admin = login_as(role="admin")
    base = f"/api/v1/fiscal-years/{books.id}"
    closing_ready(books)
    admin.post(f"{base}/close", json={})
    assert "Motif" in _error(admin.post(f"{base}/reopen", json={}), 422)["message"]
    assert admin.post(f"{base}/reopen", json={"reason": "Facture oubliée"}).get_json()["item"]["status"] == "open"
    assert {e.validation_number for e in JournalEntry.query.all()} == {None}
    admin.post(f"{base}/close", json={})
    final = admin.post(f"{base}/close", json={"final": True}).get_json()["item"]
    assert final["status"] == "closed"
    db.session.refresh(books)
    assert books.fec_sha256 and books.closed_at is not None
    assert "irréversible" in _error(admin.post(f"{base}/reopen", json={"reason": "x"}), 409)["message"]
    actions = [e.action for e in ClosingEvent.query.order_by(ClosingEvent.id)]
    assert actions[-4:] == ["provisional", "reopen", "provisional", "final"]
    assert admin.get(f"/fiscal-years/{books.id}/fec").status_code == 200


def test_reopen_refused_when_next_year_final(books, login_as, closing_ready):
    _siren()
    admin = login_as(role="admin")
    closing_ready(books)
    admin.post(f"/api/v1/fiscal-years/{books.id}/close", json={})
    nxt = FiscalYear(label="2027", start_date=date(2027, 1, 1), end_date=date(2027, 12, 31), status="closed")
    db.session.add(nxt)
    db.session.commit()
    assert "2027" in _error(admin.post(f"/api/v1/fiscal-years/{books.id}/reopen", json={"reason": "x"}), 409)["message"]


def test_final_close_needs_valid_fec(books, login_as, closing_ready):
    admin = login_as(role="admin")
    closing_ready(books)
    admin.post(f"/api/v1/fiscal-years/{books.id}/close", json={})
    assert "SIREN" in _error(admin.post(f"/api/v1/fiscal-years/{books.id}/close", json={"final": True}), 422)["message"]
    db.session.refresh(books)
    assert books.status == "provisional"


def test_accountant_reads_closing_but_cannot_act(books, login_as):
    client = login_as(role="accountant")
    body = client.get(f"/api/v1/fiscal-years/{books.id}/closing").get_json()
    assert [s["key"] for s in body["steps"]][:6] == ["checks", "inventory", "dedicated_funds", "result", "fec", "close"]
    assert body["result"]["result_cents"] == 7000
    assert client.get(f"/api/v1/fiscal-years/{books.id}/fec/preview").status_code == 200
    _error(client.post(f"/api/v1/fiscal-years/{books.id}/closing/checks", json={"state": "done"}), 403)


def test_fec_preview_leaves_no_trace(books, login_as):
    _siren()
    body = login_as().get(f"/api/v1/fiscal-years/{books.id}/fec/preview").get_json()
    assert body["errors"] == [] and body["problems"] == [] and body["stats"]["entries"] == 2
    assert {e.validation_number for e in JournalEntry.query.all()} == {None}
