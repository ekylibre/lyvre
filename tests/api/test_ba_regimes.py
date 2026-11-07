"""Lot AG6.e : régimes BA (moyennes, GAEC, 72 E bis, simulation), revenus accessoires (art. 75), étalement 75-0 A."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, FiscalYear, Journal, TaxOption, TaxProfile
from app.models.journal_entry import SOURCE_OPENING
from app.services import closing
from app.services.ledger import post_entry
from test_agri_fixtures import _agri_instance


def _id(code):
    return Account.query.filter_by(code=code).one().id


@pytest.fixture()
def farm(app, login_as):
    client = login_as(role="admin")
    _agri_instance()
    years = {y: FiscalYear(label=str(y), start_date=date(y, 1, 1), end_date=date(y, 12, 31)) for y in (2024, 2025, 2026, 2027)}
    od = Journal(code="OD", label="OD")
    db.session.add_all([*years.values(), od])
    db.session.commit()

    def sale(year, euros, account="7011", vat_euros=0):
        lines = [{"account_id": _id("411"), "label": "x", "debit_cents": (euros + vat_euros) * 100, "credit_cents": 0},
                 {"account_id": _id(account), "label": "x", "debit_cents": 0, "credit_cents": euros * 100}]
        if vat_euros:
            lines.append({"account_id": _id("44571"), "label": "x", "debit_cents": 0, "credit_cents": vat_euros * 100})
        post_entry(years[year].id, od.id, date(year, 6, 30), "Ventes", lines)

    def form(code, created=None):
        from app.services import organization
        org = organization.get()
        org.legal_form_code, org.created_on = code, created
        db.session.commit()

    return {"client": client, "fy": years, "sale": sale, "form": form, "od": od,
            "url": lambda y: f"/api/v1/fiscal-years/{years[y].id}"}


def test_average_custom_work_and_regime_change(farm):
    client = farm["client"]
    farm["form"]("EI")
    db.session.add(TaxProfile(kind="ba_regime", value="micro", start_date=date(2020, 1, 1)))
    db.session.commit()
    for year in (2024, 2025, 2026):
        farm["sale"](year, 120000)
    farm["sale"](2026, 10000, account="7041")                               # façon × 3
    client.put(f"/api/v1/accounts/{_id('7041')}/ba-income-class", json={"ba_income_class": "custom_work"})
    assert client.put(f"/api/v1/accounts/{_id('60111')}/ba-income-class", json={"ba_income_class": "accessory"}).status_code == 422
    reg = client.get(f"{farm['url'](2026)}/ba-regime").get_json()["item"]["regime"]
    assert [y["threshold_cents"] for y in reg["years"]] == [12000000, 12000000, 15000000]
    assert reg["average_cents"] == 13000000 and reg["expected"] == "simplified"
    assert reg["change"]["direction"] == "up" and "01/01/2027" in reg["change"]["label"]
    assert any(c.key == "ba_regime_change" for c in closing._agri_checks(farm["fy"][2026]))
    client.put("/api/v1/ba-history/2024", json={"agricultural_receipts_cents": 9000000, "note": "ancienne compta"})
    reg = client.get(f"{farm['url'](2026)}/ba-regime").get_json()["item"]["regime"]
    assert reg["years"][0]["source"] == "entered" and reg["average_cents"] == 12000000 and reg["change"] is None


def test_gaec_thresholds_and_micro_ban(farm):
    client = farm["client"]
    farm["form"]("GAEC", date(2010, 1, 1))
    from app.services import associates
    for n in ("A", "B", "C"):
        associates.create({"new_name": n}).is_operator = True
    db.session.commit()
    farm["sale"](2026, 300000)
    reg = client.get(f"{farm['url'](2026)}/ba-regime").get_json()["item"]["regime"]
    assert reg["thresholds"]["micro_cents"] == 3 * 12920000 and "3 associés" in reg["thresholds"]["detail"]
    assert reg["micro_allowed"] is False and "69 D" in reg["micro_reason"] and reg["expected"] == "simplified"


def test_micro_to_real_receivables(farm):
    client = farm["client"]
    farm["form"]("EI")
    db.session.add_all([TaxProfile(kind="ba_regime", value="micro", start_date=date(2020, 1, 1), end_date=date(2025, 12, 31)),
                        TaxProfile(kind="ba_regime", value="simplified", start_date=date(2026, 1, 1))])
    db.session.commit()
    post_entry(farm["fy"][2026].id, farm["od"].id, date(2026, 1, 1), "À-nouveaux", [
        {"account_id": _id("411"), "label": "x", "debit_cents": 2000000, "credit_cents": 0},
        {"account_id": _id("101"), "label": "x", "debit_cents": 0, "credit_cents": 2000000}], source=SOURCE_OPENING)
    lines = client.get(f"{farm['url'](2026)}/tax-result").get_json()["item"]["lines"]
    assert {l["key"]: l["amount_cents"] for l in lines} == {"micro_to_real": 260000}
    lines = client.get(f"{farm['url'](2027)}/tax-result").get_json()["item"]["lines"]
    assert not any(l["key"] == "micro_to_real" for l in lines)


def test_accessory_income_and_is_alert(farm):
    client = farm["client"]
    farm["form"]("SCEA", date(2010, 1, 1))
    for year in (2023, 2024, 2025):
        client.put(f"/api/v1/ba-history/{year}", json={"agricultural_receipts_cents": 10000000, "accessory_receipts_cents": 6000000})
    acc = client.get(f"{farm['url'](2026)}/ba-regime").get_json()["item"]["accessory"]
    assert acc["span"] == [2023, 2024, 2025] and acc["accessory_avg_cents"] == 6000000
    assert acc["limit_ratio_cents"] == 5000000 and acc["exceeded"] and acc["consequence"] == "is"
    assert any(c.key == "accessory_is" and c.severity == "anomaly" for c in closing._agri_checks(farm["fy"][2026]))
    # TTC : TVA collectée de la même écriture au prorata des produits
    client.put(f"/api/v1/accounts/{_id('7083')}/ba-income-class", json={"ba_income_class": "accessory"})
    farm["sale"](2026, 1000, account="7083", vat_euros=200)
    acc = client.get(f"{farm['url'](2027)}/ba-regime").get_json()["item"]["accessory"]
    assert acc["years"][-1]["accessory_ttc_cents"] == 120000


def test_simulation_micro_vs_real(farm):
    client = farm["client"]
    farm["form"]("EI")
    for year in (2024, 2025, 2026):
        farm["sale"](year, 60000)
    sim = client.get(f"{farm['url'](2026)}/ba-regime").get_json()["item"]["simulation"]
    assert sim["average_cents"] == 6000000 and sim["micro_profit_cents"] == 780000
    assert sim["real_result_cents"] == 6000000 and sim["best"] == "micro"


def test_income_spread_sevenths(farm):
    client = farm["client"]
    farm["form"]("EI")
    for fy in [farm["fy"][2024], farm["fy"][2025]]:
        db.session.delete(fy)
    db.session.commit()
    for year in (2023, 2024, 2025):
        client.put(f"/api/v1/ba-history/{year}", json={"fiscal_result_cents": 2000000})
    farm["sale"](2026, 100000)
    view = client.get(f"{farm['url'](2026)}/income-spreads").get_json()["item"]
    prop = view["proposal"]
    assert prop["average_cents"] == 2000000 and prop["floor_cents"] == 2500000 and prop["exceptional_cents"] == 7500000
    assert any(c.key == "income_spread" for c in closing._agri_checks(farm["fy"][2026]))
    assert client.post(f"{farm['url'](2026)}/income-spreads", json={"kind": "profit", "amount_cents": 8000000}).status_code == 422
    assert client.post(f"{farm['url'](2026)}/income-spreads", json={"kind": "profit", "amount_cents": 7500000}).status_code == 201
    result = client.get(f"{farm['url'](2026)}/tax-result").get_json()["item"]
    assert {l["key"]: l["amount_cents"] for l in result["lines"]} == {"spread_1": 1071429 - 7500000}
    assert result["fiscal_result_cents"] == 10000000 - 7500000 + 1071429
    lines = client.get(f"{farm['url'](2027)}/tax-result").get_json()["item"]["lines"]
    assert {l["key"]: l["amount_cents"] for l in lines} == {"spread_1_2": 1071428}
    history = client.get(f"{farm['url'](2027)}/income-spreads").get_json()["item"]["averaging"]
    assert history["labels"] == ["2025", "2026", "2027"] and history["totals"][0] == 2000000


def test_spread_exclusions(farm):
    client = farm["client"]
    db.session.add(TaxOption(code="averaging_75_0_b", start_date=date(2026, 1, 1)))
    db.session.commit()
    resp = client.post(f"{farm['url'](2026)}/income-spreads", json={"kind": "profit", "amount_cents": 100})
    assert resp.status_code == 422 and "75-0 B" in resp.get_json()["error"]["message"]
    assert client.post(f"{farm['url'](2026)}/income-spreads", json={"kind": "slaughter", "amount_cents": 100}).status_code == 422  # motif
    assert client.post(f"{farm['url'](2026)}/income-spreads", json={"kind": "slaughter", "amount_cents": 700,
                                                                     "reason": "indemnité 2026 − valeur des animaux"}).status_code == 201
    db.session.add(TaxOption(code="stock_freeze_72_b_bis", start_date=date(2026, 1, 1)))
    db.session.commit()
    resp = client.post(f"{farm['url'](2027)}/income-spreads", json={"kind": "slaughter", "amount_cents": 700, "reason": "motif long"})
    assert resp.status_code == 422 and "72 B bis" in resp.get_json()["error"]["message"]


def test_stock_freeze_and_averaging_conflict_cg4b(farm):
    """Lot CG4.b (BOI-BA-BASE-20-20-20-40 § 100) : 72 B bis et moyenne triennale 75-0 B non cumulables."""
    from app.services import ba_regimes, tax_profile
    db.session.add(TaxOption(code="stock_freeze_72_b_bis", start_date=date(2025, 1, 1)))
    db.session.commit()
    assert not any(c[0] == "freeze_averaging_conflict" for c in ba_regimes.checks(farm["fy"][2026]))
    db.session.add(TaxOption(code="averaging_75_0_b", start_date=date(2026, 1, 1)))
    db.session.commit()
    (conflict,) = [c for c in ba_regimes.checks(farm["fy"][2026]) if c[0] == "freeze_averaging_conflict"]
    assert conflict[3] == "anomaly" and "§ 100" in conflict[1]
    assert not any(c[0] == "freeze_averaging_conflict" for c in ba_regimes.checks(farm["fy"][2025]))
    assert tax_profile.CONFLICT_72_B_BIS_75_0_B in tax_profile.warnings(date(2026, 6, 1))
    assert any(c.key == "freeze_averaging_conflict" for c in closing._agri_checks(farm["fy"][2026]))
