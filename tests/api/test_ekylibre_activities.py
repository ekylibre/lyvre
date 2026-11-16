"""Lot AG11.b : activités et surfaces lues dans Ekylibre (instantané fictif, aucun appel à l'API)."""
from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import Activity, ActivityProduction, Campaign
from app.services import analytic, ekylibre_sync, external_config, import_activities
from app.services.ekylibre_client import Production

from test_agri_fixtures import _agri_instance

API = "/api/v1/ekylibre/activities"


def _plant(pid, activity_id, name, ha, stop=date(2026, 8, 31)):
    return Production(id=pid, name=f"Culture {pid}", activity_id=activity_id, activity_name=name, surface_ha=Decimal(ha),
                      started_on=date(2025, 10, 1), stopped_on=stop)


def _snapshot(plants, parcel_ha="10"):
    ekylibre_sync.save_snapshot("productions", plants)
    ekylibre_sync.save_snapshot("parcels", [Production(id=900, name="Îlot 1", activity_id=None, activity_name=None,
                                                       surface_ha=Decimal(parcel_ha), started_on=None, stopped_on=None)])
    db.session.commit()


@pytest.fixture()
def farm(app, login_as):
    client = login_as(role="admin")
    _agri_instance()
    external_config.set_enabled("ekylibre", True)
    workshop = import_activities._workshop("plant_farming")
    analytic.save_activity(None, {"workshop_id": workshop.id, "name": "Blé tendre"})
    prairie = analytic.save_activity(None, {"workshop_id": workshop.id, "name": "Prairie"})
    analytic.set_measure(prairie.id, 2026, {"measure": "3"})               # saisie à la main
    db.session.commit()
    _snapshot([_plant(1, 3, "Blé tendre", "12.5"), _plant(2, 3, "Blé tendre", "7.5"),
               _plant(3, 4, "Maïs grain", "4"), _plant(4, 5, "Prairie", "0.35"),
               Production(id=5, name="Sans surface", activity_id=6, activity_name="Vide", surface_ha=None,
                          started_on=None, stopped_on=None)])
    return client


def _activity(name):
    return Activity.query.filter_by(name=name).one()


def _measure(activity, year):
    return ActivityProduction.query.filter_by(activity_id=activity.id,
                                              campaign_id=Campaign.query.filter_by(year=year).one().id).one()


def test_rows(farm):
    data = farm.get(API).get_json()
    by_name = {r["name"]: r for r in data["items"]}
    assert set(by_name) == {"Blé tendre", "Maïs grain", "Prairie"}                # sans surface : ignorée
    assert by_name["Blé tendre"]["activity"]["how"] == "name"
    assert by_name["Blé tendre"]["campaigns"] == [{"year": 2026, "surface_ha": "20.00", "lyvre_ha": None, "state": "new"}]
    assert by_name["Maïs grain"]["activity"] is None and by_name["Maïs grain"]["proposal"]["lexicon_reference"]
    assert by_name["Prairie"]["campaigns"][0]["state"] == "conflict"
    assert any("2026" in w and "parcelles" in w for w in data["warnings"])        # 24,35 ha pour 10 ha


def test_apply_link_create_measures(farm):
    items = [{"ekylibre_id": 3}, {"ekylibre_id": 4, "create": True}, {"ekylibre_id": 5}]
    resp = farm.post(API, json={"items": items})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["stats"] == {"linked": 3, "created": 1, "measures": 2, "conflicts": 1}
    ble, mais, prairie = _activity("Blé tendre"), Activity.query.filter_by(ekylibre_id=4).one(), _activity("Prairie")
    assert (ble.ekylibre_id, prairie.ekylibre_id) == (3, 5) and mais.lexicon_reference
    m = _measure(ble, 2026)
    assert (m.measure, m.measure_source) == (Decimal("20.000"), "ekylibre")
    assert _measure(prairie, 2026).measure == Decimal("3.000")                     # saisie conservée
    year = analytic.campaign_year(mais, date(2026, 8, 31))
    assert _measure(mais, year).measure == Decimal("4.000")
    # Nouvelle lecture : la surface Ekylibre est mise à jour, la saisie reste.
    _snapshot([_plant(1, 3, "Blé tendre", "12.5"), _plant(2, 3, "Blé tendre", "9.5"), _plant(4, 5, "Prairie", "0.35")])
    rows = {r["name"]: r for r in farm.get(API).get_json()["items"]}
    assert rows["Blé tendre"]["activity"]["how"] == "ekylibre" and rows["Blé tendre"]["campaigns"][0]["state"] == "update"
    farm.post(API, json={"items": [{"ekylibre_id": 3}, {"ekylibre_id": 5}]})
    assert _measure(ble, 2026).measure == Decimal("22.000")
    # Saisie à la main ensuite : plus jamais écrasée.
    analytic.set_measure(ble.id, 2026, {"measure": "21"})
    db.session.commit()
    farm.post(API, json={"items": [{"ekylibre_id": 3}]})
    assert _measure(ble, 2026).measure == Decimal("21.000")


def test_apply_refusals(farm):
    assert farm.post(API, json={"items": []}).status_code == 422
    assert farm.post(API, json={"items": [{"ekylibre_id": 99}]}).status_code == 409
    assert farm.post(API, json={"items": [{"ekylibre_id": 4}]}).status_code == 422      # ni rattachée ni créée
    # Rattachement explicite : l'identifiant Ekylibre passe d'une activité à l'autre.
    farm.post(API, json={"items": [{"ekylibre_id": 3}]})
    assert _activity("Blé tendre").ekylibre_id == 3
    prairie = _activity("Prairie")
    farm.post(API, json={"items": [{"ekylibre_id": 3, "activity_id": prairie.id}]})
    assert prairie.ekylibre_id == 3 and _activity("Blé tendre").ekylibre_id is None
