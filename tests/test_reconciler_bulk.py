"""Rapprochement par lots : contrôles, atomicité, auto-rapprochement, suppression sûre."""
from datetime import date

import pytest

from app.extensions import db
from app.models import (
    Account, BankAccount, BankTransaction, FiscalYear, Journal, JournalEntry, JournalLine, Rule,
)
from app.services.ledger import delete_entries, post_validated_entry, validate_entry_payload
from app.services.reconciler import (
    auto_reconcile, reconcile_many, suggest_matches_scored, unreconcile_many,
)
from app.services.rules_engine import apply_rules


@pytest.fixture()
def base(session):
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    bq = Journal(code="BQ", label="Banque")
    bank, other_bank = Account(code="5121", label="CA"), Account(code="5122", label="Autre")
    expense = Account(code="606", label="Achats")
    session.add_all([fy, bq, bank, other_bank, expense])
    session.flush()
    ba = BankAccount(label="CA Courant", account_id=bank.id)
    session.add(ba)
    session.commit()
    return {"fy": fy, "bq": bq, "bank": bank, "other_bank": other_bank, "expense": expense, "ba": ba}


def txn(base, amount, day=10, fitid=None):
    bt = BankTransaction(bank_account_id=base["ba"].id, fitid=fitid or f"F{amount}-{day}",
                         amount_cents=amount, transaction_date=date(2026, 3, day), label="X")
    db.session.add(bt)
    db.session.commit()
    return bt


def entry(base, amount, day=10, bank_account="bank"):
    """Écriture de dépense (amount < 0) ou de recette, côté banque sur ``bank_account``."""
    value = abs(amount)
    bank_side = {"debit_cents": value} if amount > 0 else {"credit_cents": value}
    other_side = {"credit_cents": value} if amount > 0 else {"debit_cents": value}
    clean, errors = validate_entry_payload({
        "fiscal_year_id": base["fy"].id, "journal_id": base["bq"].id,
        "entry_date": date(2026, 3, day).isoformat(), "description": "E",
        "lines": [{"account_id": base[bank_account].id, **bank_side},
                  {"account_id": base["expense"].id, **other_side}],
    })
    assert not errors
    e = post_validated_entry(clean)
    return e, next(l for l in e.lines if l.account_id == base[bank_account].id)


def test_suggestions_restricted_to_bank_ledger_account_and_scored(base):
    bt = txn(base, -5000, day=10)
    _e1, same_day = entry(base, -5000, day=10)
    _e2, near = entry(base, -5000, day=12)
    entry(base, -5000, day=10, bank_account="other_bank")  # autre compte : exclu
    entry(base, 5000, day=10)                             # sens opposé : exclu
    scored = suggest_matches_scored(bt.id)
    assert [(l.id, s) for l, s in scored] == [(same_day.id, 2), (near.id, 1)]


def test_reconcile_many_checks_each_pair(base):
    ok_bt, wrong_amount_bt, done_bt = txn(base, -100, fitid="a"), txn(base, -200, fitid="b"), txn(base, -300, fitid="c")
    _e, line_100 = entry(base, -100)
    _e, line_999 = entry(base, -999)
    _e, line_300 = entry(base, -300)
    _e, other_account = entry(base, -100, bank_account="other_bank")
    reconcile_many([(done_bt.id, line_300.id)])

    results = reconcile_many([
        (ok_bt.id, line_100.id),
        (wrong_amount_bt.id, line_999.id),
        (done_bt.id, line_300.id),
        (wrong_amount_bt.id, other_account.id),
        (9999, line_100.id),
    ])
    statuses = [(r["status"], r.get("message")) for r in results]
    assert statuses == [
        ("ok", None),
        ("error", "Montant différent de celui de la transaction."),
        ("error", "Transaction déjà rapprochée."),
        ("error", "La ligne n'est pas sur le compte comptable du compte bancaire."),
        ("error", "Transaction bancaire introuvable."),
    ]
    assert db.session.get(BankTransaction, ok_bt.id).journal_line_id == line_100.id
    assert db.session.get(BankTransaction, wrong_amount_bt.id).reconciled is False


