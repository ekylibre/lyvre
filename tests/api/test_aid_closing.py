"""Lot AG3.c : aides à recevoir à la clôture et dates des dossiers dans l'échéancier (design_aides_pac.md § 4, § 6.3).

Recette du design (§ 12) : exploitation clôturant au 31/01, campagne 2026, demande 18 000 €, avance de 12 000 € le
16/10 → produit à recevoir de 6 000 € au 31/01/2027 (D 441 / C 7451).
"""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, Aid, FiscalYear, JournalEntry
from app.services import agenda, aid_closing, closing
from test_agri_fixtures import _agri_instance

END = date(2027, 1, 31)


@pytest.fixture()
def farm(app, login_as):
    client = login_as(role="admin")
    _agri_instance()
    fy = FiscalYear(label="2026-2027", start_date=date(2026, 2, 1), end_date=END)
    db.session.add(fy)
    db.session.commit()
    return {"client": client, "fy": fy, "url": f"/api/v1/fiscal-years/{fy.id}/closing/aids"}


def _aid(client, payments=(), **data):
    resp = client.post("/api/v1/aids", json=data)
    assert resp.status_code == 201, resp.get_json()
    aid = resp.get_json()["item"]
    for day, cents, kind in payments:
        assert client.post(f"/api/v1/aids/{aid['id']}/payments",
                           json={"paid_on": day, "amount_cents": cents, "kind": kind}).status_code == 201
    return aid


def _checks(fy):
    return {c.key: c for c in closing._agri_checks(fy)}


def test_accrued_income_at_closing(farm):
    client, fy = farm["client"], farm["fy"]
    _aid(client, scheme="basic_income", campaign=2026, requested_cents=1800000,
         payments=[("2026-10-16", 1200000, "advance")])
    (item,) = client.get(farm["url"]).get_json()["items"]
    assert item["kind"] == "accrued" and item["amount_cents"] == 600000 and item["account_code"] == "7451"
    assert item["trigger_on"] == "2026-05-18" and item["posted"] is False
    assert _checks(fy)["aid_accrual"].severity == "anomaly"
    resp = client.post(farm["url"], json={"items": [{"key": item["key"]}]})
    assert resp.status_code == 200, resp.get_json()
    (item,) = resp.get_json()["items"]
    assert item["posted"] and item["posted_cents"] == 600000
    entry = db.session.get(JournalEntry, item["entry"]["id"])
    lines = {(l.account.code, l.debit_cents, l.credit_cents) for l in entry.lines}
    assert lines == {("441", 600000, 0), ("7451", 0, 600000)} and entry.entry_date == END
    checks = _checks(fy)
    assert "aid_accrual" not in checks and "aid_441" not in checks
    assert client.post(farm["url"], json={"items": [{"key": item["key"]}]}).get_json()["notices"][0]["message"].startswith("0")
    closing.delete_inventory(fy, entry.id)                                   # supprimée : la proposition revient
    assert client.get(farm["url"]).get_json()["items"][0]["posted"] is False


def test_amount_override_needs_reason_and_dismissal(farm):
    client, fy = farm["client"], farm["fy"]
    aid = _aid(client, scheme="eco_scheme", campaign=2026, requested_cents=300000)
    (item,) = client.get(farm["url"]).get_json()["items"]
    assert client.post(farm["url"], json={"items": [{"key": item["key"], "amount_cents": 250000}]}).status_code == 422
    dismiss = f"{farm['url']}/dismissed"
    assert client.post(dismiss, json={"aid_id": aid["id"], "reason": "non"}).status_code == 422
    resp = client.post(dismiss, json={"aid_id": aid["id"], "reason": "Écorégime non obtenu (contrôle)"})
    assert resp.status_code == 200 and resp.get_json()["items"][0]["dismissed"] is True
    assert "aid_accrual" not in _checks(fy)
    assert client.delete(f"{dismiss}/{aid['id']}").status_code == 200
    resp = client.post(farm["url"], json={"items": [{"key": item["key"], "amount_cents": 250000,
                                                     "reason": "Montant notifié par courrier"}]})
    assert resp.get_json()["items"][0]["posted_cents"] == 250000


