"""Lot AG5.d : reproducteur en stock (option du profil, AGD22 Q-B6), sortie de lot sans fiche, effectifs de l'annexe."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, FiscalYear, Journal, TaxOption
from app.services import closing
from test_agri_fixtures import _agri_instance


def _id(code):
    return Account.query.filter_by(code=code).one().id


@pytest.fixture()
def farm(app, login_as):
    client = login_as(role="admin")
    _agri_instance()
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    db.session.add_all([fy, Journal(code="OD", label="OD")])
    db.session.commit()
    return {"client": client, "fy": fy, "stock": f"/api/v1/fiscal-years/{fy.id}/stock", "q": f"?fiscal_year_id={fy.id}"}


def _checks(fy):
    return {c.key: c for c in closing._agri_checks(fy)}


def test_breeder_in_stock_warning_and_option(farm):
    client = farm["client"]
    body = client.post(f"{farm['stock']}/lines", json={"account_code": "3112", "label": "Truies gestantes", "quantity": "12",
                                                       "unit": "head", "method": "actual", "unit_value_cents": 30000}).get_json()
    (line,) = body["item"]["items"]
    assert any("Reproducteur en stock" in w for w in line["warnings"])
    assert _checks(farm["fy"])["stock_breeders"].count == 1
    lot = client.post(f"/api/v1/stock-lots{farm['q']}", json={"species": "Ovin", "age_class": "Agnelles", "account_code": "3113",
                                                              "destination": "breeding"}).get_json()["item"]
    body = client.post(f"{farm['stock']}/lines", json={"lot_id": lot["id"], "heads": 30, "unit": "head", "method": "actual",
                                                       "unit_value_cents": 15000}).get_json()
    assert sum(1 for i in body["item"]["items"] if any("Reproducteur" in w for w in i["warnings"])) == 2
    resp = client.post("/api/v1/tax-options", json={"code": "breeders_in_stock", "start_date": "2020-01-01"})
    assert resp.status_code == 201, resp.get_json()
    body = client.get(farm["stock"]).get_json()
    assert not any("Reproducteur" in w for i in body["item"]["items"] for w in i["warnings"])
    assert "stock_breeders" not in _checks(farm["fy"])
    assert TaxOption.query.filter_by(code="breeders_in_stock").count() == 1


def test_orphan_movement_and_headcount(farm):
    client, q = farm["client"], farm["q"]
    lot = client.post(f"/api/v1/stock-lots{q}", json={"species": "Bovin", "account_code": "3112"}).get_json()["item"]
    client.post(f"/api/v1/stock-lots/{lot['id']}/movements{q}", json={"on": "2026-01-01", "kind": "opening", "heads": 10})
    client.post(f"/api/v1/stock-lots/{lot['id']}/movements{q}", json={"on": "2026-03-01", "kind": "to_fixed_assets", "heads": 2})
    assert _checks(farm["fy"])["stock_to_assets_orphan"].count == 1
    herd = client.post("/api/v1/assets", json={"label": "Vaches allaitantes", "account_id": _id("241"), "acquired_on": "2026-01-01",
                                               "in_service_date": "2026-01-01", "acquisition_cents": 2000000, "method": "linear",
                                               "duration_months": 60, "units": 20, "species": "Bovin"}).get_json()["item"]
    client.post(f"/api/v1/assets/{herd['id']}/living-exits",
                json={"date": "2026-09-01", "kind": "sanitary_slaughter", "units": 5, "indemnity_cents": 100000})
    data = client.get(f"/api/v1/reports/living-assets?fy_id={farm['fy'].id}").get_json()["item"]
    (row,) = [r for r in data["headcount"] if r["kind"] == "breeding"]
    assert row == {"kind": "breeding", "label": "Animaux reproducteurs", "opening": 0, "entries": 20, "exits": 5, "closing": 15}
