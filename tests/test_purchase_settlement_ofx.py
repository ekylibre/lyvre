"""Règlement des factures saisies depuis un compte hors Qonto (OFX) : candidats, lien auto, choix."""
import io
from datetime import date

import pytest

from app.extensions import db
from app.models import (
    Account, BankAccount, BankTransaction, Entity, FiscalYear, Journal, Purchase, PurchaseLine,
    PurchasePayment,
)
from app.services import purchase_posting, purchase_settlement as ps
from app.services.ledger import LedgerError, post_entry
from app.services.reconciler import reconcile


@pytest.fixture()
def books(app):
    accounts = {code: Account(code=code, label=f"Compte {code}", account_type="EXPENSE")
                for code in ("401", "512", "5121", "6061")}
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    db.session.add_all([*accounts.values(), fy, Journal(code="AC", label="Achats"),
                        Journal(code="BQ", label="Banque")])
    db.session.flush()
    bank = BankAccount(label="Crédit Coopératif", account_id=accounts["512"].id)
    qonto = BankAccount(label="Qonto", account_id=accounts["5121"].id, qonto_account_id="qa-1")
    db.session.add_all([bank, qonto])
    db.session.commit()
    return {"fy": fy, "bank": bank, "qonto": qonto, **accounts}


def txn(books, day, amount=-3999, fitid=None, bank=None, **extra):
    t = BankTransaction(bank_account_id=(bank or books["bank"]).id,
                        fitid=fitid or f"OFX-{BankTransaction.query.count() + 1}",
                        transaction_date=day, amount_cents=amount, label="PRLV FREE", **extra)
    db.session.add(t)
    db.session.commit()
    return t


def invoice(books, number="F-1", total=3999, day=date(2026, 9, 2), due=date(2026, 9, 4),
            supplier="Free", post=True, **extra):
    entity = Entity.query.filter_by(name=supplier).first() or Entity(name=supplier)
    p = Purchase(source="manual", invoice_number=number, issue_date=day, due_date=due,
                 total_cents=total, entity=entity, lines_edited=True, **extra)
    p.lines = [PurchaseLine(position=0, account=books["6061"], untaxed_cents=total, vat_rate_bp=0,
                            vat_cents=0, total_cents=total)]
    db.session.add(p)
    db.session.commit()
    if post:
        purchase_posting.post(p)
        db.session.commit()
    return p


def lines(entry):
    return sorted((l.account.code, l.debit_cents, l.credit_cents) for l in entry.lines)


# ------------------------------------------------------------------ candidats

def test_candidates_window_amount_and_bank(books):
    p = invoice(books, post=False)
    good = txn(books, date(2026, 9, 4))
    txn(books, date(2026, 8, 27))                       # avant date − 5 j
    txn(books, date(2026, 11, 4))                       # après échéance + 60 j
    txn(books, date(2026, 9, 5), amount=-4000)          # autre montant
    txn(books, date(2026, 9, 5), bank=books["qonto"])   # compte Qonto : désigné par Qonto
    txn(books, date(2026, 9, 6), is_reversed=True)      # annulée
    late = txn(books, date(2026, 11, 3))                # dernier jour de la fenêtre
    assert ps.match_window(p) == (date(2026, 8, 28), date(2026, 11, 3))
    assert ps.match_candidates(p) == [good, late]


def test_candidates_prefer_same_supplier_then_nearest_date(books):
    p = invoice(books, post=False)
    near = txn(books, date(2026, 9, 5))
    same = txn(books, date(2026, 10, 20), entity_id=p.entity_id)
    assert ps.match_candidates(p) == [same, near]


def test_credit_note_matches_a_credit(books):
    p = invoice(books, is_credit_note=True, post=False)
    txn(books, date(2026, 9, 5))
    refund = txn(books, date(2026, 9, 6), amount=3999)
    assert ps.match_candidates(p) == [refund]


# ------------------------------------------------------------------ lien automatique

def test_posting_links_and_settles_unique_debit(books):
    t = txn(books, date(2026, 9, 4))
    p = invoice(books, post=False)
    outcome = purchase_posting.post_ready([p])
    assert outcome["posted"] == 1 and outcome["settled"] == 1
    (payment,) = p.payments
    assert payment.origin == "match" and payment.qonto_transaction_id is None
    assert lines(payment.journal_entry) == [("401001", 3999, 0), ("512", 0, 3999)]
    assert t.reconciled and t.journal_line.entry == payment.journal_entry and t.entity_id == p.entity_id
    assert payment.journal_entry.source == "OFX_IMPORT"


def test_ambiguous_debits_are_not_linked(books):
    txn(books, date(2026, 9, 4))
    txn(books, date(2026, 9, 10))
    p = invoice(books)
    assert ps.auto_match() == {"matched": 0, "settled": 0, "errors": []}
    assert p.payments == [] and len(ps.match_candidates(p)) == 2


