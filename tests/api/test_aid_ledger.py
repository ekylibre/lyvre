"""Essai de l'interface (09/11/2026) : aides comptabilisées sans dossier (reprise FEC), campagnes des exercices."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, FiscalYear, Journal
from app.services import aids
from app.services.ledger import post_entry
from test_agri_fixtures import _agri_instance


def _id(code):
    return Account.query.filter_by(code=code).one().id


@pytest.fixture()
def farm(app, login_as):
    client = login_as(role="admin")
    _agri_instance()
    fy = FiscalYear(label="2024-2025", start_date=date(2024, 2, 1), end_date=date(2025, 1, 31))
    od = Journal(code="OD", label="OD")
    db.session.add_all([fy, od])
    db.session.commit()

    def aid_entry(day, account, cents):
        post_entry(fy.id, od.id, day, "Aide", [
            {"account_id": _id("512"), "label": "x", "debit_cents": cents, "credit_cents": 0},
            {"account_id": _id(account), "label": f"Aide {account}", "debit_cents": 0, "credit_cents": cents}])

    aid_entry(date(2024, 3, 5), "745", 921018)
    aid_entry(date(2024, 10, 16), "745", 1248308)
    aid_entry(date(2024, 7, 4), "742", 516933)
    aid_entry(date(2024, 9, 1), "741", 100000)                       # remboursement forfaitaire : exclu
    aid_entry(date(2025, 1, 31), "745", 1028281)
    return {"client": client, "fy": fy}


def test_campaigns_follow_fiscal_years_and_ledger(farm):
    body = farm["client"].get("/api/v1/aids?campaign=default").get_json()
    assert 2024 in body["meta"]["campaigns"] and body["campaign"] == 2025      # écriture d'aide la plus récente
    lines = farm["client"].get("/api/v1/aids?campaign=2024").get_json()["ledger"]
    assert [(l["account"]["code"], l["amount_cents"]) for l in lines] == [("745", 921018), ("742", 516933), ("745", 1248308)]


def test_create_from_ledger_and_link(farm):
    client = farm["client"]
    lines = client.get("/api/v1/aids?campaign=2024").get_json()["ledger"]
    ids_745 = [l["id"] for l in lines if l["account"]["code"] == "745"]
    mixed = client.post("/api/v1/aids/from-ledger", json={"scheme": "basic_income", "campaign": 2024,
                                                           "line_ids": [l["id"] for l in lines]})
    assert mixed.status_code == 422 and "plusieurs comptes" in mixed.get_json()["error"]["message"]
    resp = client.post("/api/v1/aids/from-ledger", json={"scheme": "basic_income", "campaign": 2024, "line_ids": ids_745})
    assert resp.status_code == 201, resp.get_json()
    aid = resp.get_json()["item"]
    assert aid["account"]["code"] == "745" and aid["paid_cents"] == 921018 + 1248308
    assert aid["notified_cents"] == 921018 + 1248308 and aid["status"] == "closed" and aid["remaining_cents"] == 0
    detail = client.get(f"/api/v1/aids/{aid['id']}").get_json()["item"]
    assert all(p["journal_line"] for p in detail["payments"])
    left = client.get("/api/v1/aids?campaign=2024").get_json()["ledger"]
    assert [l["account"]["code"] for l in left] == ["742"]
    again = client.post(f"/api/v1/aids/{aid['id']}/ledger-lines", json={"line_ids": ids_745[:1]})
    assert again.status_code == 409                                    # déjà rattachée
    later = client.get("/api/v1/aids?campaign=2025").get_json()["ledger"]
    ok = client.post(f"/api/v1/aids/{aid['id']}/ledger-lines", json={"line_ids": [later[0]["id"]]})
    assert ok.status_code == 200 and ok.get_json()["item"]["paid_cents"] == 921018 + 1248308 + 1028281
    # Supprimer le dossier libère les lignes, sans toucher aux écritures.
    assert client.delete(f"/api/v1/aids/{aid['id']}").status_code in (200, 204)
    assert len(client.get("/api/v1/aids?campaign=2024").get_json()["ledger"]) == 3
