"""Lot AG3.d : subventions d'investissement (design_aides_pac.md § 6, § 12).

Recette : subvention de 10 000 € sur un bien de 50 000 € amorti sur 5 ans en linéaire, mis en service le 01/07/2026
→ reprise de 1 000 € la 1re année (6 mois), 2 000 € ensuite ; cession en 3e année : reprise du reste.
"""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, AidRelease, Asset, BankAccount, BankTransaction, FiscalYear, Journal, JournalEntry
from app.models.journal_entry import SOURCE_AID_GRANT
from app.services import aid_closing, aid_grants
from test_agri_fixtures import _agri_instance


@pytest.fixture()
def farm(app, login_as):
    client = login_as(role="admin")
    _agri_instance()
    years = {y: FiscalYear(label=str(y), start_date=date(y, 1, 1), end_date=date(y, 12, 31)) for y in (2026, 2027, 2028)}
    building = Asset(label="Stabulation", account_id=Account.query.filter_by(code="2131").one().id,
                     acquired_on=date(2026, 7, 1), in_service_date=date(2026, 7, 1), acquisition_cents=5000000,
                     method="linear", duration_months=60, status="in_use")
    land = Asset(label="Parcelle des Prés", account_id=Account.query.filter_by(code="2111").one().id,
                 acquired_on=date(2026, 3, 1), acquisition_cents=3000000, method="none", status="in_use")
    db.session.add_all([*years.values(), building, land, Journal(code="BQ", label="Banque")])
    db.session.commit()
    return {"client": client, "fy": years, "building": building, "land": land}


def _aid(client, **data):
    resp = client.post("/api/v1/aids", json=data)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["item"]


def _releases(client, fy):
    return client.get(f"/api/v1/fiscal-years/{fy.id}/closing/aid-releases").get_json()


def test_release_follows_depreciation_then_disposal(farm):
    client, fy = farm["client"], farm["fy"]
    aid = _aid(client, scheme="investment", campaign=2026, notified_cents=1000000, decision_on="2026-03-01")
    url = f"/api/v1/aids/{aid['id']}/assets"
    assert client.put(url, json={"assets": [{"asset_id": farm["building"].id, "amount_cents": 1100000}]}).status_code == 422
    body = client.put(url, json={"assets": [{"asset_id": farm["building"].id, "amount_cents": 1000000}]}).get_json()["item"]
    assert body["investment"]["assets"][0]["label"] == "Stabulation"
    assert not any("Immobilisations financées" in w for w in body["warnings"])
    (row,) = _releases(client, fy[2026])["items"]
    assert row["kind"] == "depreciation" and row["amount_cents"] == 100000 and row["dotation_cents"] == 500000
    assert any(c[0] == "aid_release" for c in aid_closing.checks(fy[2026]))
    resp = client.post(f"/api/v1/fiscal-years/{fy[2026].id}/closing/aid-releases")
    assert resp.status_code == 200, resp.get_json()
    entry = aid_grants.release_entry(fy[2026])
    assert {(l.account.code, l.debit_cents, l.credit_cents) for l in entry.lines} == {("139", 100000, 0), ("747", 0, 100000)}
    assert entry.entry_date == date(2026, 12, 31)
    client.post(f"/api/v1/fiscal-years/{fy[2026].id}/closing/aid-releases")       # repassée : une seule écriture
    assert AidRelease.query.count() == 1 and not any(c[0] == "aid_release" for c in aid_closing.checks(fy[2026]))
    assert client.put(url, json={"assets": []}).status_code == 409                 # reprises passées
    (row,) = _releases(client, fy[2027])["items"]
    assert row["amount_cents"] == 200000
    client.post(f"/api/v1/fiscal-years/{fy[2027].id}/closing/aid-releases")
    building = farm["building"]
    building.status, building.disposal_date = "sold", date(2028, 6, 30)
    db.session.commit()
    (row,) = _releases(client, fy[2028])["items"]
    assert row["kind"] == "disposal" and row["amount_cents"] == 700000
    annex = _releases(client, fy[2028])["annex"][0]
    assert annex["released_before_cents"] == 300000 and annex["released_cents"] == 700000 and annex["remaining_cents"] == 0


