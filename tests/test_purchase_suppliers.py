"""Fournisseurs des factures à valider, factures visibles depuis le compte bancaire."""
from app.extensions import db
from app.models import BankTransaction, Entity, IgnoredCounterparty, Purchase
from app.services import counterparties
from test_purchase_settlement import (  # noqa: F401 (fixture)
    books, invoice, payment, sync_invoices, sync_transactions, TX_UUID,
)

PAPIN = {"id": "sup-papin", "name": "SARL PAPIN", "vat_number": "FR55123456789",
         "iban": "FR7630004000039999999999999"}


def papin_invoice():
    return invoice(supplier="SARL PAPIN", supplier_snapshot=PAPIN)


def test_invoice_proposals_grouped_by_name(books):
    sync_invoices(papin_invoice())
    (proposal,) = counterparties.invoice_proposals()
    assert (proposal.key, proposal.label, proposal.count, proposal.total_cents) == \
        ("sarl papin", "SARL PAPIN", 1, 27177)
    assert proposal.vat_number == "FR55123456789" and proposal.iban == PAPIN["iban"]


def test_accept_creates_supplier_posts_and_settles(books):
    sync_transactions(books, payment(clean_counterparty_name="SARL PAPIN"))
    sync_invoices(papin_invoice())
    purchase = Purchase.query.one()
    assert purchase.entity is None and purchase.journal_entry_id is None

    entity, n_txn, n_inv = counterparties.accept("sarl papin", create_name="SARL Papin")
    assert (entity.entity_type, n_txn, n_inv) == ("FOURNISSEUR", 1, 1)
    assert entity.vat_number == "FR55123456789" and entity.qonto_supplier_id == "sup-papin"
    db.session.refresh(purchase)
    assert purchase.entity == entity and purchase.journal_entry_id is not None
    txn = BankTransaction.query.filter_by(fitid=TX_UUID).one()
    assert txn.reconciled and txn.entity == entity
    assert counterparties.invoice_proposals() == []


def test_next_invoice_recognised_by_qonto_id(books):
    sync_invoices(papin_invoice())
    counterparties.accept("sarl papin", create_name="Papin (renommé)")
    later = invoice(supplier="SARL PAPIN", supplier_snapshot=PAPIN)
    later["id"] = "si-2"
    later["created_at"] = "2026-10-09T08:00:00Z"
    later["matched_transactions"] = []
    sync_invoices(papin_invoice(), later)
    assert {p.entity.name for p in Purchase.query.all()} == {"Papin (renommé)"}


def test_ignored_supplier_not_proposed(books):
    sync_invoices(papin_invoice())
    counterparties.ignore("sarl papin", "SARL PAPIN")
    assert counterparties.invoice_proposals() == []
    assert IgnoredCounterparty.query.count() == 1


def test_supplier_recognised_by_iban(books):
    other = Entity(name="Établissements Papin", entity_type="FOURNISSEUR", iban=PAPIN["iban"])
    db.session.add(other)
    db.session.commit()
    sync_invoices(papin_invoice())
    # L'IBAN reconnaît le fournisseur (D5 du lot 2b) : rien à valider.
    assert counterparties.invoice_proposals() == []
    assert Purchase.query.one().entity == other


def test_suppliers_page(books, login_as):
    sync_invoices(papin_invoice())
    client = login_as()
    assert client.get("/api/v1/purchases").get_json()["meta"]["counters"]["supplier_proposals"] == 1
    (row,) = client.get("/api/v1/purchases/suppliers").get_json()["items"]
    assert row["label"] == "SARL PAPIN" and row["vat_number"] == "FR55123456789"
    client.post("/api/v1/purchases/suppliers", json={"action": "create", "key": row["key"],
                                                     "label": "SARL PAPIN", "name": "SARL Papin"})
    assert Purchase.query.one().entity.name == "SARL Papin"
    assert client.get("/api/v1/purchases/suppliers").get_json()["items"] == []


def test_bank_view_invoice_badge_and_filter(books, login_as):
    sync_transactions(books, payment(), payment_other())
    sync_invoices(invoice())
    client = login_as()
    url = f"/api/v1/bank-accounts/{books['ba'].id}/transactions?status=all"
    rows = client.get(url).get_json()["transactions"]
    assert ["Facture FAC-si-1"] in [[i["label"] for i in r["invoices"]] for r in rows]
    filtered = client.get(url + "&no_invoice=1").get_json()["transactions"]
    assert [r["label"] for r in filtered] == ["Fournitures diverses"]


def payment_other():
    from test_qonto_sync import tx
    return tx("other-uuid", 1500, "debit", settled_at="2026-10-09T09:00:00Z",
              label="Fournitures diverses", clean_counterparty_name="Bureau Vallée")
