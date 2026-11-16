"""Lot AG4.b : lots d'animaux en stock et mouvements (design_inventaire_agricole.md § 5.5, AGD21 Q-S8).

Recette du design (§ 13) : 120 porcelets à l'ouverture, 300 naissances, 280 ventes et 4 morts donnent un effectif
théorique de 136 ; 135 comptés signalent un écart d'une tête ; valeur = 135 × valeur par tête.
"""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, FiscalYear, StockLine
from test_agri_fixtures import _agri_instance


@pytest.fixture()
def farm(app, login_as):
    client = login_as(role="admin")
    _agri_instance()
    previous = FiscalYear(label="2025", start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    db.session.add_all([previous, fy])
    db.session.commit()
    return {"client": client, "fy": fy, "previous": previous, "q": f"?fiscal_year_id={fy.id}",
            "stock": f"/api/v1/fiscal-years/{fy.id}/stock"}


def _lot(client, q="", **data):
    resp = client.post(f"/api/v1/stock-lots{q}", json=data)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["item"]


def _move(client, lot_id, q, status=201, **data):
    resp = client.post(f"/api/v1/stock-lots/{lot_id}/movements{q}", json=data)
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()


def test_theoretical_heads_and_gap(farm):
    client, q = farm["client"], farm["q"]
    lot = _lot(client, q, species="Porc", age_class="Porcelets", account_code="3113", average_weight_kg="25")
    assert lot["label"] == "Porc — Porcelets" and lot["summary"]["theoretical"] == 0
    previous_line = StockLine(fiscal_year_id=farm["previous"].id, category="animals_short", label="Porcelets",
                              quantity=120, unit="head", method="actual", unit_value_cents=6000, lot_id=lot["id"], heads=120,
                              account_id=Account.query.filter_by(code="3113").one().id,
                              variation_account_id=Account.query.filter_by(code="713552").one().id)
    db.session.add(previous_line)
    db.session.commit()
    for kind, heads in (("birth", 300), ("sale", 280), ("death", 4)):
        _move(client, lot["id"], q, on="2026-06-01", kind=kind, heads=heads)
    assert _move(client, lot["id"], q, 409, on="2026-01-01", kind="opening", heads=10)["error"]["code"] == "conflict"
    summary = client.get(f"/api/v1/stock-lots/{lot['id']}{q}").get_json()["item"]["summary"]
    assert summary["opening"] == 120 and summary["opening_source"] == "previous" and summary["theoretical"] == 136
    body = client.post(f"{farm['stock']}/lines", json={"lot_id": lot["id"], "heads": 135, "unit": "head",
                                                        "method": "actual", "unit_value_cents": 6500}).get_json()
    (line,) = [i for i in body["item"]["items"] if i["lot_id"] == lot["id"]]
    assert line["account"]["code"] == "3113" and line["label"] == "Porc — Porcelets" and line["value_cents"] == 877500
    assert any("Écart de -1 tête" in w for w in line["warnings"])
    body = client.put(f"{farm['stock']}/lines/{line['id']}", json={"gap_reason": "porcelet écrasé non déclaré"}).get_json()
    assert not any("Écart" in w for w in body["item"]["items"][0]["warnings"])
    body = client.put(f"{farm['stock']}/lines/{line['id']}", json={"unit": "kg", "unit_value_cents": 260}).get_json()
    assert body["item"]["items"][0]["quantity"] == "3375.000" and body["item"]["items"][0]["value_cents"] == 877500
    assert body["item"]["lots"][0]["summary"]["counted"] == 135
    assert client.post(f"{farm['stock']}/lines", json={"lot_id": lot["id"], "heads": 1}).status_code == 409


def test_transfer_between_lots_and_opening(farm):
    client, q = farm["client"], farm["q"]
    young = _lot(client, q, species="Bovin", age_class="Génisses 0-1 an", account_code="3112")
    older = _lot(client, q, species="Bovin", age_class="Génisses 1-2 ans", account_code="3112")
    _move(client, young["id"], q, on="2026-01-01", kind="opening", heads=40)
    assert _move(client, young["id"], q, 409, on="2026-01-02", kind="opening", heads=1)
    assert _move(client, young["id"], q, 422, on="2026-03-01", kind="transfer_out", heads=15)       # lot d'arrivée
    body = _move(client, young["id"], q, on="2026-03-01", kind="transfer_out", heads=15, counterpart_lot_id=older["id"])
    assert body["item"]["summary"]["theoretical"] == 25
    assert body["item"]["movements"][-1]["counterpart"]["label"] == "Bovin — Génisses 1-2 ans"
    other = client.get(f"/api/v1/stock-lots/{older['id']}{q}").get_json()["item"]
    assert other["summary"]["movements"]["transfer_in"] == 15 and other["summary"]["theoretical"] == 15
    transfer = body["item"]["movements"][-1]["id"]
    after = client.delete(f"/api/v1/stock-lots/{young['id']}/movements/{transfer}{q}").get_json()["item"]
    assert after["summary"]["theoretical"] == 40
    assert client.get(f"/api/v1/stock-lots/{older['id']}{q}").get_json()["item"]["summary"]["theoretical"] == 0


def test_validation_and_frozen_year(farm):
    client, q = farm["client"], farm["q"]
    assert client.post("/api/v1/stock-lots", json={"species": "Porc", "account_code": "31111"}).status_code == 422
    assert client.post("/api/v1/stock-lots", json={"account_code": "3113"}).status_code == 422          # espèce
    lot = _lot(client, q, species="Ovin", account_code="3113")
    assert _move(client, lot["id"], q, 422, on="2026-02-01", kind="sale", heads=0)
    assert _move(client, lot["id"], q, 422, on="2026-02-01", kind="birth", heads=3, sale_id=999)
    _move(client, lot["id"], q, on="2026-02-01", kind="birth", heads=3)
    assert client.delete(f"/api/v1/stock-lots/{lot['id']}").status_code == 409                      # mouvements
    farm["previous"].status = "closed"
    db.session.commit()
    assert _move(client, lot["id"], q, 409, on="2025-12-01", kind="birth", heads=1)
    body = client.post(f"{farm['stock']}/lines", json={"lot_id": lot["id"], "heads": 3, "unit": "t"})
    assert body.status_code == 422                                                                    # tête ou kg
