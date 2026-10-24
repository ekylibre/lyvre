"""API de rapprochement : lecture, actions groupées, annulation par rejeu de ``undo``."""
from datetime import date

import pytest

from app.extensions import db
from app.models import (
    Account, BankAccount, BankTransaction, FiscalYear, Journal, JournalEntry, Rule,
)
from app.services.ledger import post_validated_entry, validate_entry_payload


@pytest.fixture()
def client(app):
    app.config["LOGIN_DISABLED"] = True
    return app.test_client()


@pytest.fixture()
def base(session):
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    bq = Journal(code="BQ", label="Banque")
    bank, expense = Account(code="5121", label="CA"), Account(code="606", label="Achats")
    session.add_all([fy, bq, bank, expense])
    session.flush()
    ba = BankAccount(label="CA Courant", account_id=bank.id)
    session.add(ba)
    session.flush()
    bts = [
        BankTransaction(bank_account_id=ba.id, fitid=f"F{i}", amount_cents=amount,
                        transaction_date=date(2026, month, 10), label=label)
        for i, (amount, month, label) in enumerate([
            (-100, 3, "PRLV EDF"), (-250, 3, "CB LEROY"), (900, 4, "VIR HELLOASSO"),
        ])
    ]
    session.add_all(bts)
    session.commit()
    return {"fy": fy, "bq": bq, "bank": bank, "expense": expense, "ba": ba, "bts": bts}


def line_for(base, amount, day=10, month=3):
    value = abs(amount)
    bank_side = {"debit_cents": value} if amount > 0 else {"credit_cents": value}
    other = {"credit_cents": value} if amount > 0 else {"debit_cents": value}
    clean, errors = validate_entry_payload({
        "fiscal_year_id": base["fy"].id, "journal_id": base["bq"].id,
        "entry_date": date(2026, month, day).isoformat(), "description": "E",
        "lines": [{"account_id": base["bank"].id, **bank_side},
                  {"account_id": base["expense"].id, **other}],
    })
    assert not errors
    entry = post_validated_entry(clean)
    return next(l for l in entry.lines if l.account_id == base["bank"].id)


def replay(client, undo):
    assert undo["method"] == "POST"
    return client.post(undo["url"], json=undo["body"])


def test_list_transactions_with_filters_and_counters(client, base):
    ba = base["ba"].id
    data = client.get(f"/api/v1/bank-accounts/{ba}/transactions").get_json()
    assert [t["label"] for t in data["transactions"]] == ["PRLV EDF", "CB LEROY", "VIR HELLOASSO"]
    assert data["counters"] == {"unreconciled": 3, "total": 3}
    first = data["transactions"][0]
    assert first["amount_cents"] == -100 and first["entry"] is None
    assert first["new_entry_url"] == f"/entries/new?bt_id={first['id']}"

    march = client.get(f"/api/v1/bank-accounts/{ba}/transactions?month=2026-03&sort=desc").get_json()
    assert sorted(t["label"] for t in march["transactions"]) == ["CB LEROY", "PRLV EDF"]
    assert client.get("/api/v1/bank-accounts/999/transactions").status_code == 404


def test_suggestions(client, base):
    line = line_for(base, -100)
    data = client.get(f"/api/v1/bank-transactions/{base['bts'][0].id}/suggestions").get_json()
    assert data["suggestions"] == [{
        "journal_line_id": line.id, "entry_id": line.entry_id, "reference": line.entry.reference,
        "entry_date": "2026-03-10", "label": "E", "account_code": "5121",
        "amount_cents": -100, "score": 2,
    }]
    assert client.get("/api/v1/bank-transactions/999/suggestions").status_code == 404


def test_reconcile_batch_and_undo(client, base):
    l100, l250 = line_for(base, -100), line_for(base, -999)
    bt0, bt1 = base["bts"][0], base["bts"][1]
    resp = client.post("/api/v1/reconciliations", json={"items": [
        {"bank_transaction_id": bt0.id, "journal_line_id": l100.id},
        {"bank_transaction_id": bt1.id, "journal_line_id": l250.id},
    ]})
    data = resp.get_json()
    assert [r["status"] for r in data["results"]] == ["ok", "error"]
    assert data["counters"] == {"unreconciled": 2, "total": 3}
    assert data["undo"]["body"] == {"bank_transaction_ids": [bt0.id]}

    undone = replay(client, data["undo"]).get_json()
    assert undone["counters"]["unreconciled"] == 3
    assert db.session.get(BankTransaction, bt0.id).reconciled is False
    # L'annulation de l'annulation relie à nouveau la même ligne.
    assert undone["undo"]["body"] == {"items": [
        {"bank_transaction_id": bt0.id, "journal_line_id": l100.id}]}
    replay(client, undone["undo"])
    assert db.session.get(BankTransaction, bt0.id).journal_line_id == l100.id


