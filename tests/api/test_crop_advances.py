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


def test_real_rubrics_by_method_cg2a(farm):
    """Lot CG2.a (design_fiabilisation_cegara.md § 2.1) : travaux par des tiers au réel en M1 et M2, main-d'œuvre
    salariée au réel en M2, rémunérations des associés et entretien des bâtiments exclus."""
    client, fy = farm["client"], farm["fy"]
    od = Journal.query.filter_by(code="OD").one()
    acc = {c: Account.query.filter_by(code=c).one().id for c in ("6051", "64111", "64116", "6152", "401")}
    for code, cents, label in (("6051", 200000, "Semis par ETA"), ("64111", 150000, "Salaire tractoriste"),
                               ("64116", 900000, "Rémunération associé"), ("6152", 50000, "Réparation hangar")):
        post_entry(fy.id, od.id, date(2025, 11, 10), label, [
            {"account_id": acc[code], "label": label, "debit_cents": cents, "credit_cents": 0},
            {"account_id": acc["401"], "label": label, "debit_cents": 0, "credit_cents": cents}])
    std = client.post("/api/v1/crop-standards", json={"production": "Blé tendre", "year": 2025, "rows": [
        {"component": "machinery", "month": 11, "amount_cents": 3000}, {"component": "labour", "month": 11, "amount_cents": 1000}]})
    adv = _create(farm, production="Blé tendre", surface_ha="10", planted_on="2025-11-05", method="standard_m1",
                  crop_standard_id=std.get_json()["item"]["id"])
    proposals = {p["label"]: p for p in adv["proposals"]}
    assert "Réparation hangar" not in proposals
    assert proposals["Rémunération associé"]["rubric"] == "labour"               # lot CG3.a : associés compris (Q5)
    assert proposals["Semis par ETA"]["rubric"] == "contracting" and proposals["Salaire tractoriste"]["rubric"] == "labour"
    url = f"/api/v1/crop-advances/{adv['id']}"
    for label in ("Semis par ETA", "Salaire tractoriste"):
        assert client.post(f"{url}/costs", json={"journal_line_id": proposals[label]["journal_line_id"]}).status_code == 201
    body = client.get(url).get_json()["item"]
    assert body["value_cents"] == 40000 + 200000                    # M1 : barème (30 + 10) × 10 + ETA ; salaire au barème
    resp = client.put(url, json={"method": "standard_m2"}).get_json()
    assert resp["item"]["value_cents"] == 30000 + 200000 + 150000   # M2 : mécanisation au barème + ETA + salaire au réel
    assert resp["meta"]["real_rubrics"]["standard_m2"] == ["seeds", "fertilizers", "treatments", "contracting", "labour"]


def test_standard_entered_as_cumulative_cg2b(farm):
    """Lot CG2.b (design_fiabilisation_cegara.md § 2.2) : un barème saisi en cumul vaut le même barème saisi par mois.
    Barème fictif (mécanisation, € / ha) : septembre 100, octobre 50, novembre 30, décembre rien, janvier 20."""
    client = farm["client"]
    monthly = client.post("/api/v1/crop-standards", json={"production": "Blé (mensuel)", "year": 2025, "rows": [
        {"component": "machinery", "month": m, "amount_cents": c} for m, c in ((9, 10000), (10, 5000), (11, 3000), (1, 2000))]})
    cumul = client.post("/api/v1/crop-standards", json={
        "production": "Blé (cumul)", "year": 2025, "entry_mode": "cumulative", "start_month": 9, "rows": [
            {"component": "machinery", "month": m, "amount_cents": c}
            for m, c in ((9, 10000), (10, 15000), (11, 18000), (12, 0), (1, 20000))]})
    assert monthly.status_code == 201 and cumul.status_code == 201, cumul.get_json()
    item = cumul.get_json()["item"]
    assert {(r["month"], r["amount_cents"]) for r in item["rows"]} == {(9, 10000), (10, 5000), (11, 3000), (1, 2000)}
    assert [(r["month"], r["amount_cents"]) for r in item["cumulative_rows"] if r["component"] == "machinery"] == [
        (9, 10000), (10, 15000), (11, 18000), (12, 18000), (1, 20000)]
    values = []
    for std in (monthly, cumul):
        adv = _create(farm, production="Blé", surface_ha="10", planted_on="2025-09-15", method="standard_m2",
                      crop_standard_id=std.get_json()["item"]["id"])
        values.append(adv["value_cents"])
    assert values == [200000, 200000]                                       # 200 € / ha × 10 ha, compté une fois
    sid = item["id"]
    down = client.put(f"/api/v1/crop-standards/{sid}", json={"rows": [
        {"component": "machinery", "month": 9, "amount_cents": 10000}, {"component": "machinery", "month": 10, "amount_cents": 8000}]})
    assert down.status_code == 422 and "baisse en octobre" in down.get_json()["error"]["message"]
    assert client.post("/api/v1/crop-standards", json={"production": "X", "year": 2025, "entry_mode": "cumulative"}).status_code == 422


