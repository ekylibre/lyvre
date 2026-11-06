"""Lot AG12.a : cadre des calculettes (registre, API, gabarit, copie) et pilotes 23 amortissement, 25 acomptes de
TVA, 08 micro-BA. Les calculettes du groupe A donnent le même résultat que le service existant (règle unique)."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, Asset, FiscalYear
from app.services import assets, ba_regimes, calculators, reg_params, vat_installments
from app.services.calculators import CalculatorError

from test_agri_fixtures import _agri_instance

API = "/api/v1/calculators"


@pytest.fixture()
def farm(app, login_as):
    client = login_as(role="admin")
    _agri_instance()
    db.session.add(FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), vat_liable=True))
    db.session.commit()
    return client


def test_registry_specs_and_examples(farm):
    modules = calculators.registry()
    assert {"amortissement", "acompte-tva", "micro-ba"} <= set(modules)
    for code, module in modules.items():
        spec = module.SPEC
        assert spec.method.strip() and spec.category in calculators.CATEGORIES and spec.charts
        assert set(spec.example) <= {i.key for i in spec.inputs}
        result = calculators.run(module, spec.example)                      # l'exemple se calcule
        assert result["headline"] and spec.title in result["text"] and "Méthode et limites" in result["text"]


def test_list_and_filter(farm):
    data = farm.get(API).get_json()
    assert data["meta"]["chart"] == "agri" and {i["code"] for i in data["items"]} >= {"micro-ba", "acompte-tva"}
    assert farm.get(f"{API}?chart=asso").get_json()["items"] == []
    assert len(farm.get(f"{API}?chart=all").get_json()["items"]) == len(calculators.registry())


def test_amortissement_equals_register(farm):
    account = Account.query.filter(Account.code.like("2154%"), Account.is_header.is_(False)).first() \
        or Account.query.filter(Account.code.like("215%"), Account.is_header.is_(False)).first()
    asset = Asset(label="Tracteur", account_id=account.id, acquired_on=date(2026, 3, 15), in_service_date=date(2026, 4, 1),
                  acquisition_cents=4500000, method="linear", duration_months=84, status="in_use")
    db.session.add(asset)
    db.session.commit()
    detail = farm.get(f"{API}/amortissement?choice={asset.id}").get_json()["item"]
    assert detail["prefill"]["base"] == {"value": "45000.00", "origin": "registre des immobilisations : Tracteur"}
    values = {k: v["value"] for k, v in detail["prefill"].items()}
    result = farm.post(f"{API}/amortissement", json={"values": values}).get_json()["result"]
    expected = [calculators.euros(r.amount_cents)
                for r in assets.schedule(asset)]
    assert [row[4] for row in result["table"]["rows"]] == expected
    regressive = farm.post(f"{API}/amortissement", json={"values": {**values, "method": "regressive", "duration_months": "24"}})
    assert any("3 ans" in w for w in regressive.get_json()["result"]["warnings"])
    assert farm.post(f"{API}/amortissement", json={"values": {**values, "duration_months": "0"}}).status_code == 422


def test_acompte_tva(farm):
    result = farm.post(f"{API}/acompte-tva", json={"values": {"year": "2027", "due": "8400", "assets_vat": "1200"}}).get_json()["result"]
    amount = vat_installments.proposed_amount(840000, date(2027, 12, 31))
    assert result["headline"][0]["value"] == calculators.euros(amount)
    assert len(result["table"]["rows"]) == 4
    assert result["table"]["rows"][0][2] == f"{vat_installments.due_date(date(2027, 3, 31)):%d/%m/%Y}"
    small = farm.post(f"{API}/acompte-tva", json={"values": {"year": "2027", "due": "500", "assets_vat": "200"}}).get_json()["result"]
    assert small["headline"][0]["value"] == "dispense"
    assert {p["key"] for p in result["params"]} == set(calculators.get("acompte-tva").SPEC.params)


def test_micro_ba_single_rule(farm):
    values = {"year": "2026", "receipts_n2": "61000", "receipts_n1": "68000", "receipts_n": "72000", "real_result": "21000"}
    result = farm.post(f"{API}/micro-ba", json={"values": values, "origins": {"receipts_n": "saisie"}}).get_json()["result"]
    expected = ba_regimes.micro_profit(6700000, date(2026, 12, 31))
    assert result["headline"][1] == {"label": "Bénéfice micro-BA", "value": calculators.euros(expected)}
    assert "Recettes N : 72000 € (saisie)" in result["text"]
    assert farm.post(f"{API}/micro-ba", json={"values": {**values, "receipts_n": ""}}).status_code == 422
    assert farm.post(f"{API}/micro-ba", json={"values": {**values, "receipts_n": "abc"}}).status_code == 422


def test_missing_param_blocks(farm, monkeypatch):
    real = reg_params.get
    monkeypatch.setattr(reg_params, "get", lambda key, on=None, default=None: None if key == "ba.micro.allowance_bp"
                        else real(key, on, default))
    resp = farm.post(f"{API}/micro-ba", json={"values": calculators.get("micro-ba").SPEC.example})
    assert resp.status_code == 409 and "ba.micro.allowance_bp" in resp.get_json()["error"]["message"]
    with pytest.raises(CalculatorError):
        calculators.require_params(calculators.get("micro-ba").SPEC, date(2026, 12, 31))


def test_unknown(farm):
    assert farm.get(f"{API}/inconnue").status_code == 404


def test_accountant_can_compute(app, login_as):
    accountant = login_as(role="accountant")
    _agri_instance()
    resp = accountant.post(f"{API}/acompte-tva", json={"values": {"year": "2027", "due": "8400"}})
    assert resp.status_code == 200                                          # un calcul n'écrit rien


# ------------------------------------------------------------------ lot AG12.b : reste du groupe A

def _run(farm, code, values):
    resp = farm.post(f"{API}/{code}", json={"values": values})
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["result"]


def test_dep_single_rule(farm):
    from app.services import dep
    result = _run(farm, "dep", {"closing": "2026-12-31", "profit": "62000", "operators": "2", "months": "12", "pending": "15000"})
    expected = dep.ceiling_for(6200000, date(2026, 12, 31), 2, 12, 1500000)
    assert result["headline"][0]["value"] == calculators.euros(expected["ceiling_cents"])
    fy = FiscalYear.query.one()
    assert dep.ceiling(6200000, fy)["ceiling_cents"] == dep.ceiling_for(6200000, fy.end_date, dep.operators(fy), 12,
                                                                         dep.outstanding(fy, exclude_fy=fy))["ceiling_cents"]


def test_fermage(farm):
    from decimal import Decimal
    from app.services import rent_revision
    rent_revision.save_value("FERMAGES", "2025", "122.55")
    rent_revision.save_value("FERMAGES", "2026", "123.06")
    db.session.commit()
    result = _run(farm, "fermage", {"rent": "4800", "index_code": "FERMAGES", "old_period": "2025", "new_period": "2026"})
    expected = rent_revision.apply_ratio(480000, Decimal("123.06") / Decimal("122.55"))
    assert result["headline"][0]["value"] == calculators.euros(expected)
    missing = farm.post(f"{API}/fermage", json={"values": {"rent": "4800", "index_code": "FERMAGES", "old_period": "2019",
                                                           "new_period": "2026"}})
    assert missing.status_code == 409 and "2019" in missing.get_json()["error"]["message"]


def test_msa_single_rule(farm):
    from app.services import msa_estimate
    result = _run(farm, "msa", {"year": "2026", "base": "32000", "status": "principal", "atexa": "B"})
    expected = msa_estimate.estimate(3200000, 2026, "principal", "B")["totals"]["total_cents"]
    assert result["headline"][0]["value"] == calculators.euros(expected) and len(result["table"]["rows"]) > 8


def test_marge_brute_and_cout_materiel(farm):
    result = _run(farm, "marge-brute", {"sales": "86000", "aids": "4200", "other": "-1500", "operational": "38500",
                                        "measure": "62", "unit": "ha"})
    assert result["headline"][0]["value"] == calculators.euros(5020000)
    assert result["headline"][1] == {"label": "Marge brute par ha", "value": calculators.euros(80968)}
    cost = _run(farm, "cout-materiel", {"depreciation": "9600", "financial": "1100", "insurance": "650", "maintenance": "2400",
                                        "hours": "480", "fuel_per_hour": "14", "fuel_price": "1.15", "hectares": "320"})
    # Fixes 11 350 € ÷ 480 h = 23,65 €/h ; variables : 2 400 ÷ 480 + 14 × 1,15 = 21,10 €/h.
    assert cost["headline"][0]["value"] == calculators.euros(2365 + 2110)
    assert cost["headline"][1]["value"] == calculators.euros(round((1135000 + 240000 + 1610 * 480) / 320))


def test_rfa_single_rule(farm):
    from app.services import rfa
    result = _run(farm, "rfa", {"year": "2026", "high_base": "38000", "low_base": "6500", "receipts_previous": "41000",
                                "receipts_year": "60000", "factor": "1"})
    on = date(2026, 12, 31)
    expected = rfa.flat_amount(3800000, 650000, reg_params.value("vat.rfa.rate_high_bp", on), reg_params.value("vat.rfa.rate_low_bp", on))
    assert result["headline"][0]["value"] == calculators.euros(expected)
    assert any("régime simplifié" in w for w in result["warnings"])         # moyenne 50 500 € > 46 000 €
