"""Lot D.3 : recettes et dépenses de la comptabilité simplifiée — écriture générée (source SIMPLE),
catégorisation d'une transaction importée (rapprochée), modification, suppression, liste."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, BankAccount, BankTransaction, Entity, FiscalYear, JournalEntry, SimpleCategory
from app.services import closing


def _error(resp, status):
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()["error"]


@pytest.fixture()
def books(app):
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    accounts = {c: Account(code=c, label=f"Compte {c}", account_type="OTHER")
                for c in ("512", "530", "756", "7541", "6061", "613")}
    db.session.add_all([fy, *accounts.values(), Entity(name="Mairie", entity_type="ORGANISME")])
    db.session.commit()
    bank = BankAccount(label="CIC", account_id=accounts["512"].id)
    till = BankAccount(label="Caisse", account_id=accounts["530"].id, kind="cash")
    db.session.add_all([bank, till])
    db.session.commit()
    return {"fy": fy, "bank": bank, "till": till, **{c: a.id for c, a in accounts.items()}}


def _category(client, code):
    items = client.get("/api/v1/simple/operations").get_json()["meta"]["categories"]
    return next(c["id"] for c in items if c["code"] == code)


def test_create_generates_double_entry(books, login_as):
    client = login_as()
    cotisations = _category(client, "cotisations")
    resp = client.post("/api/v1/simple/operations", json={
        "date": "2026-02-01", "label": "Cotisation Dupont", "amount_cents": 3000, "category_id": cotisations,
        "bank_account_id": books["bank"].id, "entity_id": Entity.query.one().id})
    assert resp.status_code == 201
    entry = JournalEntry.query.one()
    assert entry.source == "SIMPLE" and entry.journal.code == "BQ"
    assert {l.account.code: (l.debit_cents, l.credit_cents) for l in entry.lines} == {"512": (3000, 0), "756": (0, 3000)}
    client.post("/api/v1/simple/operations", json={"date": "2026-02-03", "label": "Fournitures", "amount_cents": 1200,
                                                  "category_id": _category(client, "achats"), "bank_account_id": books["till"].id})
    cash_entry = JournalEntry.query.filter(JournalEntry.description == "Fournitures").one()
    assert cash_entry.journal.code == "CA"
    assert closing.result(books["fy"]) == {"income_cents": 3000, "expense_cents": 1200, "result_cents": 1800}
    data = client.get("/api/v1/simple/operations").get_json()
    assert (data["income_cents"], data["expense_cents"], data["balance_cents"]) == (3000, 1200, 1800)
    assert [(r["label"], r["amount_cents"], r["category"], r["bank_account"]) for r in data["rows"]] == [
        ("Fournitures", -1200, "Achats et fournitures", "Caisse"), ("Cotisation Dupont", 3000, "Cotisations", "CIC")]
    assert data["rows"][1]["entity"] == "Mairie"
    assert client.get("/api/v1/simple/operations?month=2026-02&kind=income").get_json()["income_cents"] == 3000
    assert client.get("/api/v1/simple/operations?month=2026-03").get_json()["rows"] == []
    _error(client.post("/api/v1/simple/operations", json={"date": "2027-05-01", "label": "X", "amount_cents": 1,
                                                          "category_id": cotisations, "bank_account_id": books["bank"].id}), 422)


def test_update_and_delete(books, login_as):
    client = login_as()
    cotisations, dons = _category(client, "cotisations"), _category(client, "dons")
    client.post("/api/v1/simple/operations", json={"date": "2026-04-01", "label": "Versement", "amount_cents": 5000,
                                                  "category_id": cotisations, "bank_account_id": books["bank"].id})
    entry = JournalEntry.query.one()
    assert client.put(f"/api/v1/simple/operations/{entry.id}", json={
        "date": "2026-04-02", "label": "Don Durand", "amount_cents": 6000, "category_id": dons,
        "bank_account_id": books["bank"].id}).status_code == 200
    db.session.refresh(entry)
    assert {l.account.code: l.credit_cents for l in entry.lines if l.credit_cents} == {"7541": 6000}
    assert entry.entry_date == date(2026, 4, 2)
    assert client.delete(f"/api/v1/simple/operations/{entry.id}").status_code == 200
    assert JournalEntry.query.count() == 0


def test_categorize_bank_transaction(books, login_as):
    client = login_as()
    db.session.add_all([
        BankTransaction(bank_account_id=books["bank"].id, fitid="T1", transaction_date=date(2026, 3, 5),
                        amount_cents=-8000, label="PRLV LOYER"),
        BankTransaction(bank_account_id=books["bank"].id, fitid="T2", transaction_date=date(2026, 3, 6),
                        amount_cents=2500, label="VIR COTIS")])
    db.session.commit()
    pending = client.get("/api/v1/simple/to-categorize").get_json()["items"]
    assert [t["label"] for t in pending] == ["VIR COTIS", "PRLV LOYER"]
    loyer = next(t for t in pending if t["label"] == "PRLV LOYER")
    assert "dépense" in _error(client.post(f"/api/v1/simple/to-categorize/{loyer['id']}",
                                           json={"category_id": _category(client, "cotisations")}), 422)["message"]
    assert client.post(f"/api/v1/simple/to-categorize/{loyer['id']}",
                       json={"category_id": _category(client, "locations")}).status_code == 201
    bt = db.session.get(BankTransaction, loyer["id"])
    assert bt.reconciled and bt.journal_line.account.code == "512" and bt.journal_line.credit_cents == 8000
    _error(client.post(f"/api/v1/simple/to-categorize/{loyer['id']}", json={"category_id": _category(client, "locations")}), 409)
    assert [t["label"] for t in client.get("/api/v1/simple/to-categorize").get_json()["items"]] == ["VIR COTIS"]
    # Rapprochée : date et montant suivent le relevé ; la catégorie garde son sens.
    row = client.get("/api/v1/simple/operations").get_json()["rows"][0]
    assert row["reconciled"] and row["amount_cents"] == -8000
    _error(client.put(f"/api/v1/simple/operations/{row['entry_id']}", json={
        "label": "Loyer", "category_id": _category(client, "cotisations")}), 422)
    assert client.put(f"/api/v1/simple/operations/{row['entry_id']}", json={
        "label": "Loyer mars", "category_id": _category(client, "achats"), "amount_cents": 1, "date": "2026-12-01"}).status_code == 200
    entry = db.session.get(JournalEntry, row["entry_id"])
    db.session.refresh(entry)
    assert entry.entry_date == date(2026, 3, 5) and {l.account.code for l in entry.lines} == {"512", "6061"}
    assert sum(l.debit_cents for l in entry.lines) == 8000


def test_accountant_reads_only(books, login_as):
    client = login_as(role="accountant")
    assert client.get("/api/v1/simple/operations").status_code == 200
    _error(client.post("/api/v1/simple/operations", json={}), 403)
