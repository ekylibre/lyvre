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