def test_deferred_income_and_mixed_dja(farm):
    client = farm["client"]
    early = FiscalYear(label="2025-2026", start_date=date(2025, 2, 1), end_date=date(2026, 1, 31))
    db.session.add(early)
    db.session.commit()
    _aid(client, scheme="basic_income", campaign=2026, requested_cents=500000, account_code="745",
         payments=[("2026-01-20", 100000, "other")])                         # versé avant la date limite 2026
    (item,) = aid_closing.proposals(early)["items"]
    assert item["kind"] == "deferred" and item["amount_cents"] == 100000 and item["counterpart"] == "487"
    entry = aid_closing.post(early, [{"key": item["key"]}])[0]
    assert {(l.account.code, l.debit_cents) for l in entry.lines} == {("745", 100000), ("487", 0)}
    dja = _aid(client, scheme="dja", campaign=2026, notified_cents=3000000, decision_on="2026-03-01",
               payments=[("2026-06-01", 2400000, "installment")])
    issues = aid_closing.proposals(farm["fy"])["issues"]
    assert any("Ventilation" in i["message"] for i in issues)
    client.put(f"/api/v1/aids/{dja['id']}", json={"investment_share_cents": 2000000})
    by_aid = {p["aid_id"]: p for p in aid_closing.proposals(farm["fy"])["items"]}
    assert by_aid[dja["id"]]["account_code"] == "744" and by_aid[dja["id"]]["amount_cents"] == 200000


def test_issues_and_overpaid(farm):
    client = farm["client"]
    _aid(client, scheme="calamity", campaign=2026, notified_cents=100000)    # décision non datée
    _aid(client, scheme="maec", campaign=2026, notified_cents=100000, payments=[("2026-12-04", 150000, "balance")])
    data = aid_closing.proposals(farm["fy"])
    assert data["items"] == [] and len(data["issues"]) == 2
    assert any("au-delà" in i["message"] for i in data["issues"])
    assert _checks(farm["fy"])["aid_issues"].count == 2


def test_not_in_simple_mode(app, login_as):
    client = login_as(role="admin")
    _agri_instance(bookkeeping="simple")
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    db.session.add(fy)
    db.session.commit()
    _aid(client, scheme="basic_income", campaign=2026, requested_cents=100000)
    body = client.get(f"/api/v1/fiscal-years/{fy.id}/closing/aids").get_json()
    assert body == {"items": [], "issues": [], "enabled": False}


def test_payment_request_deadline_in_agenda(farm):
    client = farm["client"]
    aid = _aid(client, scheme="investment", campaign=2026, notified_cents=1000000, decision_on="2026-04-01",
               payment_request_deadline="2026-12-15")
    items = agenda.occurrences(date(2026, 11, 1), date(2026, 12, 31), date(2026, 11, 2))["items"]
    (occ,) = [i for i in items if i["fiche_id"] == "PAC-07"]
    assert occ["period"] == "Subvention d'investissement (PCAE, FEADER, Région, FranceAgriMer) 2026"
    assert occ["status"] == "to_prepare" or occ["status"] == "upcoming"
    assert occ["link"] == "/aids/?campaign=2026" and occ["managed"] is True
    client.put(f"/api/v1/aids/{aid['id']}", json={"payment_requested_on": "2026-11-20"})
    (occ,) = [i for i in agenda.occurrences(date(2026, 11, 1), date(2026, 12, 31), date(2026, 11, 2))["items"]
              if i["fiche_id"] == "PAC-07"]
    assert occ["status"] == "done"
    assert Aid.query.count() == 1 and Account.query.filter_by(code="131").count() == 1


def test_delete_blocked_by_posted_accrual(farm):
    client = farm["client"]
    aid = _aid(client, scheme="basic_income", campaign=2026, requested_cents=100000)
    (item,) = client.get(farm["url"]).get_json()["items"]
    client.post(farm["url"], json={"items": [{"key": item["key"]}]})
    assert client.delete(f"/api/v1/aids/{aid['id']}").status_code == 409
