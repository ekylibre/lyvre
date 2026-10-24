"""Lot F4 : charges et produits constatés d'avance proposés à la clôture."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, Entity, FiscalYear, Journal, JournalEntry, Purchase, Subscription, SubscriptionPeriod
from app.services import closing, prepaid
from app.services.ledger import post_entry


def _error(resp, status):
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()["error"]


@pytest.fixture()
def books(app, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "instance_path", str(tmp_path))
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    accounts = [Account(code=c, label=f"Compte {c}", account_type="OTHER")
                for c in ("401001", "6161", "6262", "706", "486", "487", "512100", "120", "129")]
    db.session.add_all([fy, FiscalYear(label="2027", start_date=date(2027, 1, 1), end_date=date(2027, 12, 31)),
                        Journal(code="AC", label="Achats"), Journal(code="OD", label="OD"), *accounts,
                        Entity(name="Assureur", entity_type="FOURNISSEUR", account_code="401001")])
    db.session.commit()
    return fy


def _ids():
    return {a.code: a.id for a in Account.query.all()}


def _purchase(fy, amount, account="6161", **period):
    a = _ids()
    entry = post_entry(fy.id, Journal.query.filter_by(code="AC").one().id, date(2026, 7, 1), "Assurance", [
        {"account_id": a[account], "debit_cents": amount}, {"account_id": a["401001"], "credit_cents": amount}])
    p = Purchase(source="manual", invoice_number="A-1", issue_date=date(2026, 7, 1), total_cents=amount,
                 entity_id=Entity.query.one().id, journal_entry_id=entry.id, **period)
    db.session.add(p)
    db.session.commit()
    return p


def test_share_181_over_365():
    assert prepaid.share(120000, date(2026, 7, 1), date(2027, 6, 30), date(2026, 12, 31)) == (59507, 181, 365)
    assert prepaid.share(1000, date(2027, 1, 1), date(2027, 3, 31), date(2026, 12, 31))[0] == 1000
    assert prepaid.share(1000, date(2026, 1, 1), date(2026, 12, 31), date(2026, 12, 31))[0] == 0


def test_purchase_period_proposed_and_posted_once(books, login_as):
    p = _purchase(books, 120000, service_start=date(2026, 7, 1), service_end=date(2027, 6, 30))
    client = login_as()
    base = f"/api/v1/fiscal-years/{books.id}/closing/prepaid"
    (item,) = client.get(base).get_json()["items"]
    assert item["kind"] == "prepaid_expense" and item["account_code"] == "6161" and item["amount_cents"] == 59507
    assert item["source_id"] == p.id and not item["posted"]
    resp = client.post(base, json={"items": [{"key": item["key"], "amount_cents": 59500}]})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["items"][0]["posted"]
    entry = JournalEntry.query.filter_by(source_ref=item["key"]).one()
    assert entry.inventory_kind == "prepaid_expense" and entry.entry_date == date(2026, 12, 31)
    assert sorted((l.account.code, l.debit_cents, l.credit_cents) for l in entry.lines) == [("486", 59500, 0), ("6161", 0, 59500)]
    assert client.post(base, json={"items": [{"key": item["key"]}]}).get_json()["notices"][0]["message"].startswith("0 ")
    assert "Proposition introuvable" in _error(client.post(base, json={"items": [{"key": "x"}]}), 409)["message"]


def test_subscription_period_used_when_no_period(books):
    p = _purchase(books, 60000, account="6262")
    sub = Subscription(entity_id=Entity.query.one().id, label="Assurance", amount_cents=60000, frequency="yearly",
                       due_day=1, start_date=date(2026, 10, 1))
    db.session.add(sub)
    db.session.flush()
    db.session.add(SubscriptionPeriod(subscription_id=sub.id, due_date=date(2026, 10, 1), expected_cents=60000,
                                      purchase_id=p.id, status="invoiced"))
    db.session.commit()
    (item,) = prepaid.proposals(books)
    assert (item["period_start"], item["period_end"]) == ("2026-10-01", "2027-09-30")
    assert item["amount_cents"] == round(60000 * 273 / 365)


def test_journal_line_period_and_deferred_income(books, login_as):
    a = _ids()
    client = login_as()
    resp = client.post("/api/v1/entries", json={
        "fiscal_year_id": books.id, "journal_id": Journal.query.filter_by(code="OD").one().id,
        "entry_date": "2026-11-01", "description": "Cotisations annuelles",
        "lines": [{"account_id": a["512100"], "debit_cents": 36500},
                  {"account_id": a["706"], "credit_cents": 36500, "service_start": "2026-11-01", "service_end": "2027-10-31"}]})
    assert resp.status_code == 201, resp.get_json()
    (item,) = prepaid.proposals(books)
    assert item["kind"] == "deferred_income" and item["source"] == "line" and item["amount_cents"] == 30400
    prepaid.post(books, [{"key": item["key"]}])
    following, _opening, reversals = closing_reversals(books)
    assert reversals and reversals[0].entry_date == date(2027, 1, 1)


def closing_reversals(fy):
    for step in closing.DECIDED_BEFORE_CLOSE:
        closing.set_step(fy, step, "skipped", note="test des CCA et PCA")
    closing.close_provisional(fy)
    return closing.generate_opening(fy)


def test_purchase_form_period_validation(books):
    from app.services import purchase_entry
    _clean, errors = purchase_entry.validate_header({"issue_date": "2026-07-01", "total": "10", "service_start": "2026-07-01"})
    assert any("Période" in e for e in errors)
    clean, errors = purchase_entry.validate_header({"issue_date": "2026-07-01", "total": "10",
                                                    "service_start": "2026-07-01", "service_end": "2027-06-30"})
    assert not any("Période" in e for e in errors) and clean["service_end"] == date(2027, 6, 30)
