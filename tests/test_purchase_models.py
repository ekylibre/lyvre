"""Modèles du lot 2a : catalogue, factures d'achat, lignes, paiements, curseurs."""
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    Account, BankAccount, BankTransaction, Entity, FiscalYear, Product, Purchase, PurchaseLine,
    PurchasePayment, SyncCursor,
)
from app.models.sync_cursor import CURSOR_QONTO_SUPPLIER_INVOICES


def _account(code, label="Compte"):
    acc = Account(code=code, label=label, account_type="EXPENSE")
    db.session.add(acc)
    db.session.flush()
    return acc


def _purchase(**kwargs):
    fields = {"qonto_id": "si-1", "supplier_name": "EDF", "total_cents": 12000}
    fields.update(kwargs)
    purchase = Purchase(**fields)
    db.session.add(purchase)
    db.session.flush()
    return purchase


def test_purchase_defaults(session):
    purchase = _purchase()
    db.session.commit()
    db.session.refresh(purchase)
    assert purchase.source == "qonto"
    assert purchase.currency == "EUR"
    assert not purchase.is_credit_note and not purchase.is_hidden and not purchase.lines_edited
    assert purchase.journal_entry_id is None and purchase.created_at and purchase.updated_at


def test_qonto_id_unique_but_manual_invoices_have_none(session):
    _purchase()
    _purchase(qonto_id=None, source="manual")
    _purchase(qonto_id=None, source="manual")
    db.session.commit()
    with pytest.raises(IntegrityError):
        _purchase()
    db.session.rollback()


def test_lines_ordered_and_deleted_with_purchase(session):
    acc = _account("6061", "Fournitures non stockables")
    product = Product(name="Électricité", kind="purchase", purchase_account_id=acc.id,
                      vat_rate_bp=2000)
    purchase = _purchase()
    purchase.lines = [
        PurchaseLine(position=2, label="b", account_id=acc.id, untaxed_cents=100, total_cents=100),
        PurchaseLine(position=1, label="a", product=product, account_id=acc.id,
                     untaxed_cents=10000, vat_rate_bp=2000, vat_cents=2000, total_cents=12000),
    ]
    db.session.commit()
    db.session.expire_all()
    purchase = db.session.get(Purchase, purchase.id)
    assert [line.label for line in purchase.lines] == ["a", "b"]
    assert purchase.lines[0].product.purchase_account.code == "6061"

    db.session.delete(purchase)
    db.session.commit()
    assert PurchaseLine.query.count() == 0
    assert Product.query.count() == 1  # le catalogue n'est pas touché


def test_payment_ref_unique_per_purchase(session):
    purchase = _purchase()
    other = _purchase(qonto_id="si-2")
    db.session.add_all([
        PurchasePayment(purchase=purchase, qonto_transaction_id="tx-1"),
        PurchasePayment(purchase=other, qonto_transaction_id="tx-1"),
    ])
    db.session.commit()
    db.session.add(PurchasePayment(purchase=purchase, qonto_transaction_id="tx-1"))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_payment_links_bank_transaction(session):
    acc = _account("5121", "Banque")
    bank = BankAccount(label="Qonto", account_id=acc.id)
    db.session.add(bank)
    db.session.flush()
    txn = BankTransaction(bank_account_id=bank.id, fitid="uuid-1", source="qonto",
                          transaction_date=date(2026, 10, 2), amount_cents=-12000)
    purchase = _purchase()
    purchase.payments.append(PurchasePayment(qonto_transaction_id="uuid-1",
                                             bank_transaction=txn))
    db.session.commit()
    assert purchase.payments[0].bank_transaction.fitid == "uuid-1"


def test_payment_outside_qonto(session):
    acc = _account("5121", "Banque")
    bank = BankAccount(label="Crédit Coopératif", account_id=acc.id)
    db.session.add(bank)
    db.session.flush()
    txn = BankTransaction(bank_account_id=bank.id, fitid="OFX-1", source="ofx",
                          transaction_date=date(2026, 10, 2), amount_cents=-12000)
    purchase = _purchase(qonto_id=None, source="manual")
    purchase.payments.append(PurchasePayment(bank_transaction=txn, origin="match"))
    db.session.commit()
    payment = purchase.payments[0]
    assert payment.qonto_transaction_id is None and payment.origin == "match"
    # Une même transaction ne paie qu'une fois la même facture.
    db.session.add(PurchasePayment(purchase=purchase, bank_transaction=txn, origin="manual"))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_payment_origin_defaults_to_qonto(session):
    purchase = _purchase()
    purchase.payments.append(PurchasePayment(qonto_transaction_id="tx-1"))
    db.session.commit()
    assert purchase.payments[0].origin == "qonto"


def test_manual_purchase_attachment_and_upload_fields(session):
    purchase = _purchase(qonto_id=None, source="manual", supplier_siret="12345678900011",
                         attachment_path="achats/2026/10/1-facture.pdf",
                         attachment_name="Facture.pdf", attachment_mime="application/pdf",
                         attachment_size=2048, idempotency_key="0b6c3e1e-2f4c-4f43-9f6c-1d0c0b6f2a11",
                         qonto_upload_status="failed", qonto_upload_error="Fichier refusé")
    db.session.commit()
    db.session.expire_all()
    purchase = db.session.get(Purchase, purchase.id)
    assert purchase.attachment_size == 2048 and purchase.qonto_upload_status == "failed"


def test_entity_supplier_fields_and_purchases(session):
    acc = _account("6068")
    product = Product(name="Achats divers", kind="purchase", purchase_account_id=acc.id)
    entity = Entity(name="EDF", entity_type="FOURNISSEUR", account_code="401010",
                    default_product=product, qonto_supplier_id="sup-1",
                    vat_number="FR03552081317", siret="55208131766522",
                    iban="FR7630004000031234567890143")
    db.session.add(entity)
    db.session.flush()
    _purchase(entity_id=entity.id)
    db.session.commit()
    assert entity.default_product.name == "Achats divers"
    assert entity.purchases.count() == 1


def test_fiscal_year_not_vat_liable_by_default(session):
    fy = FiscalYear(label="2027", start_date=date(2027, 1, 1), end_date=date(2027, 12, 31))
    db.session.add(fy)
    db.session.commit()
    assert fy.vat_liable is False


def test_sync_cursor_key_unique(session):
    db.session.add(SyncCursor(key=CURSOR_QONTO_SUPPLIER_INVOICES, sync_from=date(2026, 1, 1)))
    db.session.commit()
    db.session.add(SyncCursor(key=CURSOR_QONTO_SUPPLIER_INVOICES))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()
