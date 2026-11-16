"""Lot AG11.c : clés de répartition depuis les coûts des interventions Ekylibre (instantané fictif)."""
from datetime import date, datetime
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import AnalyticKey, AnalyticRule, FiscalYear
from app.services import analytic, ekylibre_keys, ekylibre_sync, external_config, import_activities
from app.services.ekylibre_client import Intervention, Production

from test_agri_fixtures import _agri_instance

API = "/api/v1/ekylibre"


def _plant(pid, activity_id, ha):
    return Production(id=pid, name=f"Culture {pid}", activity_id=activity_id, activity_name=f"A{activity_id}",
                      surface_ha=Decimal(ha), started_on=date(2025, 10, 1), stopped_on=date(2026, 8, 31))


def _intervention(iid, day, targets, inputs=0, doers=0, tools=0, seconds=0, nature="record", state="done", with_tools=True):
    return Intervention(id=iid, nature=nature, procedure="x", name=f"I{iid}", state=state,
                        started_at=datetime(day.year, day.month, day.day, 8), stopped_at=None, working_seconds=seconds,
                        costs={"inputs": Decimal(inputs), "doers": Decimal(doers), "tools": Decimal(tools),
                               "receptions": Decimal(0)},
                        targets=targets, tools=[40] if with_tools else [])


@pytest.fixture()
def farm(app, login_as):
    client = login_as(role="admin")
    _agri_instance()
    external_config.set_enabled("ekylibre", True)
    db.session.add(FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)))
    workshop = import_activities._workshop("plant_farming")
    for name, eky in (("Blé tendre", 3), ("Maïs grain", 4)):
        analytic.save_activity(None, {"workshop_id": workshop.id, "name": name}).ekylibre_id = eky
    db.session.commit()
    ekylibre_sync.save_snapshot("productions", [_plant(1, 3, "10"), _plant(2, 4, "5"), _plant(3, 9, "5")])
    ekylibre_sync.save_snapshot("interventions", [
        _intervention(1, date(2026, 3, 2), [1, 2], inputs=300, doers=60, tools=30, seconds=10800),
        _intervention(2, date(2026, 4, 1), [3], inputs=100),                         # culture non rattachée
        _intervention(3, date(2026, 4, 2), [1], inputs=999, nature="request"),       # demande : ignorée
        _intervention(4, date(2026, 4, 3), [1], inputs=999, state="rejected"),       # rejetée : ignorée
        _intervention(5, date(2025, 12, 1), [1], inputs=999),                        # hors exercice
        _intervention(6, date(2026, 5, 1), [], doers=50),                            # sans cible
    ])
    db.session.commit()
    return client


def _key(data, kind):
    return next(k for k in data["keys"] if k["kind"] == kind)


def test_compute(farm):
    data = farm.get(f"{API}/keys").get_json()
    assert (data["interventions"], data["without_target"]) == (3, 1)
    inputs = _key(data, "inputs")
    assert [(m["activity"], m["amount"], m["share_bp"]) for m in inputs["members"]] == [
        ("Blé tendre", "200.00", 6667), ("Maïs grain", "100.00", 3333)]
    assert inputs["unassigned"] == "100.00"
    assert _key(data, "doers")["unassigned"] == "50.00"
    hours = _key(data, "hours")
    assert [(m["amount"], m["share_bp"]) for m in hours["members"]] == [("2.00", 6667), ("1.00", 3333)]
    assert data["fiscal_years"][0]["label"] == "2026"


def test_apply_keys_and_rules(farm):
    resp = farm.post(f"{API}/keys", json={})
    assert resp.status_code == 200, resp.get_json()
    assert set(resp.get_json()["applied"]) == set(ekylibre_keys.KEYS.values())
    key = AnalyticKey.query.filter_by(name="Intrants (Ekylibre)").one()
    assert (key.basis, key.source) == ("percentage", "ekylibre") and key.synced_at is not None
    assert sorted(m.share_bp for m in key.members) == [3333, 6667] and "3 intervention(s)" in key.note
    # Nouveau calcul : la clé est refaite, pas doublée.
    farm.post(f"{API}/keys", json={})
    assert AnalyticKey.query.filter_by(name="Intrants (Ekylibre)").count() == 1
    rules = {r["prefix"]: r for r in farm.get(f"{API}/keys").get_json()["rules"]}
    assert rules and all(r["existing"] is None and r["key_id"] for r in rules.values())
    prefix = next(iter(rules))
    resp = farm.post(f"{API}/rules", json={"prefixes": [prefix]})
    assert resp.status_code == 200, resp.get_json()
    rule = AnalyticRule.query.filter_by(account_prefix=prefix).one()
    assert rule.key.name == rules[prefix]["key"]
    assert farm.post(f"{API}/rules", json={"prefixes": [prefix]}).status_code == 409      # déjà une règle


def test_refusals(farm):
    db.session.add(AnalyticKey(name="Intrants (Ekylibre)", basis="percentage"))
    db.session.commit()
    assert farm.post(f"{API}/keys", json={}).status_code == 409                           # nom pris par une clé saisie
    assert farm.post(f"{API}/rules", json={"prefixes": []}).status_code == 422
    fy = FiscalYear(label="2030", start_date=date(2030, 1, 1), end_date=date(2030, 12, 31))
    db.session.add(fy)
    db.session.commit()
    assert farm.post(f"{API}/keys", json={"fiscal_year_id": fy.id}).status_code == 409    # aucune intervention


def test_shares_sum():
    shares = ekylibre_keys._shares({1: Decimal(1), 2: Decimal(1), 3: Decimal(1)})
    assert sum(shares.values()) == 10000 and sorted(shares.values()) == [3333, 3333, 3334]
    assert ekylibre_keys._shares({1: Decimal(0)}) == {}
