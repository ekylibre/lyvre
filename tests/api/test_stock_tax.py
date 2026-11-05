"""Lot AG4.e : valeur fiscale des stocks (design_inventaire_agricole.md § 6, AGD21).

- forfaitaire : 100 t de blé au cours de 200 €/t → 16 000 € (−20 %) ; bovins −30 % ; refusée sur les approvisionnements ;
- stock bloqué (72 B bis, règle proposée Q-S5) : 100 unités à 10 € avant l'option, 80 l'exercice suivant, 120 ensuite →
  80 bloquées à 10 € + 40 à la valeur comptable.
"""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, FiscalYear, StockLine, TaxOption
from app.services import closing, stock_tax
from test_agri_fixtures import _agri_instance


@pytest.fixture()
def farm(app, login_as):
    client = login_as(role="admin")
    _agri_instance()
    years = {y: FiscalYear(label=str(y), start_date=date(y, 1, 1), end_date=date(y, 12, 31)) for y in (2024, 2025, 2026)}
    db.session.add_all(years.values())
    db.session.commit()
    return {"client": client, "fy": years, "url": lambda y: f"/api/v1/fiscal-years/{years[y].id}/stock"}


def _post(farm, year, status=201, **data):
    resp = farm["client"].post(f"{farm['url'](year)}/lines", json=data)
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()


def _item(body, label):
    return next(i for i in body["item"]["items"] if i["label"] == label)


def test_flat_fiscal_value_and_gap(farm):
    body = _post(farm, 2026, account_code="35511", label="Blé", quantity="100", unit="t", method="actual",
                 unit_value_cents=15000, market_price_cents=20000)
    item = _item(body, "Blé")
    assert item["fiscal"]["fiscal_method"] == "none" and item["fiscal"]["gap_cents"] == 0
    assert item["fiscal"]["allowed"] == ["none", "manual"]
    line = StockLine.query.one()
    url = f"{farm['url'](2026)}/lines/{line.id}"
    assert farm["client"].put(url, json={"fiscal_method": "flat"}).status_code == 422            # sans option
    db.session.add(TaxOption(code="flat_stock_method", start_date=date(2024, 1, 1)))
    db.session.commit()
    body = farm["client"].put(url, json={"fiscal_method": "flat"}).get_json()
    fiscal = _item(body, "Blé")["fiscal"]
    assert fiscal["fiscal_value_cents"] == 1600000 and fiscal["gap_cents"] == 100000
    assert body["item"]["fiscal"]["gap_cents"] == 100000 and body["item"]["fiscal"]["flat"] is True
    cows = _post(farm, 2026, account_code="3112", label="Vaches", quantity="10", unit="head", method="actual",
                 unit_value_cents=120000, market_price_cents=150000, flat_rate="cattle_wine", fiscal_method="flat")
    assert _item(cows, "Vaches")["fiscal"]["fiscal_value_cents"] == 1050000                       # −30 %
    assert _post(farm, 2026, 422, account_code="31111", label="Engrais", quantity="1", method="actual",
                 unit_value_cents=100, fiscal_method="flat")["error"]["fields"]["fiscal_method"]
    manual = _post(farm, 2026, 422, account_code="35513", label="Jus", quantity="1", method="actual", unit_value_cents=100,
                   fiscal_method="manual", fiscal_value_cents=50)
    assert "Motif" in manual["error"]["message"]


def test_frozen_stock_72_b_bis(farm):
    db.session.add(TaxOption(code="stock_freeze_72_b_bis", start_date=date(2025, 1, 1), duration_years=5, tacit_renewal=True))
    db.session.commit()
    for year, quantity, unit in ((2024, "100", 1000), (2025, "80", 1200), (2026, "120", 1500)):
        _post(farm, year, account_code="35513", label="Cognac", production="Cognac", quantity=quantity, unit="l",
              method="actual", unit_value_cents=unit, **({"fiscal_method": "frozen"} if year > 2024 else {}))
    body = farm["client"].get(farm["url"](2026)).get_json()
    fiscal = _item(body, "Cognac")["fiscal"]
    assert fiscal["frozen"]["reference_year"] == "2024" and fiscal["frozen"]["reference_unit_cents"] == 1000
    assert fiscal["frozen"]["blocked_quantity"] == "80.000" and fiscal["frozen"]["surplus_quantity"] == "40.000"
    assert fiscal["fiscal_value_cents"] == 140000 and fiscal["gap_cents"] == -40000              # 180 000 en comptabilité
    assert any("Q-S5" in w for w in fiscal["warnings"])
    assert _item(farm["client"].get(farm["url"](2025)).get_json(), "Cognac")["fiscal"]["fiscal_value_cents"] == 80000
    assert farm["client"].post(f"{farm['url'](2026)}/lines", json={"account_code": "31111", "label": "x", "quantity": "1",
                                                                    "fiscal_method": "frozen"}).status_code == 422


def test_closing_checks_and_export(farm):
    db.session.add(TaxOption(code="flat_stock_method", start_date=date(2024, 1, 1)))
    db.session.commit()
    _post(farm, 2026, account_code="35511", label="Blé", quantity="10", unit="t", method="actual", unit_value_cents=15000)
    checks = {c.key: c for c in closing._agri_checks(farm["fy"][2026])}
    assert checks["stock_fiscal"].count == 1 and checks["stock_fiscal"].severity == "info"
    totals = stock_tax.totals(farm["fy"][2026])
    assert totals["accounting_cents"] == totals["fiscal_cents"] == 150000 and totals["gap_cents"] == 0
    xlsx = farm["client"].get(f"/fiscal-years/{farm['fy'][2026].id}/stock.xlsx")
    assert xlsx.status_code == 200 and xlsx.data[:2] == b"PK"
    assert Account.query.filter_by(code="35511").count() == 1
