"""Lot AG1.a : profil fiscal (forme juridique codée, régimes datés, options, contrôles AG0.5)."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Organization, TaxOption, TaxProfile
from app.services import tax_profile
from app.services.tax_profile import TaxProfileError


@pytest.fixture()
def org(app, instance):
    from app.services import organization
    return organization.get()


def _set(org, **values):
    for key, value in values.items():
        setattr(org, key, value)
    db.session.commit()


@pytest.mark.parametrize("category,code", [("1000", "EI"), ("6533", "GAEC"), ("6598", "EARL"), ("6597", "SCEA"),
                                           ("6534", "GFA"), ("5499", "SARL"), ("5710", "SAS"), ("5599", "SA"),
                                           ("9220", "ASSO"), ("6540", "SCI"), ("7110", None), ("", None)])
def test_legal_form_from_insee(category, code):
    assert tax_profile.legal_form_from_insee(category) == code


def test_new_period_closes_previous(org):
    _set(org, legal_form_code="EI")
    tax_profile.add_period({"kind": "income_tax", "value": "IR", "start_date": "2020-01-01"})
    tax_profile.add_period({"kind": "ba_regime", "value": "micro", "start_date": "2020-01-01"})
    tax_profile.add_period({"kind": "ba_regime", "value": "simplified", "start_date": "2026-01-01", "origin": "option"})
    micro, simplified = tax_profile.periods("ba_regime")
    assert micro.end_date == date(2025, 12, 31) and simplified.end_date is None
    assert tax_profile.current_value("ba_regime", date(2025, 6, 1)) == "micro"
    assert tax_profile.current_value("ba_regime", date(2026, 6, 1)) == "simplified"


def test_overlap_refused(org):
    tax_profile.add_period({"kind": "income_tax", "value": "IR", "start_date": "2020-01-01", "end_date": "2025-12-31"})
    with pytest.raises(TaxProfileError) as exc:
        tax_profile.add_period({"kind": "income_tax", "value": "IS", "start_date": "2025-07-01"})
    assert exc.value.field == "start_date"
    assert TaxProfile.query.count() == 1


def test_micro_refused_for_recent_company(org):
    _set(org, legal_form_code="SCEA", created_on=date(2010, 3, 1))
    with pytest.raises(TaxProfileError, match="69 D"):
        tax_profile.add_period({"kind": "ba_regime", "value": "micro", "start_date": "2026-01-01"})
    _set(org, legal_form_code="EARL_U")
    tax_profile.add_period({"kind": "ba_regime", "value": "micro", "start_date": "2026-01-01"})
    assert tax_profile.current_value("ba_regime", date(2026, 6, 1)) == "micro"


def test_micro_company_needs_creation_date(org):
    _set(org, legal_form_code="GAEC", created_on=None)
    with pytest.raises(TaxProfileError, match="date de création"):
        tax_profile.add_period({"kind": "ba_regime", "value": "micro", "start_date": "2026-01-01"})
    _set(org, created_on=date(1990, 1, 1))
    tax_profile.add_period({"kind": "ba_regime", "value": "micro", "start_date": "2026-01-01"})


def test_is_excludes_ba_regime(org):
    _set(org, legal_form_code="SCEA")
    tax_profile.add_period({"kind": "income_tax", "value": "IS", "start_date": "2026-01-01"})
    with pytest.raises(TaxProfileError, match="IS"):
        tax_profile.add_period({"kind": "ba_regime", "value": "normal", "start_date": "2026-01-01"})


def test_option_renounce_by_with_tacit_renewal(org):
    option = tax_profile.add_option({"code": "vat_quarterly", "start_date": "2024-01-01"})
    assert option.duration_years == 5 and option.tacit_renewal  # durée par défaut des paramètres
    payload = tax_profile.option_payload(option, on=date(2026, 11, 3))
    assert payload["current_period"] == {"first_year": 2024, "last_year": 2028}
    assert payload["renounce_by"]["date"] == "2029-02-05"
    assert tax_profile.option_payload(option, on=date(2030, 3, 1))["renounce_by"]["date"] == "2034-02-05"
    tax_profile.update_option(option, {"renounced_on": "2028-12-01"})
    assert tax_profile.option_payload(option)["renounce_by"] is None


def test_option_without_rule(org):
    option = tax_profile.add_option({"code": "averaging_75_0_b", "start_date": "2025-01-01"})
    assert tax_profile.option_payload(option, on=date(2026, 1, 1))["renounce_by"]["date"] is None


def test_warnings(org):
    _set(org, legal_form_code="EARL")
    assert any("IR ou IS" in w for w in tax_profile.warnings(date(2026, 6, 1)))
    tax_profile.add_period({"kind": "income_tax", "value": "IR", "start_date": "2026-01-01"})
    assert any("bénéfices agricoles" in w for w in tax_profile.warnings(date(2026, 6, 1)))


def test_api_flow(app, login_as):
    client = login_as(role="admin")
    response = client.put("/api/v1/tax-profile", json={"legal_form_code": "gaec", "created_on": "1995-04-01"})
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["item"]["legal_form_code"] == "GAEC"
    assert client.put("/api/v1/tax-profile", json={"legal_form_code": "XYZ"}).status_code == 422
    created = client.post("/api/v1/tax-profiles", json={"kind": "income_tax", "value": "IR", "start_date": "2026-01-01"})
    assert created.status_code == 201
    item = created.get_json()["item"]
    assert item["current"]["income_tax"] == "IR" and item["periods"][0]["value_label"] == "Impôt sur le revenu"
    bad = client.post("/api/v1/tax-profiles", json={"kind": "ba_regime", "value": "forfait", "start_date": "2026-01-01"})
    assert bad.status_code == 422 and "value" in bad.get_json()["error"]["fields"]
    period_id = item["periods"][0]["id"]
    assert client.patch(f"/api/v1/tax-profiles/{period_id}", json={"end_date": "2026-12-31"}).status_code == 200
    option = client.post("/api/v1/tax-options", json={"code": "vat_monthly", "start_date": "2026-01-01"}).get_json()
    assert option["item"]["options"][0]["renounce_by"]["date"] == "2031-01-31"
    assert client.delete(f"/api/v1/tax-profiles/{period_id}").status_code == 200
    meta = client.get("/api/v1/tax-profile").get_json()["meta"]
    assert {"value": "EARL_U", "label": "EARL unipersonnelle (associé unique exploitant)"} in meta["legal_forms"]


def test_api_write_requires_instance_admin(app, login_as):
    client = login_as(role="treasurer")
    assert client.get("/api/v1/tax-profile").status_code == 200
    assert client.post("/api/v1/tax-profiles", json={"kind": "income_tax", "value": "IR",
                                                     "start_date": "2026-01-01"}).status_code == 403
