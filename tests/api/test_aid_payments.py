"""Lot AG3.b : virements d'aides rapprochés des dossiers (claudedocs/design_aides_pac.md § 5, AGD20 Q-P6)."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, AidPayment, BankAccount, BankTransaction, FiscalYear, Instance, Journal, JournalEntry
from app.services import aid_payments, closing, simple_categories
from test_agri_fixtures import _agri_instance


def _tx(bank, day, cents, label, n=[0], counterparty=None):
    n[0] += 1
    tx = BankTransaction(bank_account_id=bank.id, fitid=f"A{n[0]}", transaction_date=day, amount_cents=cents,
                         label=label, counterparty=counterparty)
    db.session.add(tx)
    db.session.commit()
    return tx


@pytest.fixture()
def farm(app, login_as):
    client = login_as(role="admin")
    _agri_instance()
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    bank = BankAccount(label="CIC", account_id=Account.query.filter_by(code="512").one().id)
    db.session.add_all([fy, bank, Journal(code="BQ", label="Banque")])
    db.session.commit()
    return {"client": client, "bank": bank, "fy": fy}


def _aid(client, **data):
    resp = client.post("/api/v1/aids", json=data)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["item"]


def test_payer_recognition():
    tx = BankTransaction(label="VIR SEPA AGENCE DE SERVICES ET DE PAIEMENT", amount_cents=1)
    assert aid_payments.payer_of(tx) == "ASP"
    assert aid_payments.payer_of(BankTransaction(label="VIREMENT", counterparty="A.S.P.", amount_cents=1)) == "ASP"
    assert aid_payments.payer_of(BankTransaction(label="VIR FRANCEAGRIMER AIDE", amount_cents=1)) == "FranceAgriMer"
    assert aid_payments.payer_of(BankTransaction(label="VIR WASP SARL", amount_cents=1)) is None   # mot entier
    assert aid_payments.payer_of(BankTransaction(label="VIR DGFIP REMB TVA", amount_cents=1)) is None


def test_split_transfer_on_two_aids_and_book(farm):
    client = farm["client"]
    base = _aid(client, scheme="basic_income", campaign=2026, requested_cents=800000)
    eco = _aid(client, scheme="eco_scheme", campaign=2026, requested_cents=200000)
    _aid(client, scheme="region_operating", campaign=2026, notified_cents=921018)       # autre payeur
    tx = _tx(farm["bank"], date(2026, 10, 16), 921018, "VIR ASP PAC 2026 AVANCE")
    found = client.get(f"/api/v1/aids/candidates?bank_transaction_id={tx.id}").get_json()["item"]
    assert found["payer"] == "ASP" and found["free_cents"] == 921018 and found["transaction"]["booked"] is False
    assert [r["aid"]["scheme"] for r in found["items"]][:2] == ["basic_income", "eco_scheme"]
    assert found["items"][-1]["payer_match"] is False                         # aide régionale : en dernier
    allocations = [{"aid_id": base["id"], "amount_cents": 721018, "kind": "advance"},
                   {"aid_id": eco["id"], "amount_cents": 200000, "kind": "advance"}]
    too_much = [{**allocations[0], "amount_cents": 800000}, allocations[1]]
    assert client.post("/api/v1/aids/link", json={"bank_transaction_id": tx.id, "allocations": too_much}).status_code == 422
    partial = [allocations[0]]
    assert client.post("/api/v1/aids/link", json={"bank_transaction_id": tx.id, "allocations": partial,
                                                  "book": True}).status_code == 422     # ventiler la totalité
    resp = client.post("/api/v1/aids/link", json={"bank_transaction_id": tx.id, "allocations": allocations, "book": True})
    assert resp.status_code == 200, resp.get_json()
    assert "comptabilisé" in resp.get_json()["notices"][0]["message"]
    db.session.refresh(tx)
    assert tx.reconciled and tx.journal_line_id is not None
    entry = tx.journal_line.entry
    credits = {line.account.code: line.credit_cents for line in entry.lines if line.credit_cents}
    assert credits == {"7451": 721018, "7453": 200000} and entry.journal.code == "BQ"
    assert client.get(f"/api/v1/aids/{base['id']}").get_json()["item"]["remaining_cents"] == 78982
    again = client.get(f"/api/v1/aids/candidates?bank_transaction_id={tx.id}").get_json()["item"]
    assert again["free_cents"] == 0 and again["transaction"]["booked_accounts"] == ["7451", "7453"]


def test_already_booked_transfer_is_never_rewritten(farm):
    client = farm["client"]
    aid = _aid(client, scheme="coupled_animal", campaign=2026, requested_cents=300000)
    tx = _tx(farm["bank"], date(2026, 12, 4), 300000, "VIR ASP AIDES BOVINES")
    from app.services.rules_engine import _post_entry_for_transaction
    line = _post_entry_for_transaction(tx, "745", "règle ASP")                  # règle « Aides PAC (ASP) »
    tx.journal_line_id, tx.reconciled = line.id, True
    db.session.commit()
    count = JournalEntry.query.count()
    payload = {"bank_transaction_id": tx.id, "allocations": [{"aid_id": aid["id"], "amount_cents": 300000}]}
    assert client.post("/api/v1/aids/link", json={**payload, "book": True}).status_code == 409
    resp = client.post("/api/v1/aids/link", json=payload).get_json()
    assert any("comptabilisé en 745" in n["message"] and n["level"] == "warning" for n in resp["notices"])
    assert JournalEntry.query.count() == count
    payment = AidPayment.query.one()
    detached = client.delete(f"/api/v1/aids/{aid['id']}/payments/{payment.id}").get_json()
    assert "écriture est conservée" in detached["notices"][0]["message"] and JournalEntry.query.count() == count


def test_mixed_dja_split_and_refusals(farm):
    client = farm["client"]
    dja = _aid(client, scheme="dja", campaign=2026, notified_cents=3000000, decision_on="2026-03-01")
    tx = _tx(farm["bank"], date(2026, 6, 1), 2400000, "VIR ASP DJA 1ERE FRACTION")
    payload = {"bank_transaction_id": tx.id, "allocations": [{"aid_id": dja["id"], "amount_cents": 2400000,
                                                              "kind": "installment"}], "book": True}
    assert client.post("/api/v1/aids/link", json=payload).status_code == 422     # ventilation à saisir
    client.put(f"/api/v1/aids/{dja['id']}", json={"investment_share_cents": 2000000})
    assert client.post("/api/v1/aids/link", json=payload).status_code == 200
    db.session.refresh(tx)
    credits = {l.account.code: l.credit_cents for l in tx.journal_line.entry.lines if l.credit_cents}
    assert credits == {"131": 1600000, "744": 800000}
    debit = _tx(farm["bank"], date(2026, 6, 2), -5000, "PRLV ASP")
    assert client.get(f"/api/v1/aids/candidates?bank_transaction_id={debit.id}").status_code == 422


def test_transactions_list_and_closing_check(farm):
    client = farm["client"]
    tx = _tx(farm["bank"], date(2026, 10, 16), 50000, "VIR ASP")
    _tx(farm["bank"], date(2026, 10, 17), 70000, "VIR CLIENT DUPONT")
    rows = client.get(f"/api/v1/bank-accounts/{farm['bank'].id}/transactions?status=all").get_json()["transactions"]
    by_id = {r["id"]: r for r in rows}
    assert by_id[tx.id]["aid"] == {"payer": "ASP", "links": [], "free_cents": 50000}
    assert sum(1 for r in rows if r["aid"]) == 1
    checks = {c.key: c for c in closing._agri_checks(farm["fy"])}
    assert checks["aid_unlinked"].count == 1 and checks["aid_unlinked"].severity == "info"
    aid = _aid(client, scheme="basic_income", campaign=2026, requested_cents=50000)
    client.post("/api/v1/aids/link", json={"bank_transaction_id": tx.id,
                                           "allocations": [{"aid_id": aid["id"], "amount_cents": 50000}]})
    assert "aid_unlinked" not in {c.key for c in closing._agri_checks(farm["fy"])}
    rows = client.get(f"/api/v1/bank-accounts/{farm['bank'].id}/transactions?status=all").get_json()["transactions"]
    assert {r["id"]: r for r in rows}[tx.id]["aid"]["links"][0]["label"] == "Aide de base au revenu (DPB) 2026"


def test_simple_mode_books_on_the_category(app, login_as):
    client = login_as(role="admin")
    _agri_instance(bookkeeping="simple")
    simple_categories.ensure_defaults()
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    bank = BankAccount(label="CIC", account_id=Account.query.filter_by(code="512").one().id)
    db.session.add_all([fy, bank])
    db.session.commit()
    aid = _aid(client, scheme="basic_income", campaign=2026, requested_cents=100000)    # crée 7451 sous 745
    tx = _tx(bank, date(2026, 10, 16), 100000, "VIR ASP")
    resp = client.post("/api/v1/aids/link", json={"bank_transaction_id": tx.id, "book": True,
                                                  "allocations": [{"aid_id": aid["id"], "amount_cents": 100000}]})
    assert resp.status_code == 200, resp.get_json()
    db.session.refresh(tx)
    credits = {l.account.code for l in tx.journal_line.entry.lines if l.credit_cents}
    assert credits == {"745"}                                                   # catégorie « Aides PAC découplées »
    assert Instance.query.one().bookkeeping == "simple"
