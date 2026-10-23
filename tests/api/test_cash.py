"""Lot D.1 : caisse — compte de nature caisse (53x), mouvements saisis, dépôt en banque par 581
sans effet sur les recettes ni les dépenses, contrôles (solde négatif, 58 non soldé)."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, BankAccount, FiscalYear, JournalEntry
from app.services import closing


def _error(resp, status):
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()["error"]


@pytest.fixture()
def books(app):
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    accounts = {c: Account(code=c, label=f"Compte {c}", account_type="OTHER")
                for c in ("512", "530", "581", "756", "6063")}
    db.session.add_all([fy, *accounts.values()])
    db.session.commit()
    bank = BankAccount(label="CIC", account_id=accounts["512"].id)
    db.session.add(bank)
    db.session.commit()
    return {"fy": fy, "bank": bank, **{c: a.id for c, a in accounts.items()}}


def _create_cash(client, books):
    resp = client.post("/api/v1/bank-accounts", json={"label": "Caisse buvette", "kind": "cash",
                                                      "account_id": books["530"], "iban": "FR76 1234"})
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["item"]


def test_cash_account_rules(books, login_as):
    client = login_as()
    assert "caisse (53" in _error(client.post("/api/v1/bank-accounts", json={
        "label": "X", "kind": "cash", "account_id": books["512"]}), 422)["message"]
    item = _create_cash(client, books)
    assert item["kind"] == "cash" and item["iban"] is None and item["balance_cents"] == 0
    listing = client.get("/api/v1/bank-accounts").get_json()
    assert [o["label"] for o in listing["meta"]["cash_accounts"]] == ["530 — Compte 530"]
    # Hors rapprochement et sans relevé OFX.
    assert [b["label"] for b in client.get("/api/v1/reconciliation/context").get_json()["bank_accounts"]] == ["CIC"]
    from io import BytesIO
    _error(client.post("/api/v1/imports/ofx", data={"bank_account_id": item["id"], "ofx_file": (BytesIO(b"x"), "r.ofx")},
                       content_type="multipart/form-data"), 422)


def test_movements_and_deposit(books, login_as):
    client = login_as()
    cash_id = _create_cash(client, books)["id"]
    url = f"/api/v1/bank-accounts/{cash_id}/cash"
    assert client.post(url, json={"date": "2026-03-01", "label": "Cotisations en espèces", "direction": "in",
                                  "amount_cents": 12000, "account_id": books["756"]}).status_code == 201
    assert client.post(url, json={"date": "2026-03-02", "label": "Gobelets", "direction": "out",
                                  "amount_cents": 2000, "account_id": books["6063"]}).status_code == 201
    assert "négative" in _error(client.post(url, json={"date": "2026-03-03", "label": "Trop", "direction": "out",
                                                       "amount_cents": 50000, "account_id": books["6063"]}), 409)["message"]
    assert "Dépôt en banque" in _error(client.post(url, json={"date": "2026-03-03", "label": "Banque", "direction": "out",
                                                              "amount_cents": 100, "account_id": books["512"]}), 422)["message"]
    resp = client.post(f"{url}/deposit", json={"date": "2026-03-10", "amount_cents": 8000, "bank_account_id": books["bank"].id})
    assert resp.status_code == 201
    _error(client.post(f"{url}/deposit", json={"date": "2026-03-11", "amount_cents": 5000,
                                               "bank_account_id": books["bank"].id}), 409)  # solde 2 000
    data = client.get(url).get_json()
    assert [r["amount_cents"] for r in data["rows"]] == [12000, -2000, -8000]
    assert data["closing_cents"] == 2000 and data["rows"][2]["deposit"] is True
    assert data["item"]["balance_cents"] == 2000
    period = client.get(f"{url}?start=2026-03-02").get_json()
    assert period["opening_cents"] == 12000 and len(period["rows"]) == 2
    # Le dépôt passe par 581 : ni recette ni dépense, 581 soldé, banque créditée de 80,00.
    assert closing.result(books["fy"]) == {"income_cents": 12000, "expense_cents": 2000, "result_cents": 10000}
    entries = JournalEntry.query.filter_by(source="CASH").all()
    assert sorted(e.journal.code for e in entries) == ["BQ", "CA", "CA", "CA"]
    assert not [c for c in closing.checks(books["fy"]) if c.key.startswith("transfer_")]


def test_unbalanced_transfer_is_reported(books):
    from app.models import Journal
    from app.services.ledger import post_entry
    od = Journal(code="OD", label="OD")
    db.session.add(od)
    db.session.commit()
    post_entry(books["fy"].id, od.id, date(2026, 5, 1), "Dépôt sans banque", [
        {"account_id": books["581"], "debit_cents": 3000}, {"account_id": books["530"], "credit_cents": 3000}])
    assert [c.key for c in closing.checks(books["fy"]) if c.key.startswith("transfer_")] == ["transfer_581"]