def test_debit_shared_by_two_invoices_is_not_linked(books):
    a = invoice(books, number="F-1")
    b = invoice(books, number="F-2", supplier="Orange")
    txn(books, date(2026, 9, 4))
    assert ps.auto_match()["matched"] == 0 and not a.payments and not b.payments


def test_import_later_links_pending_invoice(books):
    p = invoice(books)
    assert ps.auto_match()["matched"] == 0
    txn(books, date(2026, 9, 5))
    assert ps.auto_match() == {"matched": 1, "settled": 1, "errors": []}
    assert p.payments[0].journal_entry is not None
    assert ps.auto_match()["matched"] == 0  # déjà réglée


def test_qonto_invoices_and_unposted_ignored(books):
    qonto = invoice(books, number="Q-1", post=False)
    qonto.source, qonto.qonto_id = "qonto", "si-1"
    purchase_posting.post(qonto)
    invoice(books, number="F-2", supplier="Orange", post=False)
    db.session.commit()
    txn(books, date(2026, 9, 4))
    assert ps.auto_match()["matched"] == 0


def test_rule_entry_linked_then_to_replace(books):
    t = txn(books, date(2026, 9, 4))
    entry = post_entry(fiscal_year_id=books["fy"].id, journal_id=Journal.query.filter_by(code="BQ").one().id,
                       entry_date=t.transaction_date, description="Règle Free",
                       lines=[{"account_id": books["6061"].id, "label": "Free", "debit_cents": 3999, "credit_cents": 0},
                              {"account_id": books["512"].id, "label": "Free", "debit_cents": 0, "credit_cents": 3999}],
                       source="OFX_IMPORT", source_ref=f"FITID:{t.fitid}", commit=False)
    reconcile(t.id, next(l.id for l in entry.lines if l.account_id == books["512"].id), commit=False)
    db.session.commit()
    p = invoice(books)
    assert ps.auto_match() == {"matched": 1, "settled": 0, "errors": []}
    (row,) = ps.to_replace()
    assert row.replaceable and row.purchases == [p]
    assert ps.replace_many([t.id])["counters"]["ok"] == 1
    assert p.payments[0].journal_entry is not None


def test_manually_reconciled_debit_not_offered(books):
    t = txn(books, date(2026, 9, 4))
    entry = post_entry(fiscal_year_id=books["fy"].id, journal_id=Journal.query.filter_by(code="BQ").one().id,
                       entry_date=t.transaction_date, description="Saisie",
                       lines=[{"account_id": books["6061"].id, "label": "x", "debit_cents": 3999, "credit_cents": 0},
                              {"account_id": books["512"].id, "label": "x", "debit_cents": 0, "credit_cents": 3999}],
                       commit=False)
    reconcile(t.id, next(l.id for l in entry.lines if l.account_id == books["512"].id), commit=False)
    db.session.commit()
    assert ps.match_candidates(invoice(books)) == []


# ------------------------------------------------------------------ choix, annulation

def test_link_manual_then_unlink(books):
    first = txn(books, date(2026, 9, 4))
    second = txn(books, date(2026, 9, 10))
    p = invoice(books)
    assert ps.link_manual(p, second.id)["settled"] == 1
    payment = p.payments[0]
    assert payment.origin == "manual" and second.reconciled and not first.reconciled
    with pytest.raises(LedgerError, match="n'attend pas"):
        ps.link_manual(p, first.id)

    ps.unlink(payment)
    db.session.refresh(second)
    assert p.payments == [] and not second.reconciled and second.journal_line_id is None
    assert PurchasePayment.query.count() == 0
    # Le règlement a rattaché le fournisseur à la transaction : elle reste proposée en premier.
    assert ps.match_candidates(p) == [second, first]


def test_link_manual_refuses_foreign_transaction(books):
    other = txn(books, date(2026, 9, 4), amount=-100)
    with pytest.raises(LedgerError, match="ne peut pas"):
        ps.link_manual(invoice(books), other.id)


def test_qonto_payment_cannot_be_unlinked(books):
    p = invoice(books)
    payment = PurchasePayment(purchase=p, qonto_transaction_id="tx-1")
    db.session.add(payment)
    db.session.commit()
    with pytest.raises(LedgerError, match="Qonto"):
        ps.unlink(payment)


# ------------------------------------------------------------------ écrans

