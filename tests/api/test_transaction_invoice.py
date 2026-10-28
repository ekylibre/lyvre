"""Facture d'achat créée depuis le justificatif d'une transaction Qonto : pièce téléchargée et lue, formulaire
prérempli (la transaction fait foi pour le montant payé), facture reliée à cette transaction avant sa
comptabilisation (règlement sur elle, pas sur un autre débit de même montant)."""
from datetime import date

import fitz
import pytest

from app.extensions import db
from app.models import Account, BankAccount, BankTransaction, FiscalYear, Journal, Purchase
from app.services import qonto_client, transaction_invoice
from app.services.qonto_client import QontoError


def _pdf(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((60, 80), text, fontsize=11)
    return doc.tobytes()


INVOICE = _pdf("Google Cloud France SARL\nFacture n° 5214789632\nDate de facture : 02/07/2026\n"
               "Total HT 48,60 EUR\nTVA 20 % 9,72 EUR\nTotal TTC 58,32 EUR")


class FakeQonto:
    def __init__(self, content=INVOICE, ids=("att-1",)):
        self.content, self.ids, self.calls = content, ids, []

    def transaction(self, transaction_id):
        self.calls.append(("transaction", transaction_id))
        return {"id": transaction_id, "attachment_ids": list(self.ids)}

    def attachment(self, attachment_id):
        self.calls.append(("attachment", attachment_id))
        return {"id": attachment_id, "file_name": "facture-google.pdf", "url": f"https://files.example/{attachment_id}"}

    def download(self, url):
        self.calls.append(("download", url))
        return self.content


@pytest.fixture()
def bank(app, login_as, monkeypatch):
    client = login_as()
    accounts = {code: Account(code=code, label=code, account_type="EXPENSE")
                for code in ("401", "512", "6068", "44566")}
    db.session.add_all([*accounts.values(), Journal(code="AC", label="Achats"), Journal(code="BQ", label="Banque"),
                        FiscalYear(label="2026-2027", start_date=date(2026, 7, 1), end_date=date(2027, 6, 30),
                                   vat_liable=True)])
    db.session.flush()
    ba = BankAccount(label="Qonto — Compte principal", account_id=accounts["512"].id, qonto_account_id="qa-1")
    db.session.add(ba)
    db.session.commit()
    fake = FakeQonto()
    monkeypatch.setattr(qonto_client, "from_app_config", lambda *a, **k: fake)
    return {"client": client, "ba": ba, "fake": fake}


def _txn(bank, amount=-5832, fitid="tx-google", source="qonto", attachments=1, day=date(2026, 7, 2)):
    t = BankTransaction(bank_account_id=bank["ba"].id, fitid=fitid, transaction_date=day, amount_cents=amount,
                        label="Google Workspace_ekyli", counterparty="Google Workspace", source=source,
                        attachment_count=attachments)
    db.session.add(t)
    db.session.commit()
    return t


def test_blockers(bank):
    assert "Qonto" in transaction_invoice.blocker(_txn(bank, source="ofx", fitid="o-1"))
    assert "débit" in transaction_invoice.blocker(_txn(bank, amount=5832, fitid="c-1"))
    assert "justificatif" in transaction_invoice.blocker(_txn(bank, attachments=0, fitid="n-1"))
    assert transaction_invoice.blocker(_txn(bank)) is None


def test_draft_reads_the_attachment(bank):
    t = _txn(bank)
    body = bank["client"].post(f"/api/v1/bank-transactions/{t.id}/purchase-draft", json={}).get_json()
    assert body["transaction"]["amount_cents"] == -5832 and body["preview"]["mime"] == "application/pdf"
    values = body["form"]["values"]
    assert values["total"] == "58,32" and values["issue_date"] == "2026-07-02"
    assert values.get("entity_id") == "new" and values.get("new_name")
    assert ("transaction", "tx-google") in bank["fake"].calls and ("download", "https://files.example/att-1") in bank["fake"].calls


def test_amount_mismatch_is_flagged(bank):
    bank["fake"].content = _pdf("Facture n° 9\nDate : 02/07/2026\nTotal TTC 60,00 EUR")
    t = _txn(bank)
    form = bank["client"].post(f"/api/v1/bank-transactions/{t.id}/purchase-draft", json={}).get_json()["form"]
    assert any("montant payé" in w for w in form["warnings"]) and "total" in form["checks"]


def test_create_links_and_settles_this_transaction(bank):
    t = _txn(bank)
    _txn(bank, fitid="tx-same-amount", day=date(2026, 7, 3))  # autre débit de même montant : jamais choisi
    client = bank["client"]
    draft = client.post(f"/api/v1/bank-transactions/{t.id}/purchase-draft", json={}).get_json()
    resp = client.post("/api/v1/purchases", json={**draft["form"]["values"], "token": draft["token"],
                                                  "rows": draft["form"]["rows"], "bank_transaction_id": t.id,
                                                  "send_to_qonto": True})
    assert resp.status_code == 201, resp.get_json()
    p = Purchase.query.one()
    assert p.attachment_path and p.qonto_upload_status is None  # pièce rangée, rien d'envoyé à Qonto
    assert [pay.bank_transaction_id for pay in p.payments] == [t.id]
    from app.services.purchase_posting import purchase_state
    assert p.journal_entry_id is not None, purchase_state(p).reasons  # comptabilisée…
    db.session.refresh(t)
    assert p.payments[0].journal_entry_id is not None and t.reconciled  # …et réglée par cette transaction
    assert transaction_invoice.blocker(t) is not None
    rows = client.get(f"/api/v1/bank-accounts/{bank['ba'].id}/transactions?status=all").get_json()["transactions"]
    flags = {row["id"]: row["purchase_from_attachment"] for row in rows}
    assert flags[t.id] is False


def test_qonto_errors_become_messages(bank, monkeypatch):
    def boom(*a, **k):
        raise QontoError("identifiants refusés")
    monkeypatch.setattr(qonto_client, "from_app_config", boom)
    t = _txn(bank)
    resp = bank["client"].post(f"/api/v1/bank-transactions/{t.id}/purchase-draft", json={})
    assert resp.status_code == 502 and "identifiants refusés" in resp.get_json()["error"]["message"]
    bank["fake"].ids = ()
    monkeypatch.setattr(qonto_client, "from_app_config", lambda *a, **k: FakeQonto(ids=()))
    resp = bank["client"].post(f"/api/v1/bank-transactions/{t.id}/purchase-draft", json={})
    assert resp.status_code == 409 and "Aucun justificatif" in resp.get_json()["error"]["message"]
