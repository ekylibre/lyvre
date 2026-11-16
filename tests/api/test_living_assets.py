"""Lot AG5.a : biens vivants immobilisés, lots, sortie partielle au coût moyen, cession en 6571 / 7571 (AGD22)."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, Asset, FiscalYear, Journal, JournalEntry
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
    return {"client": client, "fy": fy}


def _asset(client, status=201, **data):
    resp = client.post("/api/v1/assets", json=data)
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()["item"] if status == 201 else resp.get_json()


def _lot(client):
    lot = _asset(client, label="Truies", account_id=_id("241"), acquired_on="2026-01-01", in_service_date="2026-01-01",
                 acquisition_cents=0, method="linear", duration_months=60, species="Porc", age_class="Truies")
    for label, units, cents in (("Truies 2024", 10, 300000), ("Truies 2025", 30, 1200000)):
        _asset(client, label=label, account_id=_id("241"), acquired_on="2026-01-01", in_service_date="2026-01-01",
               acquisition_cents=cents, method="linear", duration_months=60, parent_id=lot["id"], units=units,
               origin="purchase")
    return client.get(f"/api/v1/assets/{lot['id']}").get_json()["item"]


def test_living_fields_and_lot(farm):
    lot = _lot(farm["client"])
    assert lot["living"] == {"kind": "breeding", "species": "Porc", "age_class": "Truies", "units": 40, "origin": None}
    service = _asset(farm["client"], label="Cheval de trait", account_id=_id("243"), acquired_on="2026-01-01",
                     acquisition_cents=500000, method="linear", duration_months=96, units=1)
    assert service["living"]["kind"] == "service"
    machine = _asset(farm["client"], label="Tracteur", account_id=_id("2154"), acquired_on="2026-01-01",
                     acquisition_cents=500000, method="linear", duration_months=60, units=3, species="x")
    assert machine["living"] is None
    patched = farm["client"].patch(f"/api/v1/assets/{service['id']}", json={"notes": "Comtois"}).get_json()["item"]
    assert patched["living"]["kind"] == "service" and patched["living"]["units"] == 1          # champs gardés
    items = farm["client"].get("/api/v1/assets?living=1").get_json()["items"]
    assert {i["label"] for i in items} == {"Truies", "Cheval de trait"}
    assert _asset(farm["client"], 422, label="x", account_id=_id("241"), acquired_on="2026-01-01", acquisition_cents=1,
                  method="none", living_kind="cattle")




def test_partial_exit_splits_each_component(farm):
    client = farm["client"]
    lot = _lot(client)
    url = f"/api/v1/assets/{lot['id']}/living-exit"
    assert client.post(url, json={"date": "2026-06-30", "kind": "sold", "units": 0}).status_code == 422
    resp = client.post(url, json={"date": "2026-06-30", "kind": "sold", "units": 10, "price_cents": 200000})
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    exited = body["exited"]
    assert exited["acquisition_cents"] == 375000 and exited["living"]["units"] == 10       # 1/4 de chaque composant
    assert body["item"]["acquisition_cents"] == 1125000 and body["item"]["living"]["units"] == 30
    entry = JournalEntry.query.filter(JournalEntry.description.like("Cession%")).one()
    codes = {l.account.code for l in entry.lines}
    assert "6571" in codes and "7571" in codes and "6578" not in codes and "7578" not in codes
    assert not any(c.key == "living_disposal" for c in closing._agri_checks(farm["fy"]))


def test_full_exit_and_other_assets(farm):
    client = farm["client"]
    horse = _asset(client, label="Cheval", account_id=_id("243"), acquired_on="2026-01-01", in_service_date="2026-01-01",
                   acquisition_cents=500000, method="linear", duration_months=96, units=1)
    resp = client.post(f"/api/v1/assets/{horse['id']}/living-exit", json={"date": "2026-12-01", "kind": "sold", "price_cents": 300000})
    assert resp.status_code == 200, resp.get_json()
    assert Asset.query.get(horse["id"]).status == "sold"
    tractor = _asset(client, label="Tracteur", account_id=_id("2154"), acquired_on="2026-01-01", in_service_date="2026-01-01",
                     acquisition_cents=500000, method="linear", duration_months=60)
    assert client.post(f"/api/v1/assets/{tractor['id']}/living-exit", json={"date": "2026-12-01", "kind": "sold",
                                                                            "units": 1}).status_code == 422
    client.post(f"/api/v1/assets/{tractor['id']}/dispose", json={"date": "2026-12-01", "kind": "sold", "price_cents": 100000})
    entry = JournalEntry.query.filter(JournalEntry.description == "Cession — Tracteur").one()
    assert "6578" in {l.account.code for l in entry.lines} and "7578" in {l.account.code for l in entry.lines}