def test_import_cumulative_and_warning_cg2b(farm):
    client = farm["client"]
    head = "Production;Année;Composante;Mois;Montant;Mode;Début du cycle\n"
    csv = head + "".join(f"Orge;2025;Mécanisation;{m};{c};cumul;septembre\n" for m, c in ((9, 100), (10, 150), (1, 200)))
    resp = client.post("/api/v1/crop-standards/import", data={"file": (io.BytesIO(csv.encode()), "c.csv")},
                       content_type="multipart/form-data")
    assert resp.status_code == 201, resp.get_json()
    (row,) = resp.get_json()["items"]
    assert row["entry_mode"] == "cumulative" and {(r["month"], r["amount_cents"]) for r in row["rows"]} == {
        (9, 10000), (10, 5000), (1, 5000)}
    growing = "Production;Année;Composante;Mois;Montant\n" + "".join(
        f"Maïs;2025;Mécanisation;{m};{10 * m}\n" for m in range(1, 8))
    resp = client.post("/api/v1/crop-standards/import", data={"file": (io.BytesIO(growing.encode()), "g.csv")},
                       content_type="multipart/form-data")
    assert resp.status_code == 201 and any("sans doute un cumul" in n["message"] for n in resp.get_json()["notices"])


def test_salaried_share_cg5a(farm):
    """Lot CG5.a (BOI-BA-BASE-20-20-20-30 § 100) : en F et M1, la main-d'œuvre du barème est réduite à la part
    salariée ; sans effet en M2 (main-d'œuvre au réel)."""
    client = farm["client"]
    std = client.post("/api/v1/crop-standards", json={"production": "Blé", "year": 2025, "rows": [
        {"component": "machinery", "month": 11, "amount_cents": 3000}, {"component": "labour", "month": 11, "amount_cents": 1000}]})
    adv = _create(farm, production="Blé", surface_ha="10", planted_on="2025-11-05", method="standard_f",
                  crop_standard_id=std.get_json()["item"]["id"])
    assert adv["value_cents"] == 40000                                            # (30 + 10) × 10
    url = f"/api/v1/crop-advances/{adv['id']}"
    body = client.put(url, json={"salaried_share_bp": 4000}).get_json()["item"]
    assert body["value_cents"] == 34000 and body["detail"]["components"]["labour"] == 4000   # 10 × 40 % × 10 ha
    assert body["salaried_share_bp"] == 4000 and body["detail"]["salaried_share_bp"] == 4000
    assert client.put(url, json={"salaried_share_bp": 0}).get_json()["item"]["value_cents"] == 30000
    assert client.put(url, json={"method": "standard_m2"}).get_json()["item"]["value_cents"] == 30000  # mécanisation seule
    assert client.put(url, json={"salaried_share_bp": 12000}).status_code == 422
