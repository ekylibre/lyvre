"""Lot AG6.g : plus-values (court / long terme, 151 septies) et crédits d'impôt."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, FiscalYear, Journal
from app.services import capital_gains
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
    from app.services import organization
    org = organization.get()
    org.legal_form_code, org.created_on = "EI", date(2010, 1, 1)
    db.session.commit()
    return {"client": client, "fy": fy, "od": od, "url": f"/api/v1/fiscal-years/{fy.id}"}


def _asset(client, **data):
    resp = client.post("/api/v1/assets", json=data)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["item"]


def _sell(client, asset, price):
    resp = client.post(f"/api/v1/assets/{asset['id']}/dispose", json={"date": "2026-06-30", "kind": "sold", "price_cents": price})
    assert resp.status_code == 200, resp.get_json()


def test_short_long_term_and_151_septies(farm):
    client, url = farm["client"], farm["url"]
    land = _asset(client, label="Parcelle", account_id=_id("2111"), acquired_on="2015-01-01", in_service_date="2015-01-01",
                  acquisition_cents=1000000, method="none")
    tractor = _asset(client, label="Tracteur", account_id=_id("2154"), acquired_on="2018-01-01", in_service_date="2018-01-01",
                     acquisition_cents=2000000, method="linear", duration_months=60,
                     prior_depreciation_cents=2000000, prior_as_of="2025-12-31")
    _sell(client, land, 2500000)
    _sell(client, tractor, 500000)
    view = client.get(f"{url}/capital-gains").get_json()["item"]
    rows = {d["label"]: d for d in view["disposals"]}
    assert rows["Parcelle"]["long_cents"] == 1500000 and rows["Parcelle"]["short_cents"] == 0
    assert rows["Tracteur"]["net_cents"] == 0 and rows["Tracteur"]["short_cents"] == 500000 and rows["Tracteur"]["long_cents"] == 0
    assert {l["key"]: l["amount_cents"] for l in view["lines"]} == {"pv_long_term": -1500000}
    for year in (2024, 2025):
        client.put(f"/api/v1/ba-history/{year}", json={"agricultural_receipts_cents": 20000000})
    body = client.put(f"{url}/capital-gains", json={"apply_151_septies": True}).get_json()["item"]
    assert body["septies"]["rate_bp"] == 10000 and body["long_exempt_cents"] == 1500000 and body["long_taxable_cents"] == 0
    lines = {l["key"]: l["amount_cents"] for l in client.get(f"{url}/tax-result").get_json()["item"]["lines"]}
    assert lines == {"pv_long_term": -1500000, "pv_151_septies": -500000}
    rate, _ = capital_gains.exemption_rate(40000000, farm["fy"], False)
    assert rate == 5000
    assert capital_gains.exemption_rate(40000000, farm["fy"], True)[0] == 10000          # cession à un JA
    client.put(f"{url}/capital-gains", json={"activity_since": "2023-01-01"})
    body = client.get(f"{url}/capital-gains").get_json()["item"]
    assert body["septies"]["rate_bp"] is None and "5 ans" in body["septies"]["reason"]


def test_long_term_loss_reintegrated(farm):
    client = farm["client"]
    land = _asset(client, label="Parcelle", account_id=_id("2111"), acquired_on="2015-01-01", in_service_date="2015-01-01",
                  acquisition_cents=1000000, method="none")
    _sell(client, land, 800000)
    lines = client.get(f"{farm['url']}/capital-gains").get_json()["item"]["lines"]
    assert lines[0]["key"] == "mv_long_term" and lines[0]["amount_cents"] == 200000


def test_tax_credits(farm):
    client, url = farm["client"], farm["url"]
    post_entry(farm["fy"].id, farm["od"].id, date(2026, 6, 30), "Ventes", [
        {"account_id": _id("411"), "label": "x", "debit_cents": 10000000, "credit_cents": 0},
        {"account_id": _id("7011"), "label": "x", "debit_cents": 0, "credit_cents": 10000000}])
    body = client.put(f"{url}/tax-credits/organic", json={"organic_receipts_cents": 5000000}).get_json()["item"]
    organic = body["items"][0]
    assert organic["share_bp"] == 5000 and organic["amount_cents"] == 450000
    client.put(f"{url}/tax-credits/organic", json={"organic_receipts_cents": 3000000})
    client.put(f"{url}/tax-credits/replacement", json={"expense_cents": 200000, "days": 20})
    client.put(f"{url}/tax-credits/hve", json={"certified_on": "2026-03-01"})
    items = {i["kind"]: i["amount_cents"] for i in client.get(f"{url}/tax-credits").get_json()["item"]["items"]}
    assert items == {"organic": 0, "replacement": 84000, "hve": 250000}       # HVE 2 500 € (exercice clos en 2026)
    assert client.put(f"{url}/tax-credits/other", json={}).status_code == 422
    assert client.delete(f"{url}/tax-credits/hve").status_code == 200


def test_151_septies_with_a_missing_year(farm):
    """Essai de l'interface (10/11/2026) : une année inconnue n'est pas une moyenne ; elle compte pour 0 et ne conclut
    que si les recettes connues dépassent déjà le seuil haut (0 %, même sans ancienneté connue)."""
    client, url = farm["client"], farm["url"]
    client.put("/api/v1/ba-history/2025", json={"agricultural_receipts_cents": 20000000})
    s = client.get(f"{url}/capital-gains").get_json()["item"]["septies"]
    assert s["average_cents"] is None and s["rate_bp"] is None and s["missing_years"] == [2024] and "2024" in s["detail"]
    client.put("/api/v1/ba-history/2025", json={"agricultural_receipts_cents": 140000000})
    client.put(f"{url}/capital-gains", json={"activity_since": "2023-01-01"})                 # moins de 5 ans
    s = client.get(f"{url}/capital-gains").get_json()["item"]["septies"]
    assert s["rate_bp"] == 0 and "pour 0" in s["detail"]
