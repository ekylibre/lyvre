"""Transactions annulées par la banque et justificatifs : rapprochement, API, règles, vue du compte."""
from datetime import date

import pytest

from app.extensions import db
from app.models import (
    Account, BankAccount, BankTransaction, FiscalYear, Journal, JournalEntry, JournalLine, Rule,
)
from app.services import reconciler, rules_engine
from app.services.ledger import LedgerError, post_validated_entry, validate_entry_payload


@pytest.fixture()
def setup(app):
    bank, expense = Account(code="512", label="Banques"), Account(code="606", label="Achats")
    db.session.add_all([bank, expense, FiscalYear(label="2026", start_date=date(2026, 1, 1),
                                                  end_date=date(2026, 12, 31)),
                        Journal(code="BQ", label="Banque")])
    db.session.commit()
    ba = BankAccount(label="Qonto", account_id=bank.id, qonto_account_id="acc-1")
    db.session.add(ba)
    db.session.commit()
    return ba, bank, expense


def _txn(ba, fitid, amount=-1000, **extra):
    extra.setdefault("source", "qonto")
    txn = BankTransaction(bank_account_id=ba.id, fitid=fitid, amount_cents=amount,
                          transaction_date=date(2026, 9, 1), label=f"Libellé {fitid}", **extra)
    db.session.add(txn)
    db.session.commit()
    return txn


def _line(bank, expense, amount=1000):
    entry = JournalEntry(journal_id=Journal.query.first().id, fiscal_year_id=FiscalYear.query.first().id,
                         entry_date=date(2026, 9, 1), description="Achat", reference="BQ-1")
    db.session.add(entry)
    db.session.flush()
    bank_line = JournalLine(entry_id=entry.id, account_id=bank.id, debit_cents=0, credit_cents=amount)
    db.session.add_all([bank_line, JournalLine(entry_id=entry.id, account_id=expense.id,
                                               debit_cents=amount, credit_cents=0)])
    db.session.commit()
    return bank_line


def test_reversed_transaction_cannot_be_reconciled(setup):
    ba, bank, expense = setup
    line = _line(bank, expense)
    txn = _txn(ba, "rev", is_reversed=True)
    assert reconciler.suggest_matches_scored(txn.id) == []
    [result] = reconciler.reconcile_many([(txn.id, line.id)])
    assert result["status"] == "error" and "annulée par la banque" in result["message"]
    assert reconciler.auto_pairs(ba.id) == []


def test_reversed_transaction_refused_for_new_entry(setup):
    ba, bank, expense = setup
    txn = _txn(ba, "rev", is_reversed=True)
    clean, errors = validate_entry_payload({
        "fiscal_year_id": FiscalYear.query.first().id, "journal_id": Journal.query.first().id,
        "entry_date": "2026-09-01", "description": "Achat",
        "lines": [{"account_id": expense.id, "debit_cents": 1000, "credit_cents": 0},
                  {"account_id": bank.id, "debit_cents": 0, "credit_cents": 1000}],
    })
    assert errors == {}
    with pytest.raises(LedgerError, match="annulée par la banque"):
        post_validated_entry(clean, bank_transaction=txn)


def test_rules_skip_reversed_transactions(setup):
    ba, _, _ = setup
    db.session.add(Rule(position=1, name="Tout", label_contains="Libellé", category="X", account_code="606"))
    db.session.commit()
    txn = _txn(ba, "rev", is_reversed=True)
    result = rules_engine.apply_rules([txn])
    assert (result["matched"], result["skipped"]) == (0, 1)
    assert txn.category is None and txn.journal_line_id is None


def test_api_serializes_flags(setup):
    from app.api.reconciliation import attachment_status, serialize_transaction

    ba, _, _ = setup
    cases = {
        "ofx": _txn(ba, "ofx", source="ofx"),
        "ok": _txn(ba, "ok", attachment_count=1, attachment_required=True, attachment_lost=False),
        "missing": _txn(ba, "missing", attachment_count=0, attachment_required=True, attachment_lost=False),
        "lost": _txn(ba, "lost", attachment_count=0, attachment_required=True, attachment_lost=True),
        "optional": _txn(ba, "optional", attachment_count=0, attachment_required=False, attachment_lost=False),
    }
    expected = {"ofx": None, "ok": "ok", "missing": "missing", "lost": "lost", "optional": "ok"}
    assert {k: attachment_status(t) for k, t in cases.items()} == expected
    from flask import current_app
    with current_app.test_request_context():
        data = serialize_transaction(_txn(ba, "rev", is_reversed=True))
    assert data["is_reversed"] is True and data["attachment_status"] is None


def test_account_view_badges_filter_and_banner(login_as, setup):
    ba, bank, expense = setup
    _txn(ba, "missing", attachment_count=0, attachment_required=True, attachment_lost=False)
    _txn(ba, "ok", attachment_count=2, attachment_required=True, attachment_lost=False, note="Note Qonto")
    line = _line(bank, expense)
    _txn(ba, "rev", is_reversed=True, reconciled=True, journal_line_id=line.id)
    client = login_as(is_admin=False)

    detail = client.get(f"/api/v1/bank-accounts/{ba.id}").get_json()
    assert [t["entry"]["reference"] for t in detail["reversed_reconciled"]] == ["BQ-1"]
    rows = {r["label"]: r for r in client.get(f"/api/v1/bank-accounts/{ba.id}/transactions?status=all").get_json()["transactions"]}
    assert rows["Libellé rev"]["is_reversed"] is True
    assert rows["Libellé missing"]["attachment_status"] == "missing" and rows["Libellé ok"]["note"] == "Note Qonto"

    missing = client.get(f"/api/v1/bank-accounts/{ba.id}/transactions?status=all&missing=1").get_json()["transactions"]
    assert [r["label"] for r in missing] == ["Libellé missing"]
