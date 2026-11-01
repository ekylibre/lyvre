"""Module Ventes, lot S2 : encaissements (transaction bancaire, saisie), TVA virée à l'encaissement,
rapprochement automatique, remplacement d'une écriture de règle, annulation, relances, tableau de bord."""
from datetime import date, timedelta

import pytest

from app.extensions import db
from app.models import (
    Account, BankAccount, BankTransaction, Entity, FiscalYear, Journal, JournalEntry, Sale, SalePayment,
)
from app.services import external_config, organization
from app.services.ledger import post_entry

API = "/api/v1/sales"
TODAY = date.today()


@pytest.fixture()
def admin(app, login_as):
    client = login_as(role="admin")
    org = organization.get()
    org.address_line1, org.postal_code, org.city, org.siren = "1 rue A", "75001", "Paris", "123456789"
    bank = Account(code="512", label="Banque", account_type="TRESORERIE")
    cash = Account(code="531", label="Caisse", account_type="TRESORERIE")
    db.session.add_all([
        Account(code="411", label="Clients", account_type="TIERS", is_header=True),
        Account(code="4457", label="TVA collectée", account_type="TIERS"),
        Account(code="706", label="Prestations", account_type="PRODUIT"), bank, cash,
        FiscalYear(label="An", start_date=date(TODAY.year, 1, 1), end_date=date(TODAY.year, 12, 31), vat_liable=True,
                   vat_on_receipts=True),
        Entity(name="Client SARL", entity_type="CLIENT", address_line1="2 av X", postal_code="69001", city="Lyon",
               email="compta@client.example"),
        Entity(name="Autre client", entity_type="CLIENT", address_line1="3 av Y", postal_code="69002", city="Lyon"),
        Journal(code="BQ", label="Banque"),
    ])
    db.session.flush()
    db.session.add_all([BankAccount(label="Compte courant", kind="bank", account_id=bank.id),
                        BankAccount(label="Caisse", kind="cash", account_id=cash.id)])
    db.session.commit()
    _vat_number("FR32123456789")
    return client


def _vat_number(vat):
    """TVA du vendeur : mention de la Structure (lot G2)."""
    from app.services import organization
    organization.get().vat_number = vat
    db.session.commit()


def _invoice(admin, amount="1000", client="Client SARL", issue=None, due=None):
    entity = Entity.query.filter_by(name=client).one()
    item = admin.post(API, json={"entity_id": entity.id, "issue_date": (issue or TODAY).isoformat(),
                                 "due_date": due.isoformat() if due else "",
                                 "lines": [{"label": "Conseil", "unit_price": amount, "vat_rate": "20"}]}).get_json()["item"]
    resp = admin.post(f"{API}/{item['id']}/issue")
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["item"]


def _txn(amount_cents, fitid="T1", day=None, entity=None):
    txn = BankTransaction(bank_account_id=BankAccount.query.filter_by(kind="bank").one().id, fitid=fitid,
                          transaction_date=day or TODAY, amount_cents=amount_cents, label=f"VIR {fitid}", source="ofx",
                          entity_id=entity.id if entity else None)
    db.session.add(txn)
    db.session.commit()
    return txn


def _lines(entry_id):
    entry = db.session.get(JournalEntry, entry_id)
    return sorted((l.account.code, l.debit_cents, l.credit_cents) for l in entry.lines)


def test_bank_payment_releases_vat(admin):
    inv = _invoice(admin)
    txn = _txn(120000)
    options = admin.get(f"{API}/{inv['id']}/payment-options").get_json()
    assert options["due_cents"] == 120000 and options["candidates"][0]["id"] == txn.id and options["candidates"][0]["exact"]
    resp = admin.post(f"{API}/match", json={"bank_transaction_id": txn.id,
                                            "allocations": [{"sale_id": inv["id"], "amount_cents": 120000}]})
    assert resp.status_code == 200, resp.get_json()
    item = resp.get_json()["items"][0]
    assert item["status"] == "paid" and item["due_cents"] == 0
    payment = SalePayment.query.one()
    assert _lines(payment.journal_entry_id) == [("411001", 0, 120000), ("44571", 0, 20000), ("44574", 20000, 0),
                                                ("512", 120000, 0)]
    assert db.session.get(BankTransaction, txn.id).reconciled
    # Transaction déjà utilisée : refusée.
    other = _invoice(admin)
    assert admin.post(f"{API}/match", json={"bank_transaction_id": txn.id,
                                            "allocations": [{"sale_id": other["id"], "amount_cents": 120000}]}).status_code == 409


