"""Lot AG6.a : résultat fiscal BA et tableau de passage (design_fiscalite_ba.md § 3, AGD23)."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, FiscalYear, Instance, Journal, ShareMovement, ShareMovementLine
from app.services import associates
from app.services.ledger import post_entry
from test_agri_fixtures import _agri_instance


def _id(code):
    return Account.query.filter_by(code=code).one().id


@pytest.fixture()
def farm(app, login_as):
    client = login_as(role="admin")
    _agri_instance()
    years = {y: FiscalYear(label=str(y), start_date=date(y, 1, 1), end_date=date(y, 12, 31)) for y in (2026, 2027, 2028)}
    od = Journal(code="OD", label="OD")
    db.session.add_all([*years.values(), od])
    db.session.commit()
    post_entry(years[2026].id, od.id, date(2026, 6, 30), "Ventes", [
        {"account_id": _id("411"), "label": "x", "debit_cents": 10000000, "credit_cents": 0},
        {"account_id": _id("7011"), "label": "x", "debit_cents": 0, "credit_cents": 10000000}])
    post_entry(years[2026].id, od.id, date(2026, 6, 30), "Engrais", [
        {"account_id": _id("60111"), "label": "x", "debit_cents": 6000000, "credit_cents": 0},
        {"account_id": _id("401"), "label": "x", "debit_cents": 0, "credit_cents": 6000000}])
    return {"client": client, "fy": years, "url": lambda y: f"/api/v1/fiscal-years/{years[y].id}/tax-result"}


def test_passage_with_stock_gap_and_manual_lines(farm):
    client, url = farm["client"], farm["url"](2026)
    body = client.get(url).get_json()["item"]
    assert body["accounting_result_cents"] == 4000000 and body["fiscal_result_cents"] == 4000000 and body["lines"] == []
    client.post(f"/api/v1/fiscal-years/{farm['fy'][2026].id}/stock/lines", json={
        "account_code": "35511", "label": "Blé", "quantity": "1", "method": "actual", "unit_value_cents": 100000,
        "fiscal_method": "manual", "fiscal_value_cents": 120000, "fiscal_reason": "valeur fiscale retenue"})
    assert client.post(f"{url}/lines", json={"kind": "csg", "amount_cents": 50000}).status_code == 201
    assert client.post(f"{url}/lines", json={"kind": "deduct", "amount_cents": 10000}).status_code == 422     # motif
    body = client.post(f"{url}/lines", json={"kind": "deduct", "label": "Plus-value exonérée", "amount_cents": 10000,
                                             "reason": "cession tracteur, 151 septies"}).get_json()["item"]
    assert {l["key"]: l["amount_cents"] for l in body["lines"] if l["source"] != "manual"} == {"stock_gap": 20000}
    assert body["additions_cents"] == 70000 and body["deductions_cents"] == 10000
    assert body["fiscal_result_cents"] == 4060000
    line_id = next(l["id"] for l in body["lines"] if l.get("kind") == "csg")
    assert client.delete(f"{url}/lines/{line_id}").get_json()["item"]["fiscal_result_cents"] == 4010000


def test_split_between_associates_usufruct_not_bare(farm):
    client = farm["client"]
    Instance.query.one().has_associates = True
    db.session.commit()
    paul, usufruct, bare = (associates.create({"new_name": n}) for n in ("Paul", "Parent", "Enfant"))
    db.session.add(ShareMovement(movement_date=date(2026, 1, 1), kind="opening", nominal_cents=1000, lines=[
        ShareMovementLine(associate_id=paul.id, nature="full", parts=600),
        ShareMovementLine(associate_id=usufruct.id, nature="usufruct", parts=400),
        ShareMovementLine(associate_id=bare.id, nature="bare", parts=400)]))
    db.session.commit()
    client.patch(f"/api/v1/associates/{paul.id}", json={"is_operator": True})
    body = client.get(farm["url"](2026)).get_json()["item"]
    split = {a["name"]: (a["share_bp"], a["fiscal_result_cents"]) for a in body["associates"]}
    assert split == {"Paul": (6000, 2400000), "Parent": (4000, 1600000)}          # rien sur la nue-propriété
    assert next(a for a in body["associates"] if a["name"] == "Paul")["is_operator"] is True
    client.patch(f"/api/v1/associates/{paul.id}", json={"profit_share": "70"})
    body = client.get(farm["url"](2026)).get_json()["item"]
    assert any("une partie des associés" in w for w in body["warnings"])
    client.patch(f"/api/v1/associates/{usufruct.id}", json={"profit_share": "30"})
    body = client.get(farm["url"](2026)).get_json()["item"]
    assert {a["name"]: a["share_bp"] for a in body["associates"]} == {"Paul": 7000, "Parent": 3000}
    assert body["associates"][0]["basis"] == "statuts"


def test_sanitary_slaughter_exemption_and_reintegration(farm):
    client, fy = farm["client"], farm["fy"]
    herd = client.post("/api/v1/assets", json={"label": "Vaches", "account_id": _id("241"), "acquired_on": "2026-01-01",
                                               "in_service_date": "2026-01-01", "acquisition_cents": 2000000,
                                               "method": "linear", "duration_months": 60, "units": 20}).get_json()["item"]
    exit_ = client.post(f"/api/v1/assets/{herd['id']}/living-exits", json={
        "date": "2026-09-01", "kind": "sanitary_slaughter", "units": 5, "indemnity_cents": 600000}).get_json()["exit"]
    gain = 600000 - exit_["book_value_cents"]
    body = client.get(farm["url"](2026)).get_json()["item"]
    (line,) = [l for l in body["lines"] if l["key"].startswith("slaughter_exempt")]
    assert line["amount_cents"] == -gain and any("75-0 D" in w for w in body["warnings"])
    client.put(f"/api/v1/living-reinvestments/{exit_['reinvestment']['id']}", json={"reinvested_cents": 300000})
    body = client.get(farm["url"](2028)).get_json()["item"]
    (line,) = [l for l in body["lines"] if l["key"].startswith("slaughter_reintegration")]
    assert line["amount_cents"] == round(gain / 2)


def test_frozen_after_closing_and_export(farm):
    client, fy = farm["client"], farm["fy"][2026]
    xlsx = client.get(f"/fiscal-years/{fy.id}/tax-result.xlsx")
    assert xlsx.status_code == 200 and xlsx.data[:2] == b"PK"
    fy.status = "closed"
    db.session.commit()
    body = client.get(farm["url"](2026)).get_json()["item"]
    assert body["frozen"] is True
    assert client.post(f"{farm['url'](2026)}/lines", json={"kind": "csg", "amount_cents": 1}).status_code == 409