def test_same_line_cannot_be_used_twice_in_a_batch(base):
    a, b = txn(base, -100, fitid="a"), txn(base, -100, fitid="b")
    _e, line = entry(base, -100)
    results = reconcile_many([(a.id, line.id), (b.id, line.id)])
    assert [r["status"] for r in results] == ["ok", "error"]
    assert results[1]["message"] == "Ligne d'écriture déjà rapprochée."


def test_unreconcile_many_returns_previous_lines(base):
    bt = txn(base, -100)
    _e, line = entry(base, -100)
    reconcile_many([(bt.id, line.id)])
    other = txn(base, -7, fitid="n")
    results = unreconcile_many([bt.id, other.id])
    assert results[0] == {"bank_transaction_id": bt.id, "status": "ok", "journal_line_id": line.id}
    assert results[1]["message"] == "Transaction non rapprochée."
    assert db.session.get(BankTransaction, bt.id).reconciled is False
    # Rejouer le lien (annulation de l'annulation)
    assert reconcile_many([(bt.id, line.id)])[0]["status"] == "ok"


def test_auto_reconcile_only_unambiguous_pairs(base):
    clear = txn(base, -100, day=5, fitid="clear")
    _e, clear_line = entry(base, -100, day=5)
    twin_a, twin_b = txn(base, -40, day=6, fitid="ta"), txn(base, -40, day=6, fitid="tb")
    entry(base, -40, day=6)  # une ligne pour deux transactions : ambigu
    two_lines = txn(base, -60, day=7, fitid="tl")
    entry(base, -60, day=7)
    entry(base, -60, day=7)  # deux lignes candidates : ambigu

    found = auto_reconcile(base["ba"].id, dry_run=True)
    assert found == [{"bank_transaction_id": clear.id, "journal_line_id": clear_line.id,
                      "status": "found"}]
    assert db.session.get(BankTransaction, clear.id).reconciled is False  # dry run

    results = auto_reconcile(base["ba"].id)
    assert [r["status"] for r in results] == ["ok"]
    for bt in (twin_a, twin_b, two_lines):
        assert db.session.get(BankTransaction, bt.id).reconciled is False


def test_delete_entries_unlinks_reconciliation(base):
    bt = txn(base, -100)
    e, line = entry(base, -100)
    reconcile_many([(bt.id, line.id)])
    results = delete_entries([e.id, 9999])
    assert results[0]["status"] == "ok" and results[1]["status"] == "error"
    refreshed = db.session.get(BankTransaction, bt.id)
    assert refreshed.reconciled is False and refreshed.journal_line_id is None
    assert db.session.get(JournalEntry, e.id) is None
    assert JournalLine.query.filter_by(entry_id=e.id).count() == 0


def test_delete_entries_refuses_closed_year(base):
    e, _line = entry(base, -100)
    base["fy"].closed = True
    db.session.commit()
    assert delete_entries([e.id])[0]["message"] == "Exercice clôturé : suppression impossible."
    assert db.session.get(JournalEntry, e.id) is not None


def test_apply_rules_returns_created_entries(base):
    db.session.add(Rule(position=1, name="Fournitures", label_contains="X",
                        account_code="606", is_active=True))
    db.session.commit()
    bt = txn(base, -2500)
    result = apply_rules([bt])
    assert result["posted"] == 1 and len(result["created_entry_ids"]) == 2  # pièce + règlement
    document, settlement = (db.session.get(JournalEntry, i) for i in result["created_entry_ids"])
    assert (document.source, settlement.source_ref) == ("RULE", f"FITID:{bt.fitid}")
    assert db.session.get(BankTransaction, bt.id).reconciled is True


def test_entry_delete_view_unlinks_reconciliation(app, base):
    app.config["LOGIN_DISABLED"] = True
    bt = txn(base, -100)
    e, line = entry(base, -100)
    reconcile_many([(bt.id, line.id)])
    resp = app.test_client().delete(f"/api/v1/entries/{e.id}")
    assert resp.status_code == 200
    assert db.session.get(BankTransaction, bt.id).reconciled is False