def test_grant_then_payment_settles_441(farm):
    client, fy = farm["client"], farm["fy"]
    aid = _aid(client, scheme="investment", campaign=2026, notified_cents=1000000)
    url = f"/api/v1/aids/{aid['id']}/grant"
    assert client.post(url).status_code == 422                                    # décision à dater
    client.put(f"/api/v1/aids/{aid['id']}", json={"decision_on": "2026-03-01"})
    resp = client.post(url)
    assert resp.status_code == 200, resp.get_json()
    entry = JournalEntry.query.filter_by(source=SOURCE_AID_GRANT).one()
    assert {(l.account.code, l.debit_cents, l.credit_cents) for l in entry.lines} == {("441", 1000000, 0), ("131", 0, 1000000)}
    assert resp.get_json()["item"]["investment"]["grant_entry"]["entry_date"] == "2026-03-01"
    assert not any(c[0] == "aid_441" for c in aid_closing.checks(fy[2026]))     # octroi restant à percevoir
    bank = BankAccount(label="CIC", account_id=Account.query.filter_by(code="512").one().id)
    db.session.add(bank)
    db.session.flush()
    tx = BankTransaction(bank_account_id=bank.id, fitid="G1", transaction_date=date(2026, 9, 1), amount_cents=1000000,
                         label="VIR ASP PCAE")
    db.session.add(tx)
    db.session.commit()
    resp = client.post("/api/v1/aids/link", json={"bank_transaction_id": tx.id, "book": True,
                                                  "allocations": [{"aid_id": aid["id"], "amount_cents": 1000000}]})
    assert resp.status_code == 200, resp.get_json()
    db.session.refresh(tx)
    assert {l.account.code for l in tx.journal_line.entry.lines if l.credit_cents} == {"441"}
    assert client.delete(url).status_code == 409                                 # versement rattaché
    assert client.delete(f"/api/v1/aids/{aid['id']}").status_code == 409


def test_manual_release_for_land_and_dja(farm):
    client, fy = farm["client"], farm["fy"]
    dja = _aid(client, scheme="dja", campaign=2026, notified_cents=3000000, decision_on="2026-03-01")
    client.put(f"/api/v1/aids/{dja['id']}", json={"investment_share_cents": 2000000})
    client.put(f"/api/v1/aids/{dja['id']}/assets", json={"assets": [{"asset_id": farm["land"].id, "amount_cents": 500000}]})
    assert _releases(client, fy[2026])["items"] == []                             # terre : pas de reprise calculée
    manual = f"/api/v1/fiscal-years/{fy[2026].id}/closing/aid-releases/manual"
    assert client.post(manual, json={"aid_id": dja["id"], "amount_cents": 50000, "reason": "x"}).status_code == 422
    assert client.post(manual, json={"aid_id": dja["id"], "amount_cents": 2500000,
                                     "reason": "Clause d'inaliénabilité 10 ans"}).status_code == 422   # > part d'investissement
    resp = client.post(manual, json={"aid_id": dja["id"], "amount_cents": 50000, "asset_id": farm["land"].id,
                                     "reason": "Clause d'inaliénabilité 10 ans"}).get_json()
    (row,) = resp["items"]
    assert row["kind"] == "manual" and row["posted"] is False
    client.post(f"/api/v1/fiscal-years/{fy[2026].id}/closing/aid-releases")
    (row,) = _releases(client, fy[2026])["items"]
    assert row["posted"] is True
    assert client.delete(f"{manual}/{row['release_id']}").status_code == 409
    client.delete(f"/api/v1/fiscal-years/{fy[2026].id}/closing/aid-releases")     # annulée : la saisie reste
    (row,) = _releases(client, fy[2026])["items"]
    assert row["posted"] is False and client.delete(f"{manual}/{row['release_id']}").status_code == 200
    grant = client.post(f"/api/v1/aids/{dja['id']}/grant").get_json()["item"]
    assert grant["investment"]["grant_entry"] is not None                         # octroi de la part d'investissement
    lines = JournalEntry.query.filter_by(source=SOURCE_AID_GRANT).one().lines
    assert {(l.account.code, l.debit_cents) for l in lines} == {("441", 2000000), ("131", 0)}


def test_simple_mode_has_no_entries(app, login_as):
    client = login_as(role="admin")
    _agri_instance(bookkeeping="simple")
    db.session.add(FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)))
    db.session.commit()
    aid = _aid(client, scheme="investment", campaign=2026, notified_cents=100000, decision_on="2026-03-01")
    assert client.post(f"/api/v1/aids/{aid['id']}/grant").status_code == 409
