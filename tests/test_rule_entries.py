"""Écritures de règle en partie double : pièce + règlement lettrés sur un compte de tiers (tiers par
défaut 401000 / 411000), mode simplifié inchangé, attribution d'un vrai tiers (API comprise)."""
from datetime import date, datetime
from types import SimpleNamespace

import pytest
from flask import g

from app.extensions import db
from app.models import (
    Account, BankAccount, BankTransaction, Entity, FiscalYear, Journal, JournalEntry, Rule,
)
from app.services import rule_entries, validation
from app.services.ledger import reversed_entry_ids
from app.services.rules_engine import apply_rules


@pytest.fixture()
def books(app):
    accounts = {code: Account(code=code, label=f"Compte {code}", account_type="TIERS" if code[0] == "4" else "CHARGE",
                              is_header=code in ("401", "411"))
                for code in ("401", "411", "512", "606", "706")}
    db.session.add_all([*accounts.values(), Journal(code="BQ", label="Banque"),
                        FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)),
                        Rule(position=1, name="EDF", label_contains="EDF", account_code="606", category="Énergie"),
                        Rule(position=2, name="Loyer", label_contains="LOYER", account_code="706", category="Loyers")])
    db.session.flush()
    ba = BankAccount(label="Banque", account_id=accounts["512"].id)
    db.session.add(ba)
    db.session.commit()
    return {"ba": ba, **accounts}


def txn(books, amount, label, fitid):
    bt = BankTransaction(bank_account_id=books["ba"].id, fitid=fitid, transaction_date=date(2026, 3, 10),
                         amount_cents=amount, label=label, source="ofx")
    db.session.add(bt)
    db.session.commit()
    return bt


def lines(entry):
    return sorted((l.account.code, l.debit_cents, l.credit_cents) for l in entry.lines)


def rule_pair(bt):
    return rule_entries.document_of(bt), bt.journal_line.entry


def test_expense_rule_goes_through_default_supplier(books):
    bt = txn(books, -5000, "PRLV EDF", "E1")
    assert apply_rules([bt])["posted"] == 1
    document, settlement = rule_pair(bt)
    assert (document.journal.code, document.source, document.source_ref) == ("AC", "RULE", "RULE:E1")
    assert lines(document) == [("401000", 0, 5000), ("606", 5000, 0)]
    assert (settlement.journal.code, settlement.source, settlement.source_ref) == ("BQ", "OFX_IMPORT", "FITID:E1")
    assert lines(settlement) == [("401000", 5000, 0), ("512", 0, 5000)]
    assert bt.reconciled and bt.journal_line.account.code == "512"
    supplier = Account.query.filter_by(code="401000").one()
    assert supplier.lettrable and supplier.parent.code == "401"
    tiers = [l for e in (document, settlement) for l in e.lines if l.account_id == supplier.id]
    assert tiers[0].lettering_id is not None and tiers[0].lettering_id == tiers[1].lettering_id


def test_income_rule_goes_through_default_customer(books):
    bt = txn(books, 80000, "VIR LOYER MARS", "I1")
    apply_rules([bt])
    document, settlement = rule_pair(bt)
    assert document.journal.code == "VE"
    assert lines(document) == [("411000", 80000, 0), ("706", 0, 80000)]
    assert lines(settlement) == [("411000", 0, 80000), ("512", 80000, 0)]


def test_rule_entity_with_account_is_used(books):
    db.session.add(Entity(name="EDF", entity_type="FOURNISSEUR", account_code="401007"))
    db.session.add(Account(code="401007", label="EDF", account_type="TIERS", lettrable=True))
    Rule.query.filter_by(name="EDF").one().entity_name = "EDF"
    db.session.commit()
    bt = txn(books, -5000, "PRLV EDF", "E1")
    apply_rules([bt])
    assert lines(rule_pair(bt)[1]) == [("401007", 5000, 0), ("512", 0, 5000)]


def test_simple_bookkeeping_posts_directly(books):
    g.current_instance = SimpleNamespace(bookkeeping="simple")
    try:
        bt = txn(books, -5000, "PRLV EDF", "E1")
        assert len(apply_rules([bt])["created_entry_ids"]) == 1
    finally:
        del g.current_instance
    assert rule_entries.document_of(bt) is None
    assert lines(bt.journal_line.entry) == [("512", 0, 5000), ("606", 5000, 0)]


def test_assign_draft_entries_to_real_supplier(books):
    bt = txn(books, -5000, "PRLV EDF", "E1")
    apply_rules([bt])
    edf = Entity(name="EDF", entity_type="FOURNISSEUR")
    db.session.add(edf)
    db.session.commit()
    document, settlement = rule_entries.assign(bt, edf)
    db.session.commit()
    assert JournalEntry.query.count() == 2 and not list(reversed_entry_ids())  # brouillard : remplacées
    assert edf.account_code == "401001" and bt.entity_id == edf.id
    assert lines(document) == [("401001", 0, 5000), ("606", 5000, 0)]
    assert lines(settlement) == [("401001", 5000, 0), ("512", 0, 5000)]
    assert bt.journal_line.entry_id == settlement.id


def test_assign_validated_entries_reverses_them(books):
    bt = txn(books, -5000, "PRLV EDF", "E1")
    apply_rules([bt])
    old_document, old_settlement = rule_pair(bt)
    validation.assign([old_document, old_settlement], datetime(2026, 3, 31))
    db.session.commit()
    edf = Entity(name="EDF", entity_type="FOURNISSEUR")
    db.session.add(edf)
    document, _settlement = rule_entries.assign(bt, edf)
    db.session.commit()
    reversed_ids = {i for (i,) in reversed_entry_ids()}
    assert {old_document.id, old_settlement.id} <= reversed_ids
    assert rule_entries.document_of(bt).id == document.id  # la pièce contrepassée ne compte plus
    # Nouvelle attribution possible (autre tiers).
    other = Entity(name="Enercoop", entity_type="FOURNISSEUR")
    db.session.add(other)
    rule_entries.assign(bt, other)
    db.session.commit()
    assert lines(rule_entries.document_of(bt))[0][0] == "401002"


def test_assign_refused_without_rule_entries(books):
    bt = txn(books, -5000, "SANS REGLE", "N1")
    with pytest.raises(rule_entries.LedgerError):
        rule_entries.assign(bt, Entity(name="X"))


def test_assign_api_and_flag(books, login_as):
    bt = txn(books, 80000, "VIR LOYER MARS", "I1")
    other = txn(books, -100, "DIVERS", "D1")
    apply_rules([bt, other])
    tenant = Entity(name="Locataire", entity_type="CLIENT")
    db.session.add(tenant)
    db.session.commit()
    client = login_as()
    rows = client.get(f"/api/v1/bank-accounts/{books['ba'].id}/transactions?status=all").get_json()["transactions"]
    assert {r["label"]: r["rule_tiers"] for r in rows} == {"VIR LOYER MARS": True, "DIVERS": False}

    resp = client.post(f"/api/v1/bank-transactions/{bt.id}/entity", json={"entity_id": tenant.id})
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["item"]["entity"] == "Locataire" and body["item"]["rule_tiers"] is True
    assert lines(rule_entries.document_of(bt)) == [("411001", 80000, 0), ("706", 0, 80000)]
    assert client.post(f"/api/v1/bank-transactions/{other.id}/entity",
                       json={"entity_id": tenant.id}).status_code == 422
    assert client.post(f"/api/v1/bank-transactions/{bt.id}/entity", json={"entity_id": 999}).status_code == 422