def test_nothing_to_undo_when_all_fail(client, base):
    data = client.post("/api/v1/reconciliations", json={"items": [
        {"bank_transaction_id": base["bts"][0].id, "journal_line_id": 999}]}).get_json()
    assert data["undo"] is None and data["results"][0]["status"] == "error"


def test_auto_dry_run_then_real(client, base):
    line_for(base, -100)
    line_for(base, 900, month=4)
    ba = base["ba"].id
    dry = client.post("/api/v1/reconciliations/auto", json={"bank_account_id": ba, "dry_run": True}).get_json()
    assert [r["status"] for r in dry["results"]] == ["found", "found"]
    assert dry["counters"]["unreconciled"] == 3 and dry["undo"] is None

    real = client.post("/api/v1/reconciliations/auto", json={
        "bank_account_id": ba, "bank_transaction_ids": [base["bts"][0].id]}).get_json()
    assert [r["status"] for r in real["results"]] == ["ok"]  # limité à la sélection
    assert real["counters"]["unreconciled"] == 2
    replay(client, real["undo"])
    assert db.session.get(BankTransaction, base["bts"][0].id).reconciled is False

    assert client.post("/api/v1/reconciliations/auto", json={"bank_account_id": 999}).status_code == 404


def test_apply_rules_to_selection_and_undo(client, base):
    db.session.add(Rule(position=1, name="EDF", label_contains="EDF", account_code="606",
                        category="Énergie", is_active=True))
    db.session.commit()
    ids = [base["bts"][0].id, base["bts"][1].id]
    data = client.post("/api/v1/bank-transactions/apply-rules", json={"ids": ids}).get_json()
    assert data["summary"] == {"matched": 1, "posted": 1, "skipped": 1, "total": 2}
    assert data["counters"]["unreconciled"] == 2
    entry_ids = data["undo"]["body"]["entry_ids"]
    assert len(entry_ids) == 2  # pièce de règle + règlement

    undone = replay(client, data["undo"]).get_json()
    assert all(r["status"] == "ok" for r in undone["results"])
    assert all(db.session.get(JournalEntry, i) is None for i in entry_ids)
    bt = db.session.get(BankTransaction, base["bts"][0].id)
    assert bt.reconciled is False and bt.category == "Énergie"  # catégorie conservée


def test_bad_payloads(client, base):
    assert client.post("/api/v1/reconciliations", json={"items": "x"}).status_code == 400
    assert client.post("/api/v1/reconciliations/delete", json={"bank_transaction_ids": ["a"]}).status_code == 400
    assert client.post("/api/v1/bank-transactions/apply-rules", json={"ids": [999]}).status_code == 404


# --- page : îlot ReconcileWorkspace -----------------------------------------


def test_reconciliation_context(client, base):
    body = client.get("/api/v1/reconciliation/context").get_json()
    assert [(b["id"], b["label"], b["account"]["code"]) for b in body["bank_accounts"]] == [(base["ba"].id, "CA Courant", "5121")]
    assert body["default_journal_id"] == base["bq"].id
    assert len(body["months"]) == 12
    assert '<div id="root"></div>' in client.get("/reconciliation/?bank_account_id=999").get_data(as_text=True)


def test_reconciliation_context_without_bank_account(client, session):
    assert client.get("/api/v1/reconciliation/context").get_json()["bank_accounts"] == []


@pytest.mark.parametrize("method, url", [
    ("get", "/reconciliation/suggest/1"),
    ("post", "/reconciliation/link"),
    ("post", "/reconciliation/unlink/1"),
    ("post", "/reconciliation/auto"),
])
def test_legacy_reconciliation_routes_removed(client, base, method, url):
    assert getattr(client, method)(url).status_code == 404
