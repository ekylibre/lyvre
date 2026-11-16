"""Lot AG1.a : paramètres réglementaires datés (fichiers data/regulatory/ + surcharges en méta-base)."""
import json
from datetime import date

import pytest

from app.services import reg_params


def test_files_are_valid_and_sourced():
    keys = set()
    for param in reg_params.file_params():
        assert param.reliability in reg_params.RELIABILITIES, param.key
        assert param.valid_to is None or param.valid_to >= param.valid_from, param.key
        assert param.source.startswith("https://") or param.value is None, param.key
        keys.add(param.key)
    assert {"ba.micro.threshold_cents", "ba.micro.allowance_bp", "vat.rfa.threshold_cents"} <= keys


def test_typed_suffixes_hold_integers():
    for param in reg_params.file_params():
        if param.key.endswith(("_cents", "_bp")):
            assert isinstance(param.value, int), param.key


def test_get_by_date_and_missing(app):
    assert reg_params.value("ba.micro.allowance_bp", date(2026, 6, 1)) == 8700
    with pytest.raises(reg_params.MissingParam):
        reg_params.value("ba.micro.allowance_bp", date(2000, 1, 1))
    assert reg_params.value("ba.micro.allowance_bp", date(2000, 1, 1), default=None) is None
    with pytest.raises(reg_params.MissingParam):
        reg_params.get("inconnu.cle", date(2026, 1, 1))


def test_override_wins_for_covered_dates_only(app):
    row = reg_params.add_override("ba.micro.threshold_cents", {
        "value": 13000000, "valid_from": "2027-01-01", "valid_to": "2027-12-31", "reliability": "V",
        "source": "https://www.legifrance.gouv.fr/", "source_label": "Essai"})
    assert reg_params.get("ba.micro.threshold_cents", date(2027, 5, 1)).value == 13000000
    assert reg_params.get("ba.micro.threshold_cents", date(2027, 5, 1)).origin == "override"
    assert reg_params.value("ba.micro.threshold_cents", date(2026, 5, 1)) == 12920000
    assert reg_params.value("ba.micro.threshold_cents", date(2028, 1, 1)) == 12920000
    assert reg_params.value("ba.micro.threshold_cents", date(2023, 6, 30)) == 9190000
    assert reg_params.value("ba.micro.threshold_cents", date(2025, 1, 31)) == 12000000
    assert reg_params.value("ba.normal.threshold_cents", date(2025, 1, 31)) == 39100000
    assert reg_params.value("ba.micro.threshold_cents", date(2022, 12, 31), default=None) is None
    assert [p.origin for p in reg_params.history("ba.micro.threshold_cents")] == ["file", "file", "file", "override"]
    reg_params.delete_override(row.id)
    assert reg_params.value("ba.micro.threshold_cents", date(2027, 5, 1)) == 12920000


@pytest.mark.parametrize("key,data,field", [
    ("cle.inconnue", {"value": 1, "valid_from": "2027-01-01", "source": "https://x.fr"}, "key"),
    ("ba.micro.allowance_bp", {"value": "87 %", "valid_from": "2027-01-01", "source": "https://x.fr"}, "value"),
    ("ba.micro.allowance_bp", {"value": 8700, "valid_from": "2027-01-01", "source": ""}, "source"),
    ("ba.micro.allowance_bp", {"value": 8700, "valid_from": "2027-01-01", "valid_to": "2026-01-01",
                               "source": "https://x.fr"}, "valid_to"),
    ("ba.micro.allowance_bp", {"value": 8700, "valid_from": "x", "source": "https://x.fr"}, "valid_from"),
])
def test_override_validation(app, key, data, field):
    with pytest.raises(reg_params.ParamError) as exc:
        reg_params.add_override(key, data)
    assert exc.value.field == field


def test_api_read_and_admin_only_write(app, login_as):
    user = login_as()
    response = user.get("/api/v1/regulatory-values?prefix=ba.micro&on=2026-06-01")
    assert response.status_code == 200
    items = {i["key"]: i for i in response.get_json()["items"]}
    assert items["ba.micro.allowance_bp"]["current"]["value"] == 8700
    assert items["ba.micro.threshold_cents"]["current"]["reliability"] == "I"
    body = {"value": 13000000, "valid_from": "2027-01-01", "source": "https://www.legifrance.gouv.fr/"}
    assert user.post("/api/v1/regulatory-values/ba.micro.threshold_cents", json=body).status_code == 403


def test_api_admin_override(app, login_as):
    admin = login_as(is_admin=True)
    body = {"value": 13000000, "valid_from": "2027-01-01", "source": "https://www.legifrance.gouv.fr/"}
    response = admin.post("/api/v1/regulatory-values/ba.micro.threshold_cents", json=body)
    assert response.status_code == 201, response.get_json()
    override_id = response.get_json()["item"]["id"]
    listing = admin.get("/api/v1/regulatory-values?prefix=ba.micro.threshold&on=2027-02-01").get_json()["items"]
    assert listing[0]["current"]["value"] == 13000000
    assert admin.delete(f"/api/v1/regulatory-values/overrides/{override_id}").status_code == 200
    bad = admin.post("/api/v1/regulatory-values/ba.micro.threshold_cents", json={**body, "value": "x"})
    assert bad.status_code == 422 and "value" in bad.get_json()["error"]["fields"]