def test_partial_payments_then_paid(admin):
    inv = _invoice(admin)
    cheque = BankAccount.query.filter_by(kind="bank").one()
    resp = admin.post(f"{API}/{inv['id']}/payments", json={"amount": "450", "paid_on": TODAY.isoformat(),
                                                          "bank_account_id": cheque.id, "method": "check"})
    item = resp.get_json()["item"]
    assert item["status"] == "partially_paid" and item["due_cents"] == 75000
    first = SalePayment.query.one()
    assert first.vat_released_cents == 7500  # 20 000 × 450 / 1 200
    cash = BankAccount.query.filter_by(kind="cash").one()
    assert admin.post(f"{API}/{inv['id']}/payments", json={"amount": "800", "bank_account_id": cash.id}).status_code == 422
    item = admin.post(f"{API}/{inv['id']}/payments", json={"amount": "750", "bank_account_id": cash.id,
                                                          "method": "cash"}).get_json()["item"]
    assert item["status"] == "paid"
    last = SalePayment.query.order_by(SalePayment.id.desc()).first()
    assert last.vat_released_cents == 12500 and last.journal_entry.journal.code == "CA"


def test_auto_match_only_unique_candidates(admin):
    a = _invoice(admin, "500")
    _invoice(admin, "700")
    _invoice(admin, "700")
    _txn(60000, "A")
    _txn(84000, "B")
    result = admin.post(f"{API}/auto-match").get_json()["result"]
    assert result["matched"] == 1  # 700 € : deux factures candidates, aucune liée
    assert db.session.get(Sale, a["id"]).status == "paid"


def test_rule_entry_is_replaced(admin):
    inv = _invoice(admin)
    txn = _txn(120000, "R1")
    fy = FiscalYear.query.one()
    bank = Account.query.filter_by(code="512").one()
    entry = post_entry(fy.id, Journal.query.filter_by(code="BQ").one().id, TODAY, "Règle", [
        {"account_id": bank.id, "label": "x", "debit_cents": 120000, "credit_cents": 0},
        {"account_id": Account.query.filter_by(code="706").one().id, "label": "x", "debit_cents": 0, "credit_cents": 120000},
    ], source="OFX_IMPORT", source_ref="FITID:R1", commit=False)
    txn.journal_line_id, txn.reconciled = next(l.id for l in entry.lines if l.account_id == bank.id), True
    db.session.commit()
    rule_id = entry.id
    assert admin.get(f"{API}/{inv['id']}/payment-options").get_json()["candidates"][0]["rule"] is True
    resp = admin.post(f"{API}/match", json={"bank_transaction_id": txn.id,
                                            "allocations": [{"sale_id": inv["id"], "amount_cents": 120000}]})
    assert resp.status_code == 200
    assert JournalEntry.query.filter_by(source_ref="FITID:R1").count() == 0  # écriture de règle supprimée
    assert rule_id and SalePayment.query.one().journal_entry.source == "SALE_PAYMENT"


def test_unlink_and_entry_deletion(admin):
    inv = _invoice(admin)
    txn = _txn(120000)
    admin.post(f"{API}/match", json={"bank_transaction_id": txn.id, "allocations": [{"sale_id": inv["id"], "amount_cents": 120000}]})
    payment = SalePayment.query.one()
    item = admin.delete(f"/api/v1/sale-payments/{payment.id}").get_json()["item"]
    assert item["status"] == "issued" and item["payments"] == []
    assert not db.session.get(BankTransaction, txn.id).reconciled
    # Supprimer l'écriture depuis Écritures défait aussi l'encaissement.
    cash = BankAccount.query.filter_by(kind="cash").one()
    admin.post(f"{API}/{inv['id']}/payments", json={"amount": "1200", "bank_account_id": cash.id})
    entry_id = SalePayment.query.one().journal_entry_id
    assert admin.delete(f"/api/v1/entries/{entry_id}").status_code == 200
    assert SalePayment.query.count() == 0 and db.session.get(Sale, inv["id"]).status == "issued"


