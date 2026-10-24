"""Règlements des factures d'achat : lien facture ↔ transaction, 401 / banque, remplacement."""
import json
from datetime import date

import pytest

from app.extensions import db
from app.models import (
    Account, BankAccount, BankTransaction, Entity, FiscalYear, Journal, JournalEntry, Purchase,
    PurchasePayment, Rule, SyncCursor,
)
from app.services import purchase_posting, purchase_settlement, purchase_sync, qonto_sync
from app.services.ledger import delete_entries
from test_purchase_sync import FakeClient as InvoiceClient, inv
from test_qonto_sync import FakeClient as TransactionClient, tx

TX_UUID = "01a11ab8-5cd3-7be0-ab2f-860a53a581ec"


@pytest.fixture()
def books(app):
    accounts = {c: Account(code=c, label=f"Compte {c}", account_type="EXPENSE")
                for c in ("401", "512", "6061", "6068", "613")}
    db.session.add_all([*accounts.values(),
                        FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)),
                        Journal(code="AC", label="Achats"), Journal(code="BQ", label="Banque"),
                        Entity(name="DUPRE", entity_type="FOURNISSEUR"),
                        SyncCursor(key="qonto_supplier_invoices", sync_from=date(2026, 7, 1))])
    db.session.commit()
    ba = BankAccount(label="Qonto", account_id=accounts["512"].id, qonto_account_id="acc-1",
                     qonto_sync_from=date(2026, 7, 1))
    db.session.add(ba)
    db.session.commit()
    return {"ba": ba, **accounts}


def invoice(**extra):
    """Facture Dupré de 271,77 € payée par la transaction TX_UUID."""
    fields = {"total": "271.77", "untaxed": "247.06", "tax": "24.71", "taxes": (("10", "24.71"),),
              "supplier": "DUPRE", "created_at": "2026-10-08T08:51:00Z",
              "matched_transactions": [{"subject_type": "transfer", "transaction_id": TX_UUID}]}
    fields.update(extra)
    return inv("si-1", **fields)


def payment(**extra):
    extra.setdefault("clean_counterparty_name", "DUPRE")
    return tx(TX_UUID, 27177, "debit", settled_at="2026-10-08T09:00:00Z", label="DUPRE MAINTENANCE",
              **extra)


def sync_invoices(*invoices):
    return purchase_sync.sync_supplier_invoices(client=InvoiceClient(invoices))


def sync_transactions(books, *transactions):
    return qonto_sync.sync_bank_account(books["ba"].id, client=TransactionClient(transactions))


def entry_lines(entry):
    return sorted((l.account.code, l.debit_cents, l.credit_cents) for l in entry.lines)


def _txn():
    return BankTransaction.query.filter_by(fitid=TX_UUID).one()


# ------------------------------------------------------------------ ordre d'arrivée

def test_transaction_first_then_invoice(books):
    sync_transactions(books, payment())
    txn = _txn()
    assert not txn.reconciled

    result = sync_invoices(invoice())
    assert result["posted"] == 1 and result["settled"] == 1
    db.session.refresh(txn)
    assert txn.reconciled and txn.entity.name == "DUPRE"
    settlement = txn.journal_line.entry
    assert settlement.journal.code == "BQ" and settlement.source_ref == f"PURCHASE_PAYMENT:{TX_UUID}"
    assert entry_lines(settlement) == [("401001", 27177, 0), ("512", 0, 27177)]
    (pay,) = Purchase.query.one().payments
    assert pay.bank_transaction_id == txn.id and pay.journal_entry_id == settlement.id


def test_invoice_first_then_transaction_skips_rules(books):
    db.session.add(Rule(position=1, name="Maintenance", label_contains="DUPRE", account_code="613"))
    db.session.commit()
    sync_invoices(invoice())
    (pay,) = Purchase.query.one().payments
    assert pay.bank_transaction_id is None  # pas encore importée

    result = sync_transactions(books, payment())
    assert result["settled"] == 1 and result["rules_posted"] == 0
    txn = _txn()
    assert entry_lines(txn.journal_line.entry) == [("401001", 27177, 0), ("512", 0, 27177)]
    assert JournalEntry.query.count() == 2  # achat + règlement, pas d'écriture de règle


