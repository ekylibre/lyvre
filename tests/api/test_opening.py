"""Phase A.5 : ouverture de l'exercice suivant (à-nouveaux, extournes, regénération) et
affectation du résultat (association et SCI)."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, ClosingEvent, FiscalYear, Journal, JournalEntry, JournalLine
from app.services import closing, organization
from app.services.ledger import post_entry


def _error(resp, status):
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()["error"]


def _ids(*codes):
    return {c: Account.query.filter_by(code=c).one().id for c in codes}


def _make_books(app, tmp_path, monkeypatch, codes):
    monkeypatch.setattr(app, "instance_path", str(tmp_path))
    fy = FiscalYear(label="2025", start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
    db.session.add_all([fy, Journal(code="BQ", label="Banque")])
    db.session.add_all([Account(code=c, label=f"Compte {c}", account_type="OTHER") for c in codes])
    db.session.commit()
    org = organization.get()
    org.siren = "732829320"
    db.session.commit()
    ids = _ids("512100", "6061", "706", "102")
    bq = Journal.query.one()
    post_entry(fy.id, bq.id, date(2025, 1, 2), "Apport", [
        {"account_id": ids["512100"], "debit_cents": 50000}, {"account_id": ids["102"], "credit_cents": 50000}])
    post_entry(fy.id, bq.id, date(2025, 3, 1), "Vente", [
        {"account_id": ids["512100"], "debit_cents": 10000}, {"account_id": ids["706"], "credit_cents": 10000}])
    post_entry(fy.id, bq.id, date(2025, 4, 1), "Achat", [
        {"account_id": ids["6061"], "debit_cents": 3000}, {"account_id": ids["512100"], "credit_cents": 3000}])
    return fy


@pytest.fixture()
def asso(app, tmp_path, monkeypatch):
    return _make_books(app, tmp_path, monkeypatch,
                       ("512100", "6061", "706", "102", "408", "120", "129", "110", "119", "1068"))


@pytest.fixture()
def sci(app, tmp_path, monkeypatch):
    return _make_books(app, tmp_path, monkeypatch, ("512100", "6061", "706", "102", "408", "12", "11", "4551"))


def _close(client, fy, closing_ready):
    closing_ready(fy)
    assert client.post(f"/api/v1/fiscal-years/{fy.id}/close", json={}).status_code == 200


def _balances(fy_id, classes=("1", "2", "3", "4", "5")):
    rows = (db.session.query(Account.code, db.func.sum(JournalLine.debit_cents - JournalLine.credit_cents))
            .join(JournalLine, JournalLine.account_id == Account.id)
            .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
            .filter(JournalEntry.fiscal_year_id == fy_id).group_by(Account.code).all())
    return {c: v for c, v in rows if v and c.startswith(classes)}


def test_opening_needs_close_and_next_year(asso, login_as):
    client = login_as()
    url = f"/api/v1/fiscal-years/{asso.id}/opening"
    assert "Clôturez" in _error(client.post(url, json={}), 409)["message"]
    steps = {s["key"]: s for s in client.get(f"/api/v1/fiscal-years/{asso.id}/closing").get_json()["steps"]}
    assert not steps["opening"]["available"] and not steps["allocation"]["available"]


def test_opening_balances_and_reversals(asso, login_as, closing_ready):
    client = login_as()
    base = f"/api/v1/fiscal-years/{asso.id}"
    client.post(f"{base}/inventory", json={"kind": "accrued_expense", "account_code": "6061", "amount_cents": 1500,
                                          "label": "Électricité"})
    _close(client, asso, closing_ready)
    preview = client.get(f"{base}/closing").get_json()["opening"]
    assert {l["account_code"]: (l["debit_cents"], l["credit_cents"]) for l in preview["lines"]} == {
        "512100": (57000, 0), "102": (0, 50000), "408": (0, 1500), "120": (0, 5500)}
    assert "créez-le" in _error(client.post(f"{base}/opening", json={}), 422)["message"]
    assert client.post(f"{base}/opening", json={"create_next": True}).status_code == 200

    nxt = FiscalYear.query.filter_by(label="2026").one()
    assert (nxt.start_date, nxt.end_date) == (date(2026, 1, 1), date(2026, 12, 31))
    opening = JournalEntry.query.filter_by(fiscal_year_id=nxt.id, source="OPENING").one()
    assert opening.journal.code == "AN" and opening.entry_date == date(2026, 1, 1)
    # Bilan d'ouverture (à-nouveaux seuls) = bilan de clôture de N, résultat porté en 120.
    expected = _balances(asso.id)
    expected["120"] = -5500
    assert {l.account.code: l.debit_cents - l.credit_cents for l in opening.lines} == expected
    reversal = JournalEntry.query.filter_by(fiscal_year_id=nxt.id, source="REVERSAL").one()
    assert reversal.reverses_entry_id == JournalEntry.query.filter_by(source="INVENTORY").one().id
    # 408 : à-nouveau créditeur annulé par l'extourne ; 6061 au crédit en N+1.
    assert _balances(nxt.id, ("4", "6")) == {"6061": -1500}
    assert _balances(nxt.id, ("1", "5")) == {"102": -50000, "120": -5500, "512100": 57000}
    steps = {s["key"]: s for s in client.get(f"{base}/closing").get_json()["steps"]}
    assert steps["opening"]["state"] == "done" and steps["allocation"]["available"]
    # Les écritures gérées par l'assistant ne se modifient pas ailleurs.
    assert "assistant" in _error(client.delete(f"/api/v1/entries/{opening.id}"), 409)["message"]
    detail = client.get(f"/api/v1/entries/{opening.id}").get_json()
    assert detail["managed"] and not detail["editable"]


def test_regeneration_after_reopen(asso, login_as, closing_ready):
    admin = login_as(role="admin")
    base = f"/api/v1/fiscal-years/{asso.id}"
    _close(admin, asso, closing_ready)
    admin.post(f"{base}/opening", json={"create_next": True})
    nxt = FiscalYear.query.filter_by(label="2026").one()
    first = _balances(nxt.id)
    assert admin.post(f"{base}/opening", json={}).status_code == 200  # regénération : pas de doublon
    assert JournalEntry.query.filter_by(fiscal_year_id=nxt.id, source="OPENING").count() == 1
    assert _balances(nxt.id) == first

    admin.post(f"{base}/reopen", json={"reason": "Achat oublié"})
    assert JournalEntry.query.filter_by(fiscal_year_id=nxt.id, source="OPENING").count() == 0
    ids = _ids("6061", "512100")
    post_entry(asso.id, Journal.query.filter_by(code="BQ").one().id, date(2025, 12, 20), "Achat oublié", [
        {"account_id": ids["6061"], "debit_cents": 500}, {"account_id": ids["512100"], "credit_cents": 500}])
    admin.post(f"{base}/close", json={})
    admin.post(f"{base}/opening", json={})
    assert _balances(nxt.id) == {"102": -50000, "120": -6500, "512100": 56500}
    expected = _balances(asso.id)
    expected["120"] = -6500
    assert _balances(nxt.id) == expected


def test_allocation_association(asso, login_as, closing_ready):
    client = login_as()
    base = f"/api/v1/fiscal-years/{asso.id}"
    _close(client, asso, closing_ready)
    assert "à-nouveaux" in _error(client.post(f"{base}/allocation", json={}), 422)["message"]
    client.post(f"{base}/opening", json={"create_next": True})
    alloc = client.get(f"{base}/closing").get_json()["allocation"]
    assert alloc["result_cents"] == 7000
    assert [o["value"] for o in alloc["options"]] == ["102", "1068", "110", "119"]
    good = {"decided_on": "2026-06-15", "body": "Assemblée générale",
            "lines": [{"account_code": "110", "amount_cents": 5000}, {"account_code": "1068", "amount_cents": 2000}]}
    assert "totaliser 70.00" in _error(client.post(f"{base}/allocation", json={**good, "lines": good["lines"][:1]}),
                                       422)["message"]
    _error(client.post(f"{base}/allocation", json={**good, "decided_on": "2025-12-31"}), 422)
    _error(client.post(f"{base}/allocation", json={**good, "body": ""}), 422)
    _error(client.post(f"{base}/allocation", json={**good, "lines": [{"account_code": "512100", "amount_cents": 7000}]}),
           422)
    assert client.post(f"{base}/allocation", json=good).status_code == 200
    nxt = FiscalYear.query.filter_by(label="2026").one()
    entry = JournalEntry.query.filter_by(fiscal_year_id=nxt.id, source="ALLOCATION").one()
    assert entry.entry_date == date(2026, 6, 15) and entry.journal.code == "OD"
    assert _balances(nxt.id, ("11", "12", "106")) == {"110": -5000, "1068": -2000}
    db.session.refresh(asso)
    assert asso.allocation_body == "Assemblée générale" and asso.allocation_decided_on == date(2026, 6, 15)
    # Réouverture et regénération refusées tant que l'affectation existe.
    _error(client.post(f"{base}/opening", json={}), 409)
    _error(client.post(f"{base}/allocation", json=good), 409)
    assert client.delete(f"{base}/allocation").status_code == 200
    assert JournalEntry.query.filter_by(source="ALLOCATION").count() == 0
    assert [e.action for e in ClosingEvent.query.filter_by(step="allocation")] == ["allocate", "cancel"]


def test_allocation_deficit_sci(sci, login_as, closing_ready):
    ids = _ids("6061", "512100")
    post_entry(sci.id, Journal.query.one().id, date(2025, 5, 1), "Travaux", [
        {"account_id": ids["6061"], "debit_cents": 20000}, {"account_id": ids["512100"], "credit_cents": 20000}])
    client = login_as()
    base = f"/api/v1/fiscal-years/{sci.id}"
    _close(client, sci, closing_ready)
    client.post(f"{base}/opening", json={"create_next": True})
    nxt = FiscalYear.query.filter_by(label="2026").one()
    assert _balances(nxt.id, ("12",)) == {"12": 13000}  # perte : 12 au débit (plan SCI sans 129)
    alloc = client.get(f"{base}/closing").get_json()["allocation"]
    assert alloc["result_cents"] == -13000
    assert [o["value"] for o in alloc["options"]] == ["102", "11", "4551"]
    assert client.post(f"{base}/allocation", json={"decided_on": "2026-04-30", "body": "Assemblée des associés", "lines": [
        {"account_code": "4551", "amount_cents": 13000}]}).status_code == 200
    assert _balances(nxt.id, ("12", "455")) == {"4551": 13000}


def test_reopen_refused_when_next_year_closed_with_opening(asso, login_as, closing_ready):
    admin = login_as(role="admin")
    base = f"/api/v1/fiscal-years/{asso.id}"
    _close(admin, asso, closing_ready)
    admin.post(f"{base}/opening", json={"create_next": True})
    nxt = FiscalYear.query.filter_by(label="2026").one()
    nxt.status = "provisional"
    db.session.commit()
    assert "2026" in _error(admin.post(f"{base}/reopen", json={"reason": "x"}), 409)["message"]


def test_accountant_cannot_generate(asso, login_as):
    _error(login_as(role="accountant").post(f"/api/v1/fiscal-years/{asso.id}/opening", json={}), 403)
