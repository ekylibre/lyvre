"""Lot AG4.c : avances aux cultures (design_inventaire_agricole.md § 5, AGD21 Q-S6).

Recettes du design (§ 13) :
- coût réel : semences 2 400 €, engrais 1 800 € (100 %), carburant 3 000 € à 40 % → 5 400 € en 31151 ;
- coût standard : barème 100 €/ha en novembre, 20 €/ha en décembre, 30 €/ha en janvier ; implanté en novembre,
  clôture au 31/01, 10 ha ; variante F → 1 500 €.
"""
import io
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, FiscalYear, Journal, StockLine
from app.services.ledger import post_entry
from test_agri_fixtures import _agri_instance


@pytest.fixture()
def farm(app, login_as):
    client = login_as(role="admin")
    _agri_instance()
    fy = FiscalYear(label="2025-2026", start_date=date(2025, 2, 1), end_date=date(2026, 1, 31))
    od = Journal(code="OD", label="OD")
    db.session.add_all([fy, od])
    db.session.commit()
    acc = {c: Account.query.filter_by(code=c).one().id for c in ("60112", "60111", "60614", "6131", "401")}
    for code, cents, label in (("60112", 240000, "Semences blé"), ("60111", 180000, "Ammonitrate"),
                               ("60614", 300000, "GNR"), ("6131", 500000, "Fermage")):
        post_entry(fy.id, od.id, date(2025, 10, 15), label, [
            {"account_id": acc[code], "label": label, "debit_cents": cents, "credit_cents": 0},
            {"account_id": acc["401"], "label": label, "debit_cents": 0, "credit_cents": cents}])
    return {"client": client, "fy": fy, "url": f"/api/v1/fiscal-years/{fy.id}/crop-advances"}


def _create(farm, **data):
    resp = farm["client"].post(farm["url"], json=data)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["item"]


def test_actual_cost_from_72a_proposals(farm):
    client = farm["client"]
    adv = _create(farm, production="Blé tendre", surface_ha="10", planted_on="2025-10-20", campaign=2026, method="actual")
    assert adv["account_code"] == "31151" and adv["value_cents"] == 0 and "Aucune charge" in adv["warnings"][0]
    proposals = {p["label"]: p for p in adv["proposals"]}
    assert set(proposals) == {"Semences blé", "Ammonitrate", "GNR"}                         # fermage exclu
    assert proposals["GNR"]["rubric"] == "machinery" and proposals["Semences blé"]["rubric"] == "seeds"
    url = f"/api/v1/crop-advances/{adv['id']}/costs"
    for label, share in (("Semences blé", 10000), ("Ammonitrate", 10000), ("GNR", 4000)):
        resp = client.post(url, json={"journal_line_id": proposals[label]["journal_line_id"], "share_bp": share})
        assert resp.status_code == 201, resp.get_json()
    body = resp.get_json()["item"]
    assert body["value_cents"] == 540000 and body["detail"]["costs"]["machinery"] == 120000
    line = StockLine.query.filter_by(crop_advance_id=adv["id"]).one()
    assert line.account.code == "31151" and line.variation_account.code == "713312" and line.method == "crop_advance"
    view = client.get(f"/api/v1/fiscal-years/{farm['fy'].id}/stock").get_json()["item"]
    (item,) = [i for i in view["items"] if i["crop_advance_id"] == adv["id"]]
    assert item["value_cents"] == 540000 and item["unit_value_cents"] == 54000 and item["unit"] == "ha"
    assert client.post(url, json={"journal_line_id": proposals["GNR"]["journal_line_id"], "share_bp": 1000}).status_code == 409
    other = _create(farm, production="Orge", surface_ha="5", planted_on="2025-10-01", method="actual")
    over = client.post(f"/api/v1/crop-advances/{other['id']}/costs",
                       json={"journal_line_id": proposals["GNR"]["journal_line_id"], "share_bp": 7000})
    assert over.status_code == 422 and "restante" in over.get_json()["error"]["message"]       # 60 % libres
    fermage = client.post(url, json={"rubric": "rent", "label": "Fermage", "amount_cents": 100})
    assert fermage.status_code == 422
    assert client.put(f"/api/v1/fiscal-years/{farm['fy'].id}/stock/lines/{line.id}",
                      json={"method": "retail"}).status_code == 409