def test_refusals(admin):
    inv = _invoice(admin)
    other = _invoice(admin, client="Autre client")
    txn = _txn(240000)
    resp = admin.post(f"{API}/match", json={"bank_transaction_id": txn.id, "allocations": [
        {"sale_id": inv["id"], "amount_cents": 120000}, {"sale_id": other["id"], "amount_cents": 120000}]})
    assert resp.status_code == 422 and "seul client" in resp.get_json()["error"]["message"]
    resp = admin.post(f"{API}/match", json={"bank_transaction_id": txn.id, "allocations": [{"sale_id": inv["id"], "amount_cents": 120000}]})
    assert resp.status_code == 422 and "égale au montant" in resp.get_json()["error"]["message"]
    debit = _txn(-120000, "D")
    assert admin.post(f"{API}/match", json={"bank_transaction_id": debit.id,
                                            "allocations": [{"sale_id": inv["id"], "amount_cents": 120000}]}).status_code == 409


def test_credit_note_reduces_due(admin):
    inv = _invoice(admin)
    cash = BankAccount.query.filter_by(kind="cash").one()
    admin.post(f"{API}/{inv['id']}/payments", json={"amount": "600", "bank_account_id": cash.id})
    note = admin.post(f"{API}/{inv['id']}/credit-note", json={"reason": "Remise"}).get_json()["item"]
    resp = admin.patch(f"{API}/{note['id']}", json={"entity_id": note["client"]["id"], "issue_date": note["issue_date"],
                                                   "lines": [{"label": "Remise", "unit_price": "500", "vat_rate": "20", "account_code": "706"}]})
    assert resp.status_code == 200, resp.get_json()
    assert admin.post(f"{API}/{note['id']}/issue").status_code == 200
    invoice = admin.get(f"{API}/{inv['id']}").get_json()["item"]
    assert invoice["status"] == "paid" and invoice["due_cents"] == 0  # 1 200 − 600 encaissés − 600 d'avoir


def test_reminders(admin, monkeypatch):
    late = _invoice(admin, issue=TODAY - timedelta(days=40), due=TODAY - timedelta(days=10))
    paid = _invoice(admin)
    cash = BankAccount.query.filter_by(kind="cash").one()
    admin.post(f"{API}/{paid['id']}/payments", json={"amount": "1200", "bank_account_id": cash.id})
    assert admin.get(f"{API}?overdue=1").get_json()["items"][0]["id"] == late["id"]
    sent = []

    class FakeSMTP:
        def send_message(self, message):
            sent.append(message)

        def quit(self):
            pass
    from app.services import membership_reminders
    monkeypatch.setattr(membership_reminders, "_open_smtp", lambda settings, timeout=20: FakeSMTP())
    external_config.set_enabled("smtp", True)
    result = admin.post(f"{API}/remind", json={"ids": [late["id"], paid["id"]]}).get_json()["result"]
    assert result["sent"] == 1 and result["skipped"] == 1
    assert sent[0]["Subject"].startswith("Relance : facture n° ")
    body = sent[0].get_body(preferencelist=("html",)).get_content()
    assert "reste impayée" in body and "1 200,00" in body
    sale = db.session.get(Sale, late["id"])
    assert sale.reminder_count == 1 and sale.last_reminder_at is not None and sale.sent_at is None


