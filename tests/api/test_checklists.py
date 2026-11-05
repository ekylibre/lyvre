"""Lot AG9b.e : listes de contrôle guidées (clôture, PAC, mai, automne), sans IA."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, BankAccount, BankTransaction, FiscalYear, Journal
from app.services import agri_profile, checklists
from test_agri_fixtures import _agri_instance


@pytest.fixture()
def farm(app, login_as):
    client = login_as(role="admin")
    _agri_instance()
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    db.session.add_all([fy, Journal(code="OD", label="OD")])
    db.session.commit()
    return {"client": client, "fy": fy}


def test_definitions_valid():
    items = checklists.definitions()
    assert [c["id"] for c in items] == ["closing", "pac", "may", "autumn"]
    assert checklists.validate([{"id": "x", "window": {"type": "?"}, "steps": [{"id": "a", "auto": "nope"}]}])


def test_windows_and_auto_steps(farm):
    client, fy = farm["client"], farm["fy"]
    body = client.get("/api/v1/checklists?on=2026-11-20").get_json()["item"]
    by_id = {c["id"]: c for c in body["items"]}
    assert by_id["autumn"]["status"] == "current" and by_id["closing"]["status"] == "upcoming"
    assert by_id["closing"]["period"] == "2026" and "pac" not in by_id and "may" not in by_id
    closing = {s["id"]: s for s in by_id["closing"]["steps"]}
    assert closing["inventory"]["link"] == f"/inventory/?fiscal_year={fy.id}" and closing["inventory"]["done"] is False
    assert closing["checks"]["link"] == f"/fiscal-years/{fy.id}/closing"
    assert closing["bank"]["auto"] is False                        # aucune transaction : case à cocher
    bank = BankAccount(label="CIC", account_id=Account.query.filter_by(code="512").one().id)
    db.session.add(bank)
    db.session.commit()
    db.session.add(BankTransaction(bank_account_id=bank.id, fitid="T1", transaction_date=date(2026, 6, 1), amount_cents=-100,
                                   label="x", reconciled=True))
    db.session.commit()
    closing = {s["id"]: s for s in client.get("/api/v1/checklists?on=2026-12-20").get_json()["item"]["items"][0]["steps"]}
    assert closing["bank"]["auto"] is True and closing["bank"]["done"] is True
    assert client.put("/api/v1/checklists/closing/2026/steps/aids", json={"done": True}).status_code == 200
    closing = {s["id"]: s for s in client.get("/api/v1/checklists?on=2026-12-20").get_json()["item"]["items"][0]["steps"]}
    assert closing["aids"]["done"] and closing["aids"]["marked_on"]
    assert client.put("/api/v1/checklists/closing/2026/steps/aids", json={"done": False}).status_code == 200
    assert client.put("/api/v1/checklists/closing/2026/steps/nope", json={"done": True}).status_code == 404


def test_pac_applies_to_profile(farm):
    client = farm["client"]
    items = client.get("/api/v1/checklists?on=2026-04-15").get_json()["item"]["items"]
    pac = next(c for c in items if c["id"] == "pac")
    assert pac["profile_incomplete"] is True and pac["period"] == "2026"
    agri_profile.save({"pac": False})
    db.session.commit()
    assert all(c["id"] != "pac" for c in client.get("/api/v1/checklists?on=2026-04-15").get_json()["item"]["items"])
    agri_profile.save({"pac": True})
    db.session.commit()
    pac = next(c for c in client.get("/api/v1/checklists?on=2026-04-15").get_json()["item"]["items"] if c["id"] == "pac")
    assert pac["profile_incomplete"] is False and {s["id"] for s in pac["steps"]} >= {"surfaces", "telepac"}