def test_standard_cost_variants(farm):
    client = farm["client"]
    std = client.post("/api/v1/crop-standards", json={
        "production": "Blé tendre", "year": 2025, "source": "barème de l'exploitation", "labour_assumption": "100 % salariée",
        "rows": [{"component": "supplies", "month": 11, "amount_cents": 6000}, {"component": "machinery", "month": 11, "amount_cents": 3000},
                 {"component": "labour", "month": 11, "amount_cents": 1000}, {"component": "machinery", "month": 12, "amount_cents": 2000},
                 {"component": "machinery", "month": 1, "amount_cents": 3000}, {"component": "machinery", "month": 3, "amount_cents": 9999}]})
    assert std.status_code == 201, std.get_json()
    sid = std.get_json()["item"]["id"]
    adv = _create(farm, production="Blé tendre", surface_ha="10", planted_on="2025-11-05", method="standard_f", crop_standard_id=sid)
    assert adv["detail"]["months"] == 3 and adv["value_cents"] == 150000                       # (60+30+10+20+30) × 10
    assert adv["detail"]["labour_assumption"] == "100 % salariée"
    url = f"/api/v1/crop-advances/{adv['id']}"
    body = client.put(url, json={"method": "standard_m2"}).get_json()["item"]
    assert body["value_cents"] == 80000                                                       # mécanisation seule
    seeds = next(p for p in body["proposals"] if p["label"] == "Semences blé")
    body = client.post(f"{url}/costs", json={"journal_line_id": seeds["journal_line_id"]}).get_json()["item"]
    assert body["value_cents"] == 320000                                                      # + semences au réel
    body = client.put(url, json={"method": "standard_f"}).get_json()["item"]
    assert body["value_cents"] == 150000 and any("non prises" in w for w in body["warnings"])
    assert client.put(url, json={"planted_on": "2026-03-01"}).get_json()["item"]["value_cents"] == 0
    body = client.put(url, json={"cycle": "long", "planted_on": "2025-11-05"}).get_json()["item"]
    assert StockLine.query.filter_by(crop_advance_id=adv["id"]).one().account.code == "31141"


def test_import_standards_and_guards(farm):
    client = farm["client"]
    csv = "Production;Année;Composante;Mois;Montant\nColza;2025;Approvisionnements;août;120,50\nColza;2025;Mécanisation;sept;80\n"
    resp = client.post("/api/v1/crop-standards/import", data={"file": (io.BytesIO(csv.encode()), "bareme.csv")},
                       content_type="multipart/form-data")
    assert resp.status_code == 201, resp.get_json()
    (row,) = resp.get_json()["items"]
    assert row["production"] == "Colza" and {(r["component"], r["month"], r["amount_cents"]) for r in row["rows"]} == {
        ("supplies", 8, 12050), ("machinery", 9, 8000)}
    bad = "Production;Année;Composante;Mois;Montant\nColza;2025;Fermage;août;1\n"
    assert client.post("/api/v1/crop-standards/import", data={"file": (io.BytesIO(bad.encode()), "b.csv")},
                       content_type="multipart/form-data").status_code == 422
    adv = _create(farm, production="Colza", surface_ha="2", planted_on="2025-08-20", method="standard_f")
    assert "Barème" in adv["warnings"][0] and adv["value_cents"] is None
    assert client.post(f"/api/v1/fiscal-years/{farm['fy'].id}/stock/lines",
                       json={"account_code": "31151", "label": "x", "method": "crop_advance"}).status_code == 422
    assert client.delete(f"/api/v1/crop-advances/{adv['id']}").status_code == 200
    assert StockLine.query.count() == 0
