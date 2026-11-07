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
    # Lot CG2.c (design_fiabilisation_cegara.md § 2.3) : DPI au 5e exercice, DPA au 10e (paramètre « I »).
    assert client.post("/api/v1/dep/history", json={"kind": "dpi", "origin_year": 2018, "amount_cents": 500000}).status_code == 201
    lines = {l["key"]: l["amount_cents"] for l in client.get(f"{farm['url'](2028)}/tax-result").get_json()["item"]["lines"]}
    assert not any(k.startswith("dep_deadline_") for k in lines)                  # DPI 2018 : échéance 2023, hors Lyvre
    past = next(c for c in closing._agri_checks(farm["fy"][2026]) if c.key == "dep_deadline_past")
    assert past.severity == "anomaly" and "DPI (ancienne) 2018 (échéance 2023)" in past.label
    assert client.post("/api/v1/dep/history", json={"kind": "dpi", "origin_year": 2022, "amount_cents": 1}).status_code == 422
    fy2023 = FiscalYear(label="2023", start_date=date(2023, 1, 1), end_date=date(2023, 12, 31), status="closed")
    db.session.add(fy2023)
    db.session.commit()                                                           # 2023 tenu dans Lyvre : échéance visible
    lines = {l["key"]: l for l in client.get(f"/api/v1/fiscal-years/{fy2023.id}/tax-result").get_json()["item"]["lines"]}
    dpi = next(l for k, l in lines.items() if k.startswith("dep_deadline_"))
    assert dpi["amount_cents"] == 500000 and "au 5e exercice" in dpi["label"]
    assert not any(c.key == "dep_deadline_past" for c in closing._agri_checks(farm["fy"][2026]))
    assert client.post("/api/v1/dep/history", json={"kind": "dpa", "origin_year": 2018, "amount_cents": 300000}).status_code == 201
    lines = {l["key"]: l for l in client.get(f"{farm['url'](2028)}/tax-result").get_json()["item"]["lines"]}
    dpa = next(l for k, l in lines.items() if k.startswith("dep_deadline_"))
    assert dpa["amount_cents"] == 300000 and "au 10e exercice" in dpa["label"]
    assert any(c.key == "dep_deadline" for c in closing._agri_checks(farm["fy"][2028]))


def test_economic_hazard_value_added(farm):
    data = dep.economic_hazard(farm["fy"][2026])
    assert data["value_added_cents"] == 4000000 and data["average3_cents"] is None and data["hazard"] is False


@pytest.mark.parametrize("close, base, n, months, pending, expected", [
    (date(2019, 12, 31), 10000000, 1, 12, 0, 4140000),        # au-delà du 4e seuil : plafond 41 400 €
    (date(2023, 12, 31), 10000000, 1, 12, 0, 4327470),        # 28 612 + 7 311,90 + 5 298,60 + 2 052,20
    (date(2024, 12, 31), 10000000, 1, 12, 0, 4792200),        # 32 608 + 8 333,10 + 6 038,80 + 942,10
    (date(2025, 12, 31), 10000000, 1, 12, 0, 4836610),        # 32 990 + 8 430,60 + 6 109,40 + 836,10
    (date(2024, 9, 30), 4000000, 1, 9, 14000000, 1000000),    # 34 825,60 × 9/12 = 26 119,20, plafond global : 10 000
    (date(2024, 12, 31), 15000000, 3, 12, 0, 15000000),       # GAEC de 3 : 3 × 50 000, limité au bénéfice
])
def test_dep_historical_scales_cg2d(app, close, base, n, months, pending, expected):
    """Lot CG2.d (design_fiabilisation_cegara.md § 2.4) : barèmes 2019 à 2025 du BOI-BA-BASE-30-45-20 § 10, valeurs
    recalculées à la main (somme des tranches)."""
    with app.app_context():
        assert dep.ceiling_for(base, close, n, months, pending)["ceiling_cents"] == expected


def test_dep_before_2019_has_no_scale(app):
    with app.app_context():
        assert "introuvable" in dep.ceiling_for(10000000, date(2018, 12, 31), 1, 12, 0)["error"]
