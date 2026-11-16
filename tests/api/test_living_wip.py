"""Lot AG5.b : biens vivants en cours (234x / 7222), mise en service, animal du stock devenu reproducteur (724)."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, Asset, FiscalYear, Journal, JournalEntry, StockLotMovement
from app.models.journal_entry import SOURCE_LIVING_WIP
from app.services import closing
from test_agri_fixtures import _agri_instance


def _id(code):
    return Account.query.filter_by(code=code).one().id


@pytest.fixture()
def farm(app, login_as):
    client = login_as(role="admin")
    _agri_instance()
    years = {y: FiscalYear(label=str(y), start_date=date(y, 1, 1), end_date=date(y, 12, 31)) for y in (2025, 2026)}
    db.session.add_all([*years.values(), Journal(code="OD", label="OD")])
    db.session.commit()
    return {"client": client, "fy": years}


def _lines(entry):
    return {(l.account.code, l.debit_cents, l.credit_cents) for l in entry.lines}


def test_wip_costs_then_in_service(farm):
    client, fy = farm["client"], farm["fy"]
    resp = client.post("/api/v1/assets", json={"label": "Génisses de renouvellement", "account_id": _id("2341"),
                                               "acquired_on": "2025-03-01", "acquisition_cents": 200000, "method": "linear",
                                               "duration_months": 72, "units": 10, "species": "Bovin", "origin": "born"})
    asset = resp.get_json()["item"]
    assert asset["status"] == "waiting" and asset["living"]["kind"] == "breeding"
    url = f"/api/v1/fiscal-years/{fy[2025].id}/closing/living-wip"
    (row,) = client.get(url).get_json()["items"]
    assert row["amount_cents"] is None and any(c.key == "living_wip_missing" for c in closing._agri_checks(fy[2025]))
    client.put(f"{url}/costs", json={"asset_id": asset["id"], "amount_cents": 150000, "basis": "coût standard élevage"})
    assert any(c.key == "living_wip_entry" and c.severity == "anomaly" for c in closing._agri_checks(fy[2025]))
    assert client.post(url).status_code == 200
    entry = JournalEntry.query.filter_by(source=SOURCE_LIVING_WIP).one()
    assert _lines(entry) == {("2341", 150000, 0), ("7222", 0, 150000)} and entry.entry_date == date(2025, 12, 31)
    assert db.session.get(Asset, asset["id"]).acquisition_cents == 350000
    client.post(url)                                                                        # repassée
    assert db.session.get(Asset, asset["id"]).acquisition_cents == 350000
    assert JournalEntry.query.filter_by(source=SOURCE_LIVING_WIP).count() == 1
    assert client.put(f"{url}/costs", json={"asset_id": asset["id"], "amount_cents": 1}).status_code == 409
    resp = client.post(f"/api/v1/assets/{asset['id']}/in-service", json={"date": "2026-03-01"})
    assert resp.status_code == 200, resp.get_json()
    item = resp.get_json()["item"]
    assert item["account"]["code"] == "241" and item["acquisition_cents"] == 350000             # 2341 → 241, cumul viré
    service = JournalEntry.query.filter(JournalEntry.description.like("Mise en service%")).one()
    assert _lines(service) == {("241", 350000, 0), ("2341", 0, 350000)}
    assert client.delete(url).status_code == 409                                             # bien mis en service


def test_animal_from_stock_becomes_breeder(farm):
    client = farm["client"]
    q = f"?fiscal_year_id={farm['fy'][2026].id}"
    lot = client.post(f"/api/v1/stock-lots{q}", json={"species": "Porc", "age_class": "Cochettes", "account_code": "3113"}).get_json()["item"]
    client.post(f"/api/v1/stock-lots/{lot['id']}/movements{q}", json={"on": "2026-01-01", "kind": "opening", "heads": 20})
    url = f"/api/v1/stock-lots/{lot['id']}/to-fixed-assets"
    assert client.post(url, json={"on": "2026-04-01", "heads": 5, "value_cents": 0}).status_code == 422
    assert client.post(url, json={"on": "2026-04-01", "heads": 5, "value_cents": 150000, "account_code": "3113"}).status_code == 422
    resp = client.post(url, json={"on": "2026-04-01", "heads": 5, "value_cents": 150000, "duration_months": 36})
    assert resp.status_code == 201, resp.get_json()
    asset = resp.get_json()["item"]
    assert asset["account"]["code"] == "241" and asset["status"] == "in_use"
    assert asset["living"] == {"kind": "breeding", "species": "Porc", "age_class": "Cochettes", "units": 5, "origin": "from_stock"}
    entry = JournalEntry.query.filter(JournalEntry.description.like("Entrée en production%")).one()
    assert _lines(entry) == {("241", 150000, 0), ("724", 0, 150000)}
    body = client.get(f"/api/v1/stock-lots/{lot['id']}{q}").get_json()["item"]
    assert body["summary"]["theoretical"] == 15 and body["movements"][-1]["asset"]["id"] == asset["id"]
    movement = StockLotMovement.query.filter_by(kind="to_fixed_assets").one()
    assert client.delete(f"/api/v1/stock-lots/{lot['id']}/movements/{movement.id}{q}").status_code == 200
    assert db.session.get(Asset, asset["id"]) is None and JournalEntry.query.filter(
        JournalEntry.description.like("Entrée en production%")).count() == 0


def test_from_stock_into_existing_breeding_lot(farm):
    client = farm["client"]
    q = f"?fiscal_year_id={farm['fy'][2026].id}"
    herd = client.post("/api/v1/assets", json={"label": "Truies", "account_id": _id("241"), "acquired_on": "2026-01-01",
                                               "in_service_date": "2026-01-01", "acquisition_cents": 0, "method": "linear",
                                               "duration_months": 48}).get_json()["item"]
    client.post("/api/v1/assets", json={"label": "Truies 2025", "account_id": _id("241"), "acquired_on": "2026-01-01",
                                        "in_service_date": "2026-01-01", "acquisition_cents": 900000, "method": "linear",
                                        "duration_months": 48, "parent_id": herd["id"], "units": 30})
    lot = client.post(f"/api/v1/stock-lots{q}", json={"species": "Porc", "age_class": "Cochettes", "account_code": "3113"}).get_json()["item"]
    resp = client.post(f"/api/v1/stock-lots/{lot['id']}/to-fixed-assets",
                       json={"on": "2026-05-01", "heads": 4, "value_cents": 120000, "parent_id": herd["id"]})
    assert resp.status_code == 201, resp.get_json()
    herd_now = client.get(f"/api/v1/assets/{herd['id']}").get_json()["item"]
    assert herd_now["living"]["units"] == 34 and herd_now["acquisition_cents"] == 1020000
    assert resp.get_json()["item"]["duration_months"] == 48                                   # durée du lot reprise


def test_plantations_cg5d(farm):
    """Lot CG5.d (BOI-BA-BASE-20-30-10-20) : façons culturales des jeunes plantations en avances aux cultures par défaut
    (pas d'alerte « en-cours sans coût »), annuité entière depuis l'exercice de la première récolte, repères de durée."""
    from app.services import agri_profile, assets
    client, fy = farm["client"], farm["fy"]
    resp = client.post("/api/v1/assets", json={"label": "Vigne parcelle 4", "account_id": _id("2346"),
                                               "acquired_on": "2025-04-01", "acquisition_cents": 1500000, "method": "linear",
                                               "duration_months": 300, "units": 5000, "species": "Vigne"})
    vine = resp.get_json()["item"]
    assert vine["living"]["kind"] == "plantation" and vine["full_first_year"] is True
    assert not any(c.key == "living_wip_missing" for c in closing._agri_checks(fy[2025]))   # charges : pas d'alerte
    org_profile = agri_profile.clean({"plantation_costs_capitalized": True})
    from app.services import organization
    organization.get().agri_profile = __import__("json").dumps(org_profile)
    db.session.commit()
    assert any(c.key == "living_wip_missing" for c in closing._agri_checks(fy[2025]))       # coûts immobilisés : alerte
    asset = db.session.get(Asset, vine["id"])
    asset.in_service_date, asset.status = date(2026, 9, 15), "in_use"
    db.session.commit()
    assert assets.plan_bounds(asset)[0] == date(2026, 1, 1)                                 # 1er jour de l'exercice 2026
    asset.full_first_year = False
    assert assets.plan_bounds(asset)[0] == date(2026, 9, 15)
    meta = client.get("/api/v1/assets").get_json()["meta"]["plantation_references"]
    assert meta["vine_years"] == 25 and any(s["key"] == "apple" for s in meta["orchards"]["species"])
    assert "BOI-ANNX-000100" in meta["orchards"]["source_label"]
