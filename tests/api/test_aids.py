"""Lot AG3.a : registre des aides PAC et subventions (claudedocs/design_aides_pac.md, AGD20)."""
import pytest

from app.extensions import db
from app.models import Account, Aid
from app.services import agri_profile, aids
from test_agri_fixtures import _agri_instance


@pytest.fixture()
def farm(app, login_as):
    client = login_as(role="admin")
    _agri_instance()
    return client


def _create(client, **data):
    resp = client.post("/api/v1/aids", json=data)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["item"]


def test_schemes_and_proposed_accounts(farm):
    items = {s["key"]: s for s in farm.get("/api/v1/aids/schemes").get_json()["items"]}
    assert len(items) == len(aids.schemes()) == 16
    assert items["basic_income"]["accounts"] == [
        {"code": "7451", "label": "Aide de base au revenu (DPB) (à créer)", "exists": False},
        {"code": "745", "label": "Subventions au revenu", "exists": True}]
    assert items["coupled_animal"]["accounts"][1]["code"] == "743"           # AGD20 : couplées en 743
    assert items["ichn"]["accounts"][1]["code"] == "744" and items["crop_insurance"]["accounts"][1]["code"] == "742"
    assert items["dja"]["nature"] == "mixed" and items["dja"]["operating_account"] == "744"


def test_create_with_sub_account_and_trigger_date(farm):
    aid = _create(farm, scheme="basic_income", campaign=2026, requested_cents=1800000)
    account = Account.query.filter_by(code="7451").one()
    parent = Account.query.filter_by(code="745").one()
    assert account.parent_id == parent.id and account.account_type == parent.account_type
    assert aid["account"]["code"] == "7451" and aid["payer"] == "ASP" and aid["status"] == "requested"
    assert aid["trigger_on"] == "2026-05-18" and aid["trigger_provisional"] is False     # paramètre 2026
    assert aid["acquired_cents"] == 1800000 and aid["remaining_cents"] == 1800000
    later = _create(farm, scheme="basic_income", campaign=2027, account_code="745")
    assert later["account"]["code"] == "745"
    assert later["trigger_on"] == "2027-05-15" and later["trigger_provisional"] is True  # date habituelle
    assert Account.query.filter_by(code="7451").count() == 1


def test_payments_and_remaining(farm):
    aid = _create(farm, scheme="basic_income", campaign=2026, requested_cents=1800000)
    url = f"/api/v1/aids/{aid['id']}/payments"
    resp = farm.post(url, json={"paid_on": "2026-10-16", "amount_cents": 1200000, "kind": "advance"})
    assert resp.status_code == 201 and resp.get_json()["item"]["remaining_cents"] == 600000
    assert farm.post(url, json={"paid_on": "2026-12-04", "amount_cents": 5000, "kind": "clawback"}).status_code == 422
    assert farm.post(url, json={"paid_on": "2026-12-04", "amount_cents": 0}).status_code == 422
    body = farm.put(f"/api/v1/aids/{aid['id']}", json={"notified_cents": 1150000}).get_json()["item"]
    assert body["status"] == "granted" and body["remaining_cents"] == -50000
    assert any("au-delà du montant acquis" in w for w in body["warnings"])
    payment_id = body["payments"][0]["id"]
    after = farm.delete(f"{url}/{payment_id}").get_json()["item"]
    assert after["paid_cents"] == 0 and after["payments"] == []
    listing = farm.get("/api/v1/aids?campaign=2026").get_json()
    assert listing["totals"]["acquired_cents"] == 1150000 and 2026 in listing["meta"]["campaigns"]