def test_unposted_invoice_waits_and_rules_still_skip(books):
    db.session.add(Rule(position=1, name="Maintenance", label_contains="DUPRE", account_code="613"))
    db.session.commit()
    sync_invoices(invoice(supplier="Inconnu SARL"))  # fournisseur non rattaché : à compléter
    sync_transactions(books, payment())
    txn = _txn()
    assert not txn.reconciled and txn.journal_line_id is None
    assert purchase_settlement.linked_transaction_ids([txn.id]) == {txn.id}

    p = Purchase.query.one()
    p.entity = Entity.query.filter_by(name="DUPRE").one()
    db.session.commit()
    outcome = purchase_posting.post_ready([p])
    assert outcome["posted"] == 1 and outcome["settled"] == 1
    assert _txn().reconciled


def test_credit_note_refund_debits_bank(books):
    refund = tx(TX_UUID, 5000, "credit", settled_at="2026-10-08T09:00:00Z", label="DUPRE avoir")
    sync_transactions(books, refund)
    sync_invoices(invoice(total="-50.00", untaxed="-45.45", tax="-4.55", taxes=(("10", "-4.55"),),
                          is_credit_note=True))
    assert entry_lines(_txn().journal_line.entry) == [("401001", 0, 5000), ("512", 5000, 0)]


def test_reversed_transaction_not_settled(books):
    sync_transactions(books, payment())
    _txn().is_reversed = True
    db.session.commit()
    result = sync_invoices(invoice())
    assert result["posted"] == 1 and result["settled"] == 0
    assert not _txn().reconciled


def test_one_transaction_for_two_suppliers_is_reported(books):
    db.session.add(Entity(name="EDF", entity_type="FOURNISSEUR"))
    db.session.commit()
    sync_transactions(books, payment())
    edf = {"id": "sup-EDF", "name": "EDF", "vat_number": "FR03552081317", "iban": None}
    result = sync_invoices(invoice(), inv("si-2", supplier="EDF", total="10.00", untaxed=None,
                                          tax=None, taxes=(), created_at="2026-10-08T08:52:00Z",
                                          supplier_snapshot=edf,
                                          matched_transactions=[{"transaction_id": TX_UUID}]))
    assert result["settled"] == 0
    assert any("fournisseurs différents" in e for e in result["errors"])