def test_dashboard_summary(admin):
    _invoice(admin, issue=TODAY - timedelta(days=40), due=TODAY - timedelta(days=10))
    _invoice(admin, "500")
    fy = FiscalYear.query.one()
    sales = admin.get(f"/api/v1/dashboard?fy_id={fy.id}").get_json()["sales"]
    assert sales == {"revenue_cents": 150000, "receivable_cents": 180000, "overdue_count": 1,
                     "overdue_cents": 120000, "has_sales": True}


def test_rule_pair_is_replaced_by_receipt(admin):
    """Règle en partie double (pièce VE + règlement par 411000) : l'encaissement de la facture retire les deux."""
    from app.models import Rule
    from app.services.rules_engine import apply_rules
    inv = _invoice(admin)
    txn = _txn(120000, "R2")
    db.session.add(Rule(position=1, name="Virements", label_contains="VIR", account_code="706"))
    db.session.commit()
    apply_rules([txn])
    assert JournalEntry.query.filter_by(source="RULE", source_ref="RULE:R2").count() == 1
    resp = admin.post(f"{API}/match", json={"bank_transaction_id": txn.id,
                                            "allocations": [{"sale_id": inv["id"], "amount_cents": 120000}]})
    assert resp.status_code == 200, resp.get_json()
    assert JournalEntry.query.filter(JournalEntry.source_ref.in_(["RULE:R2", "FITID:R2"])).count() == 0
    assert SalePayment.query.one().journal_entry.source == "SALE_PAYMENT"


def test_issue_matches_earlier_bank_credit(admin):
    """Relevé avant la facture : à l'émission, le crédit unique de même montant l'encaisse (écriture + rapprochement)."""
    txn = _txn(120000, "EARLY")
    resp = admin.post(API, json={"entity_id": Entity.query.filter_by(name="Client SARL").one().id,
                                 "issue_date": TODAY.isoformat(),
                                 "lines": [{"label": "Conseil", "unit_price": "1000", "vat_rate": "20"}]})
    sale_id = resp.get_json()["item"]["id"]
    body = admin.post(f"{API}/{sale_id}/issue").get_json()
    assert body["item"]["status"] == "paid"
    assert any("encaissée par la transaction" in n["message"] for n in body["notices"])
    payment = SalePayment.query.one()
    assert payment.bank_transaction_id == txn.id and db.session.get(BankTransaction, txn.id).reconciled
    assert ("44571", 0, 20000) in _lines(payment.journal_entry_id)  # TVA virée à l'encaissement


def test_issue_does_not_match_ambiguous_credit(admin):
    """Deux factures ouvertes de même montant : le crédit n'est attribué à aucune à l'émission."""
    first = _invoice(admin, "700")
    _txn(84000, "AMB")
    second = _invoice(admin, "700")
    assert second["status"] == "issued" and SalePayment.query.count() == 0
    assert db.session.get(Sale, first["id"]).status == "issued"


def test_transactions_propose_open_invoices(admin):
    """Banque › Transactions : un crédit libre propose les factures ouvertes de même restant dû ; encaissé, il les montre."""
    inv = _invoice(admin)
    other = _invoice(admin, client="Autre client")
    txn = _txn(120000, "PROP", entity=Entity.query.filter_by(name="Autre client").one())
    _txn(50000, "SMALL")
    ba = BankAccount.query.filter_by(kind="bank").one()
    rows = {t["id"]: t for t in admin.get(f"/api/v1/bank-accounts/{ba.id}/transactions?status=all").get_json()["transactions"]}
    assert [p["id"] for p in rows[txn.id]["sale_proposals"]] == [other["id"], inv["id"]]  # même client d'abord
    assert all(t["sale_proposals"] == [] for i, t in rows.items() if i != txn.id)
    resp = admin.post(f"{API}/match", json={"bank_transaction_id": txn.id,
                                            "allocations": [{"sale_id": other["id"], "amount_cents": 120000}]})
    assert resp.status_code == 200
    row = next(t for t in admin.get(f"/api/v1/bank-accounts/{ba.id}/transactions?status=all").get_json()["transactions"]
               if t["id"] == txn.id)
    assert row["sale_proposals"] == [] and row["invoices"][0]["label"] == f"Facture {other['number']}"