def test_validation(farm):
    assert farm.post("/api/v1/aids", json={"scheme": "inconnu", "campaign": 2026}).status_code == 422
    resp = farm.post("/api/v1/aids", json={"scheme": "basic_income", "campaign": 2026, "account_code": "706"})
    assert resp.status_code == 422 and "account_code" in resp.get_json()["error"]["fields"]
    assert farm.post("/api/v1/aids", json={"scheme": "basic_income", "campaign": 2026, "account_code": "7499"}).status_code == 422  # absent
    assert farm.post("/api/v1/aids", json={"scheme": "basic_income", "campaign": "2026"}).status_code == 422
    assert farm.post("/api/v1/aids", json={"scheme": "basic_income", "campaign": 2026, "bidule": 1}).status_code == 422
    aid = _create(farm, scheme="calamity", campaign=2026, notified_cents=500000)
    assert aid["trigger"] == "decision" and any("décision" in w for w in aid["warnings"])
    assert farm.put(f"/api/v1/aids/{aid['id']}", json={"scheme": "maec"}).status_code == 422
    assert farm.delete(f"/api/v1/aids/{aid['id']}").status_code == 200 and Aid.query.count() == 0


def test_mixed_dja(farm):
    aid = _create(farm, scheme="dja", campaign=2026, notified_cents=3000000, decision_on="2026-03-01")
    assert aid["account"]["code"] == "131" and aid["operating_account"]["code"] == "744"
    assert any("Ventilation" in w for w in aid["warnings"])
    url = f"/api/v1/aids/{aid['id']}"
    assert farm.put(url, json={"investment_share_cents": 4000000}).status_code == 422
    body = farm.put(url, json={"investment_share_cents": 2000000}).get_json()["item"]
    assert body["investment_share_cents"] == 2000000 and not any("Ventilation" in w for w in body["warnings"])
    assert body["investment"]["amount_cents"] == 2000000 and any("Immobilisations financées" in w for w in body["warnings"])
    other = _create(farm, scheme="other", campaign=2026, nature="investment", account_code="131")
    assert other["nature"] == "investment"
    assert farm.post("/api/v1/aids", json={"scheme": "maec", "campaign": 2026,
                                           "operating_account_code": "748"}).status_code == 422


def test_new_pac_campaign_from_profile(farm):
    agri_profile.save({"pac": True, "young_farmer": True, "productions": ["cattle"]})
    db.session.commit()
    items = {p["scheme"]: p for p in farm.get("/api/v1/aids/pac-campaign?campaign=2026").get_json()["items"]}
    checked = sorted(k for k, p in items.items() if p["checked"])
    assert checked == ["basic_income", "coupled_animal", "eco_scheme", "redistributive", "young_farmer_income"]
    assert items["ichn"]["checked"] is False and "dja" not in items and "investment" not in items
    resp = farm.post("/api/v1/aids/pac-campaign", json={"campaign": 2026, "schemes": checked})
    assert resp.status_code == 201 and len(resp.get_json()["items"]) == 5
    again = farm.post("/api/v1/aids/pac-campaign", json={"campaign": 2026, "schemes": ["basic_income"]})
    assert again.get_json()["items"] == [] and "existent déjà" in again.get_json()["notices"][0]["message"]
    assert farm.get("/api/v1/aids/pac-campaign?campaign=2026").get_json()["items"][0]["exists"] is True
    assert farm.post("/api/v1/aids/pac-campaign", json={"campaign": 2026, "schemes": ["dja"]}).status_code == 422
    animal = Aid.query.filter_by(scheme="coupled_animal").one()
    assert aids.trigger_date(animal)[0].isoformat().startswith("2026-05")      # date limite des aides bovines


def test_access(app, login_as):
    client = login_as(role="admin")
    assert client.get("/api/v1/aids").status_code == 404                     # pas une exploitation
    _agri_instance(bookkeeping="simple")
    assert client.get("/api/v1/aids").status_code == 200                     # micro-BA : suivi
    _create(client, scheme="basic_income", campaign=2026, requested_cents=100)


def test_accountant_reads_only(app, login_as):
    client = login_as(role="accountant")
    _agri_instance()
    assert client.get("/api/v1/aids").status_code == 200
    assert client.post("/api/v1/aids", json={"scheme": "basic_income", "campaign": 2026}).status_code == 403