def test_posted_invoice_settled_when_link_appears_later(books):
    sync_transactions(books, payment())
    sync_invoices(invoice(matched_transactions=[]))  # comptabilisée, paiement pas encore lié
    assert not _txn().reconciled
    later = invoice(updated_at=purchase_sync.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ"))
    result = sync_invoices(later)
    assert result["settled"] == 1 and _txn().reconciled


# ------------------------------------------------------------------ liens

def test_link_invoice_follows_qonto(books):
    sync_invoices(invoice())
    p = Purchase.query.one()
    payload = json.loads(p.raw_payload)
    payload["matched_transactions"] = [{"transaction_id": "other-uuid"}]
    p.raw_payload = json.dumps(payload)
    purchase_settlement.link_invoice(p)
    assert [pay.qonto_transaction_id for pay in p.payments] == ["other-uuid"]


def test_unlinked_settled_payment_is_flagged(books):
    sync_transactions(books, payment())
    sync_invoices(invoice())
    p = Purchase.query.one()
    p.raw_payload = json.dumps({**json.loads(p.raw_payload), "matched_transactions": []})
    purchase_settlement.link_invoice(p)
    assert len(p.payments) == 1 and "ne rattache plus" in p.review_reason


def test_deleting_entries_releases_purchase_and_payment(books):
    sync_transactions(books, payment())
    sync_invoices(invoice())
    p = Purchase.query.one()
    (pay,) = p.payments
    delete_entries([pay.journal_entry_id, p.journal_entry_id])
    db.session.refresh(p)
    db.session.refresh(pay)
    assert p.journal_entry_id is None and pay.journal_entry_id is None
    assert not _txn().reconciled


# ------------------------------------------------------------------ remplacement

def test_rule_entry_replaced_by_settlement(books):
    db.session.add(Rule(position=1, name="Maintenance", label_contains="DUPRE", account_code="613"))
    db.session.commit()
    sync_transactions(books, payment())
    rule_entry = _txn().journal_line.entry
    assert entry_lines(rule_entry) == [("512", 0, 27177), ("613", 27177, 0)]

    sync_invoices(invoice())  # facture comptabilisée, transaction déjà rapprochée par la règle
    (row,) = purchase_settlement.to_replace()
    assert row.replaceable and row.entry.id == rule_entry.id

    outcome = purchase_settlement.replace_many([row.transaction.id])
    assert outcome["counters"] == {"ok": 1, "error": 0}
    assert db.session.get(JournalEntry, rule_entry.id) is None
    assert entry_lines(_txn().journal_line.entry) == [("401001", 27177, 0), ("512", 0, 27177)]
    assert purchase_settlement.to_replace() == []


def test_manual_reconciliation_only_reported(books):
    from app.services.ledger import post_entry
    from app.services.reconciler import reconcile
    sync_transactions(books, payment())
    txn = _txn()
    fy = FiscalYear.query.one()
    entry = post_entry(fy.id, Journal.query.filter_by(code="BQ").one().id, date(2026, 10, 8),
                       "Saisie manuelle", [
                           {"account_id": books["6068"].id, "debit_cents": 27177},
                           {"account_id": books["512"].id, "credit_cents": 27177}])
    reconcile(txn.id, next(l.id for l in entry.lines if l.account_id == books["512"].id))
    sync_invoices(invoice())
    (row,) = purchase_settlement.to_replace()
    assert not row.replaceable
    outcome = purchase_settlement.replace_many([txn.id])
    assert outcome["counters"]["error"] == 1
    assert db.session.get(JournalEntry, entry.id) is not None


def test_settlements_views(books, login_as):
    db.session.add(Rule(position=1, name="Maintenance", label_contains="DUPRE", account_code="613"))
    db.session.commit()
    sync_transactions(books, payment())
    sync_invoices(invoice())
    client = login_as()
    assert client.get("/api/v1/purchases").get_json()["meta"]["counters"]["to_replace"] == 1
    body = client.get("/api/v1/purchases/settlements").get_json()
    assert [r["transaction"]["label"] for r in body["replaceable"]] == ["DUPRE MAINTENANCE"]
    detail = client.get(f"/api/v1/purchases/{Purchase.query.one().id}").get_json()
    assert [p["status_label"] for p in detail["payments"]] == ["Passée par une autre écriture"]

    resp = client.post("/api/v1/purchases/settlements/replace", json={"transaction_ids": [_txn().id]})
    assert "1 écriture(s) de règle remplacée(s)" in resp.get_json()["notices"][0]["message"]
    assert client.get("/api/v1/purchases/settlements").get_json() == {"replaceable": [], "manual": []}
    detail = client.get(f"/api/v1/purchases/{Purchase.query.one().id}").get_json()
    assert [p["status_label"] for p in detail["payments"]] == ["Réglée"]


def test_settlement_letters_supplier_account(books):
    """Lot F3 : facture d'achat et règlement lettrés sur le 401 du fournisseur, délettrés si défait."""
    from app.models import Lettering
    sync_transactions(books, payment())
    sync_invoices(invoice())
    item = Lettering.query.one()
    assert item.origin == "document" and item.document_type == "purchase" and not item.partial
    assert sorted((l.account.code, l.debit_cents, l.credit_cents) for l in item.lines) == [
        ("401001", 0, 27177), ("401001", 27177, 0)]
    settlement = _txn().journal_line.entry
    delete_entries([settlement.id])
    assert Lettering.query.count() == 0
