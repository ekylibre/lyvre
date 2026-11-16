"""Lot AG11.d : quantités d'inventaire depuis les matières Ekylibre (instantané fictif, aucun appel à l'API)."""
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import EkylibreSnapshot, EkylibreVariantLink, FiscalYear, StockLine
from app.services import ekylibre_inventory, ekylibre_sync, external_config, stock_inventory
from app.services.ekylibre_client import Matter

from test_agri_fixtures import _agri_instance

API = "/api/v1/ekylibre/inventory"


def _matter(mid, variant, name, qty, unit):
    return Matter(id=mid, name=name, variant_id=variant, variety="x", quantity=Decimal(qty), unit=unit)


def _snapshot(matters, at: datetime):
    ekylibre_sync.save_snapshot("matters", matters)
    db.session.flush()
    EkylibreSnapshot.query.filter_by(kind="matters").one().synced_at = at
    db.session.commit()


@pytest.fixture()
def farm(app, login_as):
    client = login_as(role="admin")
    _agri_instance()
    external_config.set_enabled("ekylibre", True)
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    db.session.add(fy)
    db.session.flush()
    stock_inventory.create_line(fy, {"account_code": "31111", "label": "Ammonitrate", "unit": "t", "quantity": "0",
                                     "unit_value_cents": 40000})
    db.session.commit()
    _snapshot([_matter(1, 9, "Ammonitrate lot A", "1200", "kg"), _matter(2, 9, "Ammonitrate lot B", "0.5", "tonne"),
               _matter(3, 10, "Gazole non routier", "15", "hectolitre"), _matter(4, 11, "Ficelle", "3", "bobine")],
              datetime(2026, 12, 29, 18))
    return client


def _fy():
    return FiscalYear.query.filter_by(label="2026").one()


def test_units():
    assert ekylibre_inventory.convert(Decimal("1200"), "kg", "t") == Decimal("1.200")
    assert ekylibre_inventory.convert(Decimal("15"), "hl", "l") == Decimal("1500.000")
    assert ekylibre_inventory.convert(Decimal("1"), "kg", "l") is None
    assert ekylibre_inventory.lyvre_unit("Tonne") == "t" and ekylibre_inventory.lyvre_unit("bobine") is None


def test_rows_and_apply(farm):
    data = farm.get(API).get_json()
    assert data["inventory_date"] == "2026-12-31" and data["gap_days"] == 2 and data["allowed"]
    items = {i["variant_id"]: i for i in data["items"]}
    assert items[9]["quantity"] == "1700" and items[9]["unit"] == "kg" and items[9]["matters"] == 2
    assert items[11]["unit"] is None and items[11]["raw_unit"] == "bobine"
    line = StockLine.query.filter_by(label="Ammonitrate").one()
    resp = farm.post(API, json={"items": [
        {"variant_id": 9, "line_id": line.id},
        {"variant_id": 10, "create": {"account_code": "32", "label": "GNR"}},
        {"variant_id": 11, "create": {"account_code": "32"}},
    ]})
    assert resp.status_code == 200, resp.get_json()
    stats = resp.get_json()["stats"]
    assert (stats["filled"], stats["created"]) == (2, 2)
    assert stats["skipped"] == ["Ficelle (bobine → unit)"]                    # unité inconnue : non reportée
    assert Decimal(line.quantity) == Decimal("1.700") and line.value_cents == 68000      # valeur recalculée (AG4)
    gnr = StockLine.query.filter_by(label="GNR").one()
    assert (gnr.unit, Decimal(gnr.quantity)) == ("hl", Decimal("15.000"))
    ficelle = StockLine.query.filter_by(label="Ficelle").one()
    assert (ficelle.unit, Decimal(ficelle.quantity)) == ("unit", Decimal("0"))
    # Correspondance mémorisée : la lecture suivante retrouve la ligne sans choix.
    assert EkylibreVariantLink.query.count() == 3
    rows = {i["variant_id"]: i for i in farm.get(API).get_json()["items"]}
    assert rows[9]["line"]["label"] == "Ammonitrate" and rows[9]["converted"] == "1.7"
    _snapshot([_matter(1, 9, "Ammonitrate", "2", "t")], datetime(2026, 12, 30, 9))
    farm.post(API, json={"items": [{"variant_id": 9}]})
    assert Decimal(line.quantity) == Decimal("2.000")


def test_incompatible_unit_skipped(farm):
    line = StockLine.query.filter_by(label="Ammonitrate").one()
    stock_inventory.update_line(_fy(), line, {"unit": "l"})
    db.session.commit()
    resp = farm.post(API, json={"items": [{"variant_id": 9, "line_id": line.id}]})
    assert resp.status_code == 200 and resp.get_json()["stats"]["skipped"]
    assert Decimal(line.quantity) == 0


def test_gap_refused(farm):
    _snapshot([_matter(1, 9, "Ammonitrate", "2", "t")], datetime(2026, 12, 31) - timedelta(days=20))
    data = farm.get(API).get_json()
    assert not data["allowed"] and data["gap_days"] == 20
    resp = farm.post(API, json={"items": [{"variant_id": 9, "line_id": StockLine.query.first().id}]})
    assert resp.status_code == 409 and "20 jours" in resp.get_json()["error"]["message"]
    # Date de comptage saisie : elle remplace la fin d'exercice.
    stock_inventory.set_settings(_fy(), {"counted_on": "2026-12-12"})
    db.session.commit()
    assert farm.get(API).get_json()["allowed"]
