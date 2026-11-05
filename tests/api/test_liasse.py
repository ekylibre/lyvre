"""Lot AG6.f : aide à la liasse BA 2139 / 2143 (cases, totaux, contrôles, exports)."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, FiscalYear, Journal, TaxProfile
from app.services.ledger import post_entry
from test_agri_fixtures import _agri_instance


def _id(code):
    return Account.query.filter_by(code=code).one().id


@pytest.fixture()
def farm(app, login_as):
    client = login_as(role="admin")
    _agri_instance()
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    od = Journal(code="OD", label="OD")
    db.session.add_all([fy, od])
    db.session.commit()
    post_entry(fy.id, od.id, date(2026, 6, 30), "Ventes", [
        {"account_id": _id("411"), "label": "x", "debit_cents": 10000000, "credit_cents": 0},
        {"account_id": _id("7011"), "label": "x", "debit_cents": 0, "credit_cents": 10000000}])
    post_entry(fy.id, od.id, date(2026, 6, 30), "Engrais", [
        {"account_id": _id("60111"), "label": "x", "debit_cents": 6000000, "credit_cents": 0},
        {"account_id": _id("401"), "label": "x", "debit_cents": 0, "credit_cents": 6000000}])
    return {"client": client, "fy": fy, "url": f"/api/v1/fiscal-years/{fy.id}"}


def _regime(value):
    db.session.add(TaxProfile(kind="ba_regime", value=value, start_date=date(2020, 1, 1)))
    db.session.commit()


def _cases(item):
    return {r["case"]: r["amount_cents"] for t in item["tables"] for r in t["rows"]}


def test_2139_cases_totals_and_checks(farm):
    client = farm["client"]
    _regime("simplified")
    client.post(f"{farm['url']}/tax-result/lines", json={"kind": "csg", "amount_cents": 50000})
    item = client.get(f"{farm['url']}/liasse").get_json()["item"]
    assert item["form"] == "2139" and item["millesime"] == 2026
    cases = _cases(item)
    assert cases["EA"] == 10000000 and cases["EQ"] == 6000000 and cases["ER"] == 0
    assert cases["EP"] == 10000000 and cases["FC"] == 6000000 and cases["FD"] == 4000000 and cases["FJ"] == 4000000
    assert cases["BC"] == 10000000 and cases["CK"] == 6000000 and cases["CE"] == 4000000
    assert cases["BR"] == 10000000 and cases["CP"] == 10000000
    assert cases["FK"] == 4000000 and cases["FP"] == 50000 and cases["FS"] == 4050000 and cases["ligne 1 col. 1"] == 4050000
    assert cases["FM"] is None                                                  # saisie
    assert all(c["ok"] for t in item["tables"] for c in t["checks"]) and item["warnings"] == []


def test_form_by_regime_and_exports(farm):
    client = farm["client"]
    item = client.get(f"{farm['url']}/liasse").get_json()["item"]
    assert item["form"] == "2139" and "non renseigné" in item["warnings"][0]
    _regime("micro")
    item = client.get(f"{farm['url']}/liasse").get_json()["item"]
    assert item["form"] is None and "Micro-BA" in item["reason"]
    TaxProfile.query.delete()
    _regime("simplified")
    resp = client.get(f"/fiscal-years/{farm['fy'].id}/liasse.xlsx")
    assert resp.status_code == 200 and resp.mimetype.endswith("sheet")
    resp = client.get(f"/fiscal-years/{farm['fy'].id}/liasse.pdf")
    assert resp.status_code == 200 and resp.data[:4] == b"%PDF"


def test_mapping_files_are_consistent():
    """Chaque total ne renvoie qu'à des cases du même tableau ; aucune case en double dans un tableau."""
    import json
    from app.services import liasse

    for path in liasse.DATA_DIR.glob("*.json"):
        spec = json.loads(path.read_text(encoding="utf-8"))
        for table in spec["tables"]:
            cases = [r["case"] for r in table["rows"]]
            assert len(cases) == len(set(cases)), (path.name, table["code"])
            for r in table["rows"]:
                for ref in r.get("sum", []) + r.get("minus", []):
                    assert ref in cases[:cases.index(r["case"])], (path.name, r["case"], ref)
                    assert not next(x for x in table["rows"] if x["case"] == ref).get("detail"), (path.name, ref)


def test_2143_normal_regime(farm):
    client = farm["client"]
    _regime("normal")
    client.post(f"{farm['url']}/tax-result/lines", json={"kind": "csg", "amount_cents": 50000})
    item = client.get(f"{farm['url']}/liasse").get_json()["item"]
    assert item["form"] == "2143"
    cases = _cases(item)
    assert cases["WA"] == 4000000 and cases["WO"] == 50000 and cases["XB"] == 4050000 and cases["ligne 1 col. 1"] == 4050000
    assert all(c["ok"] for t in item["tables"] for c in t["checks"]), [c for t in item["tables"] for c in t["checks"]]
