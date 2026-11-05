"""Lot AG5.c : mort, sinistre, abattage sanitaire (indemnité en 7571, réinvestissement), dépréciations (AGD22)."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, AssetImpairment, FiscalYear, Journal, JournalEntry, LivingReinvestment
from app.models.journal_entry import SOURCE_LIVING_IMPAIRMENT
from app.services import agenda, closing
from test_agri_fixtures import _agri_instance


def _id(code):
    return Account.query.filter_by(code=code).one().id


@pytest.fixture()
def farm(app, login_as):
    client = login_as(role="admin")
    _agri_instance()
    years = {y: FiscalYear(label=str(y), start_date=date(y, 1, 1), end_date=date(y, 12, 31)) for y in (2026, 2027, 2028)}
    db.session.add_all([*years.values(), Journal(code="OD", label="OD")])
    db.session.commit()
    return {"client": client, "fy": years}


def _asset(client, **data):
    base = {"account_id": _id("241"), "acquired_on": "2026-01-01", "in_service_date": "2026-01-01", "method": "linear",
            "duration_months": 60}
    resp = client.post("/api/v1/assets", json={**base, **data})
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["item"]


def _lines(entry_id):
    return {(l.account.code, l.debit_cents, l.credit_cents) for l in db.session.get(JournalEntry, entry_id).lines}


def test_death_with_insurance_indemnity(farm):
    client = farm["client"]
    cow = _asset(client, label="Vache Marguerite", acquisition_cents=300000, units=1, species="Bovin")
    url = f"/api/v1/assets/{cow['id']}/living-exits"
    assert client.post(url, json={"date": "2026-07-01", "kind": "death", "price_cents": 1000}).status_code == 422
    assert client.post(url, json={"date": "2026-07-01", "kind": "sale", "indemnity_cents": 1000}).status_code == 422
    assert client.post(url, json={"date": "2026-07-01", "kind": "fugue"}).status_code == 422
    resp = client.post(url, json={"date": "2026-07-01", "kind": "death", "indemnity_cents": 150000, "note": "assurance mortalité"})
    assert resp.status_code == 200, resp.get_json()
    exit_ = resp.get_json()["exit"]
    assert exit_["kind_label"] == "Mort" and exit_["book_value_cents"] == 269833                # 181 jours amortis (30 167)
    from app.models import AssetLivingExit
    row = AssetLivingExit.query.one()
    assert ("6571", 269833, 0) in _lines(row.entry_id)
    assert _lines(row.indemnity_entry_id) == {("462", 150000, 0), ("7571", 0, 150000)}


def test_partial_sanitary_slaughter_and_reinvestment(farm):
    client = farm["client"]
    herd = _asset(client, label="Vaches allaitantes", acquisition_cents=2000000, units=20, species="Bovin")
    resp = client.post(f"/api/v1/assets/{herd['id']}/living-exits",
                       json={"date": "2026-09-01", "kind": "sanitary_slaughter", "units": 5, "indemnity_cents": 600000})
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["item"]["living"]["units"] == 15
    reinvest = body["exit"]["reinvestment"]
    assert reinvest["deadline"] == "2028-09-01" and reinvest["indemnity_cents"] == 600000 and reinvest["book_value_cents"] > 0
    (occ,) = [i for i in agenda.occurrences(date(2028, 1, 1), date(2028, 12, 31), date(2028, 3, 1))["items"]
              if i["fiche_id"] == "DIV-06"]
    assert occ["date"] == date(2028, 9, 1) and occ["status"] != "done"
    assert any(c.key == "living_reinvestment" for c in closing._agri_checks(farm["fy"][2028]))
    client.put(f"/api/v1/living-reinvestments/{reinvest['id']}", json={"reinvested_cents": 600000, "reinvested_on": "2027-05-10"})
    (occ,) = [i for i in agenda.occurrences(date(2028, 1, 1), date(2028, 12, 31), date(2028, 3, 1))["items"]
              if i["fiche_id"] == "DIV-06"]
    assert occ["status"] == "done" and LivingReinvestment.query.one().reinvested_cents == 600000
    listing = client.get("/api/v1/living-exits").get_json()["items"]
    assert listing[0]["kind"] == "sanitary_slaughter" and listing[0]["units"] == 5


def test_impairment_then_reversal_and_exit(farm):
    client, fy = farm["client"], farm["fy"]
    ram = _asset(client, label="Bélier", acquisition_cents=100000, units=1, method="none", duration_months=None)
    url = lambda y: f"/api/v1/fiscal-years/{fy[y].id}/closing/living-impairments"  # noqa: E731
    put = lambda y, **b: client.put(f"{url(y)}/values", json={"asset_id": ram["id"], **b})  # noqa: E731
    assert put(2026, amount_cents=50000).status_code == 422                                  # motif
    assert put(2026, amount_cents=200000, reason="boiterie chronique").status_code == 422   # > valeur nette
    assert put(2026, amount_cents=50000, reason="boiterie chronique").status_code == 200
    assert any(c.key == "living_impairment" for c in closing._agri_checks(fy[2026]))
    assert client.post(url(2026)).status_code == 200
    entry = JournalEntry.query.filter_by(source=SOURCE_LIVING_IMPAIRMENT, fiscal_year_id=fy[2026].id).one()
    assert {(l.account.code, l.debit_cents, l.credit_cents) for l in entry.lines} == {("68164", 50000, 0), ("294", 0, 50000)}
    assert not any(c.key == "living_impairment" for c in closing._agri_checks(fy[2026]))
    put(2027, amount_cents=20000, reason="guéri en partie")
    client.post(url(2027))
    entry = JournalEntry.query.filter_by(source=SOURCE_LIVING_IMPAIRMENT, fiscal_year_id=fy[2027].id).one()
    assert {(l.account.code, l.debit_cents, l.credit_cents) for l in entry.lines} == {("294", 30000, 0), ("78164", 0, 30000)}
    client.post(f"/api/v1/assets/{ram['id']}/living-exits", json={"date": "2028-03-01", "kind": "sale", "price_cents": 50000})
    (row,) = client.get(url(2028)).get_json()["items"]
    assert row["exited"] and row["delta_cents"] == -20000
    client.post(url(2028))
    entry = JournalEntry.query.filter_by(source=SOURCE_LIVING_IMPAIRMENT, fiscal_year_id=fy[2028].id).one()
    assert ("78164", 0, 20000) in {(l.account.code, l.debit_cents, l.credit_cents) for l in entry.lines}
    assert AssetImpairment.query.filter_by(fiscal_year_id=fy[2028].id).one().amount_cents == 0