OFX = """OFXHEADER:100
DATA:OFXSGML
VERSION:102
SECURITY:NONE
ENCODING:USASCII
CHARSET:1252
COMPRESSION:NONE
OLDFILEUID:NONE
NEWFILEUID:NONE

<OFX><SIGNONMSGSRSV1><SONRS><STATUS><CODE>0<SEVERITY>INFO</STATUS><DTSERVER>20260930<LANGUAGE>FRA</SONRS></SIGNONMSGSRSV1>
<BANKMSGSRSV1><STMTTRNRS><TRNUID>1<STATUS><CODE>0<SEVERITY>INFO</STATUS>
<STMTRS><CURDEF>EUR<BANKACCTFROM><BANKID>42559<ACCTID>0001<ACCTTYPE>CHECKING</BANKACCTFROM>
<BANKTRANLIST><DTSTART>20260901<DTEND>20260930
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260904<TRNAMT>-39.99<FITID>FREE0904<NAME>PRLV SEPA FREE</STMTTRN>
</BANKTRANLIST><LEDGERBAL><BALAMT>100.00<DTASOF>20260930</LEDGERBAL></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>
"""


def test_ofx_import_settles_pending_invoice(books, login_as):
    p = invoice(books)
    client = login_as()
    body = client.post("/api/v1/imports/ofx", data={"bank_account_id": str(books["bank"].id),
                                                     "ofx_file": (io.BytesIO(OFX.encode()), "releve.ofx")},
                       content_type="multipart/form-data").get_json()
    messages = [n["message"] for n in body["notices"]]
    assert "1 transaction(s) importée(s), 0 doublon(s) ignoré(s)." in messages
    assert "1 facture(s) d'achat rattachée(s) à leur paiement, 1 règlement(s) passé(s)." in messages
    assert body["result"]["settled"] == 1
    db.session.expire_all()
    assert Purchase.query.get(p.id).payments[0].journal_entry is not None


def _api(path=""):
    return f"/api/v1/purchases{path}"


def _numbers(client, qs):
    return [r["invoice_number"] for r in client.get(_api(f"?{qs}")).get_json()["items"]]


def _notices(resp):
    return " ".join(n["message"] for n in resp.get_json().get("notices", [])) or resp.get_json()["error"]["message"]


def test_detail_suggestions_link_and_undo(books, login_as):
    first = txn(books, date(2026, 9, 4))
    txn(books, date(2026, 9, 10))
    p = invoice(books)
    client = login_as()
    assert len(client.get(_api(f"/{p.id}")).get_json()["suggestions"]) == 2
    client.post(_api(f"/{p.id}/payments"), json={"bank_transaction_id": first.id})
    db.session.expire_all()
    p = db.session.get(Purchase, p.id)
    assert p.payments[0].origin == "manual" and p.payments[0].journal_entry is not None
    body = client.get(_api(f"/{p.id}")).get_json()
    assert [x["status_label"] for x in body["payments"]] == ["Réglée"] and body["suggestions"] == []
    assert "F-1" not in _numbers(client, "unpaid=1")

    client.delete(_api(f"/{p.id}/payments/{p.payments[0].id}"))
    db.session.expire_all()
    assert db.session.get(Purchase, p.id).payments == []
    assert "F-1" in _numbers(client, "unpaid=1")


def test_detail_without_candidate(books, login_as):
    p = invoice(books)
    body = login_as().get(_api(f"/{p.id}")).get_json()
    assert body["suggestions"] == [] and body["awaiting_payment"] and body["match_window"][0] == "2026-08-28"


def test_payment_routes_errors_and_rule_warning(books, login_as):
    t = txn(books, date(2026, 9, 4))
    other = txn(books, date(2026, 9, 5), amount=-1)
    entry = post_entry(fiscal_year_id=books["fy"].id, journal_id=Journal.query.filter_by(code="BQ").one().id,
                       entry_date=t.transaction_date, description="Règle",
                       lines=[{"account_id": books["6061"].id, "label": "x", "debit_cents": 3999, "credit_cents": 0},
                              {"account_id": books["512"].id, "label": "x", "debit_cents": 0, "credit_cents": 3999}],
                       source="OFX_IMPORT", source_ref=f"FITID:{t.fitid}", commit=False)
    reconcile(t.id, next(l.id for l in entry.lines if l.account_id == books["512"].id), commit=False)
    db.session.commit()
    txn(books, date(2026, 9, 6))  # second candidat : pas de lien automatique
    p = invoice(books)
    client = login_as()
    assert any(s["rule"] for s in client.get(_api(f"/{p.id}")).get_json()["suggestions"])
    resp = client.post(_api(f"/{p.id}/payments"), json={"bank_transaction_id": other.id})
    assert resp.status_code == 422 and "ne peut pas régler la facture" in _notices(resp)
    assert "remplacez son écriture" in _notices(client.post(_api(f"/{p.id}/payments"),
                                                            json={"bank_transaction_id": t.id}))
    qonto_payment = PurchasePayment(purchase=invoice(books, number="F-2", supplier="Orange"),
                                    qonto_transaction_id="tx-1")
    db.session.add(qonto_payment)
    db.session.commit()
    page = _notices(client.delete(_api(f"/{qonto_payment.purchase_id}/payments/{qonto_payment.id}")))
    assert "ne se défait pas ici" in page
