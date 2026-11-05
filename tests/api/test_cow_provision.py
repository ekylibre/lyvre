"""Lot AG6.d : provision 73 A des vaches (hausse par catégorie sans compensation, minoration EGALIM, reprises, 6e exercice)."""
from datetime import date

import pytest

from app.extensions import db
from app.models import CowProvision, FiscalYear, JournalEntry, TaxOption
from app.models.journal_entry import SOURCE_COW_PROVISION
from test_agri_fixtures import _agri_instance


@pytest.fixture()
def farm(app, login_as):
    client = login_as(role="admin")
    _agri_instance()
    years = {y: FiscalYear(label=str(y), start_date=date(y, 1, 1), end_date=date(y, 12, 31)) for y in range(2025, 2033)}
    db.session.add_all(years.values())
    db.session.commit()
    return {"client": client, "fy": years, "url": lambda y: f"/api/v1/fiscal-years/{years[y].id}"}


def _cows(farm, year, category, heads, unit_euros):
    resp = farm["client"].post(f"{farm['url'](year)}/stock/lines", json={
        "account_code": "3112", "label": f"Vaches {category}", "quantity": str(heads), "unit": "head", "method": "actual",
        "unit_value_cents": unit_euros * 100, "cow_category": category})
    assert resp.status_code == 201, resp.get_json()


def _lines(entry):
    return {(l.account.code, l.debit_cents, l.credit_cents) for l in entry.lines}


def test_proposal_without_compensation_and_egalim(farm):
    client = farm["client"]
    _cows(farm, 2025, "dairy", 40, 1200)
    _cows(farm, 2025, "suckler", 20, 1000)
    _cows(farm, 2026, "dairy", 45, 1300)                                    # +10 500 €
    _cows(farm, 2026, "suckler", 18, 1000)                                  # −2 000 € : pas de compensation
    prop = client.get(f"{farm['url'](2026)}/cow-provision").get_json()["item"]["proposal"]
    assert prop["eligible"] and prop["increase_cents"] == 1050000 and prop["minoration_bp"] == 2000
    assert prop["amount_cents"] == 840000 and prop["heads"] == 63                       # −20 % sans contrat en 2026
    client.put(f"{farm['url'](2026)}/egalim", json={"egalim_contract": True})
    assert client.get(f"{farm['url'](2026)}/cow-provision").get_json()["item"]["proposal"]["amount_cents"] == 1050000
    client.put(f"{farm['url'](2026)}/egalim", json={"egalim_contract": False})
    assert client.post(f"{farm['url'](2026)}/stock/lines", json={"account_code": "31111", "label": "x", "quantity": "1",
                                                                  "cow_category": "dairy"}).status_code == 422


def test_constitution_release_and_sixth_year(farm):
    client, fy = farm["client"], farm["fy"]
    _cows(farm, 2025, "dairy", 40, 1200)
    _cows(farm, 2025, "suckler", 20, 1000)
    _cows(farm, 2026, "dairy", 45, 1300)
    _cows(farm, 2026, "suckler", 18, 1000)
    assert client.post(f"{farm['url'](2026)}/cow-provision", json={"constitute": True}).status_code == 200
    entry = JournalEntry.query.filter_by(source=SOURCE_COW_PROVISION, fiscal_year_id=fy[2026].id).one()
    assert _lines(entry) == {("6873", 840000, 0), ("1483", 0, 840000)}
    _cows(farm, 2027, "dairy", 40, 1300)                                    # 58 têtes : 5 sorties, valeur en baisse
    _cows(farm, 2027, "suckler", 18, 1000)
    from app.services import closing
    assert any(c.key == "cow_release" for c in closing._agri_checks(fy[2027]))
    plan = client.get(f"{farm['url'](2027)}/cow-provision").get_json()["item"]["plan"]
    assert plan == [{"provision_id": CowProvision.query.one().id, "origin": "2026", "kind": "exit", "heads": 5, "amount_cents": 66667}]
    client.post(f"{farm['url'](2027)}/cow-provision", json={"constitute": False})
    entry = JournalEntry.query.filter_by(source=SOURCE_COW_PROVISION, fiscal_year_id=fy[2027].id).one()
    assert _lines(entry) == {("1483", 66667, 0), ("7873", 0, 66667)}
    _cows(farm, 2032, "dairy", 70, 1300)                                    # effectif en hausse au 6e exercice
    client.post(f"{farm['url'](2032)}/cow-provision", json={"constitute": False})
    entry = JournalEntry.query.filter_by(source=SOURCE_COW_PROVISION, fiscal_year_id=fy[2032].id).one()
    assert ("7873", 0, 773333) in _lines(entry)
    lines = client.get(f"{farm['url'](2032)}/tax-result").get_json()["item"]["lines"]
    assert any(l["key"].startswith("cow_exempt_") and l["amount_cents"] == -773333 for l in lines)


def test_value_waiver_and_exclusions(farm):
    client, fy = farm["client"], farm["fy"]
    _cows(farm, 2025, "dairy", 40, 1200)
    _cows(farm, 2026, "dairy", 45, 1300)
    client.post(f"{farm['url'](2026)}/cow-provision", json={"constitute": True})
    _cows(farm, 2027, "dairy", 40, 1500)                                    # 5 sorties mais valeur ≥ constitution
    assert client.get(f"{farm['url'](2027)}/cow-provision").get_json()["item"]["plan"] == []
    db.session.add(TaxOption(code="stock_freeze_72_b_bis", start_date=date(2027, 1, 1)))
    db.session.commit()
    prop = client.get(f"{farm['url'](2027)}/cow-provision").get_json()["item"]["proposal"]
    assert prop["eligible"] is False and "72 B bis" in prop["reason"]
    assert client.post(f"{farm['url'](2027)}/cow-provision", json={"constitute": True}).status_code == 422
