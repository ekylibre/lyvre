"""Lot AG6.c : DEP (art. 73) — plafond, déduction, épargne, utilisations et aléas, réintégrations, DPI historiques."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, BankAccount, FiscalYear, Journal
from app.services import closing, dep
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
        {"account_id": _id("411"), "label": "x", "debit_cents": 4000000, "credit_cents": 0},
        {"account_id": _id("7011"), "label": "x", "debit_cents": 0, "credit_cents": 4000000}])
    return {"client": client, "fy": years, "od": od, "url": lambda y: f"/api/v1/fiscal-years/{years[y].id}"}


def _save(farm, cents, on=date(2026, 12, 15)):
    fy = farm["fy"][on.year]
    post_entry(fy.id, farm["od"].id, on, "Épargne DEP", [
        {"account_id": _id("5121"), "label": "x", "debit_cents": cents, "credit_cents": 0},
        {"account_id": _id("512"), "label": "x", "debit_cents": 0, "credit_cents": cents}])


def test_ceiling_scale(farm):
    fy = farm["fy"][2026]
    assert dep.ceiling(4000000, fy)["ceiling_cents"] == 3530090                       # 33 287 + 30 % × 6 713
    assert dep.ceiling(7000000, fy)["ceiling_cents"] == 4346510                       # + 20 % × 8 358
    assert dep.ceiling(20000000, fy)["ceiling_cents"] == 5104000                      # plafond
    assert dep.ceiling(1000000, fy)["ceiling_cents"] == 1000000 and dep.ceiling(-1, fy)["ceiling_cents"] == 0


def test_deduction_savings_and_shortfall(farm):
    client, url = farm["client"], farm["url"](2026)
    assert client.put(f"{url}/dep", json={"amount_cents": 4000000}).status_code == 422          # > plafond
    body = client.put(f"{url}/dep", json={"amount_cents": 3000000}).get_json()["item"]
    assert body["deduction_cents"] == 3000000 and body["ceiling"]["ceiling_cents"] == 3530090
    result = client.get(f"{url}/tax-result").get_json()["item"]
    assert result["fiscal_result_cents"] == 1000000
    assert {c.key for c in closing._agri_checks(farm["fy"][2026])} >= {"dep_savings_due"}        # délai de 6 mois
    bank = BankAccount(label="Épargne DEP", account_id=_id("5121"))
    db.session.add(bank)
    db.session.commit()
    assert client.put(f"/api/v1/bank-accounts/{bank.id}/dep-savings", json={"dep_savings": True}).status_code == 200
    _save(farm, 1000000)
    s = client.get(f"{url}/dep").get_json()["item"]["savings"]
    assert s["savings_cents"] == 1000000 and s["below"] is True and s["shortfall_reintegration_cents"] == 0
    late = dep.savings(farm["fy"][2026], today=date(2027, 8, 1))                           # délai passé
    assert late["shortfall_reintegration_cents"] == 1000000
    lines = {l["key"]: l["amount_cents"] for l in dep.tax_lines(farm["fy"][2026], today=date(2027, 8, 1))}
    assert lines["dep"] == -3000000 and lines["dep_shortfall"] == 1000000
    client.post(f"{url}/dep/substitutes", json={"label": "Stock de fourrage consommé", "amount_cents": 600000})
    s = client.get(f"{url}/dep").get_json()["item"]["savings"]
    assert s["below"] is False and s["ratio_bp"] == 5333
    assert not {"dep_savings", "dep_savings_due"} & {c.key for c in closing._agri_checks(farm["fy"][2026])}


def test_use_with_hazard_and_history_deadline(farm):
    client = farm["client"]
    client.put(f"{farm['url'](2026)}/dep", json={"amount_cents": 3000000})
    (entry,) = client.get(f"{farm['url'](2027)}/dep").get_json()["item"]["register"]
    url = f"{farm['url'](2027)}/dep/movements"
    assert client.post(url, json={"entry_id": entry["id"], "kind": "use", "on": "2027-05-01", "amount_cents": 4000000}).status_code == 422
    resp = client.post(url, json={"entry_id": entry["id"], "kind": "use", "on": "2027-05-01", "amount_cents": 1000000,
                                  "hazard": "climate", "reason": "grêle"})
    assert resp.status_code == 201, resp.get_json()
    (entry,) = resp.get_json()["item"]["register"]
    assert entry["outstanding_cents"] == 2000000 and entry["movements"][0]["exempt_cents"] == 300000
    lines = {l["key"]: l for l in client.get(f"{farm['url'](2027)}/tax-result").get_json()["item"]["lines"]}
    move = next(l for k, l in lines.items() if k.startswith("dep_move_"))
    assert move["amount_cents"] == 700000 and "exonérés" in move["label"]
    assert client.post("/api/v1/dep/history", json={"kind": "dpi", "origin_year": 2018, "amount_cents": 500000}).status_code == 201
    lines = {l["key"]: l["amount_cents"] for l in client.get(f"{farm['url'](2028)}/tax-result").get_json()["item"]["lines"]}
    assert any(k.startswith("dep_deadline_") and v == 500000 for k, v in lines.items())       # DPI 2018 au 10e exercice
    assert any(c.key == "dep_deadline" for c in closing._agri_checks(farm["fy"][2028]))


def test_economic_hazard_value_added(farm):
    data = dep.economic_hazard(farm["fy"][2026])
    assert data["value_added_cents"] == 4000000 and data["average3_cents"] is None and data["hazard"] is False
