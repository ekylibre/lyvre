"""Module Ventes, lot S4 : périmètre de l'intégration Qonto, émission par Qonto (facture, avoir,
devis), PDF Qonto, paiement marqué dans Qonto, envoi par Qonto, synchronisation en lecture.
Jamais le vrai Qonto : un faux client remplace `qonto_sales.client`."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, BankAccount, Entity, FiscalYear, JournalEntry, Sale, SaleCounter, SaleEmail
from app.services import external_config, organization, qonto_sales
from app.services.qonto_client import QontoError

API = "/api/v1/sales"
TODAY = date.today()
PDF = b"%PDF-1.7 qonto"


class FakeQonto:
    def __init__(self):
        self.calls = []
        self.clients = []
        self.invoices = {}
        self.fail_finalize = False
        self.number = 0
        self.pages = {"/clients": [], "/products": [], "/quotes": [], "/client_invoices": []}

    def _log(self, name, *args):
        self.calls.append((name, *args))

    def find_clients(self, **filters):
        self._log("find_clients", filters)
        return [c for c in self.clients if all(c.get(k) == v for k, v in filters.items())]

    def create_client(self, payload):
        self._log("create_client", payload)
        created = {"id": f"c{len(self.clients) + 1}", **payload}
        self.clients.append(created)
        return created

    def _numbered(self, prefix, payload, status):
        self.number += 1
        return {"id": f"{prefix}{self.number}", "number": f"{prefix.upper()}-QONTO-{self.number:03d}", "status": status,
                "attachment_id": f"att{self.number}", **payload}

    def create_client_invoice(self, payload):
        self._log("create_client_invoice", payload)
        draft = {"id": "draft1", "status": "draft"}
        self.invoices["draft1"] = payload
        return draft

    def finalize_client_invoice(self, invoice_id):
        self._log("finalize", invoice_id)
        if self.fail_finalize:
            raise QontoError("Qonto a répondu HTTP 422 : invalide")
        return self._numbered("f", {}, "unpaid")

    def delete_client_invoice(self, invoice_id):
        self._log("delete", invoice_id)

    def create_credit_note(self, payload):
        self._log("create_credit_note", payload)
        return self._numbered("av", {}, "issued")

    def create_quote(self, payload):
        self._log("create_quote", payload)
        return self._numbered("d", {}, "pending_approval")

    def get_client_invoice(self, invoice_id):
        return {"id": invoice_id, "attachment_id": "att-late"}

    def attachment(self, attachment_id):
        return {"url": f"https://qonto.example/{attachment_id}.pdf"}

    def download(self, url):
        self._log("download", url)
        return PDF

    def mark_client_invoice_paid(self, invoice_id, paid_at):
        self._log("mark_paid", invoice_id, paid_at)
        return {"id": invoice_id, "status": "paid"}

    def unmark_client_invoice_paid(self, invoice_id):
        self._log("unmark_paid", invoice_id)
        return {"id": invoice_id, "status": "unpaid"}

    def send_client_invoice(self, invoice_id, payload):
        self._log("send", invoice_id, payload)

    def send_quote(self, quote_id, payload):
        self._log("send_quote", quote_id, payload)

    def iter_pages(self, path, key, params=None):
        yield self.pages[path]


@pytest.fixture()
def fake(monkeypatch):
    api = FakeQonto()
    monkeypatch.setattr(qonto_sales, "client", lambda: api)
    return api


@pytest.fixture()
def admin(app, login_as, fake):
    client = login_as(role="admin")
    org = organization.get()
    org.address_line1, org.postal_code, org.city, org.siren = "1 rue A", "75001", "Paris", "123456789"
    bank = Account(code="512", label="Qonto", account_type="TRESORERIE")
    db.session.add_all([
        Account(code="411", label="Clients", account_type="TIERS", is_header=True),
        Account(code="706", label="Prestations", account_type="PRODUIT"), bank,
        FiscalYear(label="An", start_date=date(TODAY.year, 1, 1), end_date=date(TODAY.year, 12, 31)),
        Entity(name="Client SARL", entity_type="CLIENT", address_line1="2 av X", postal_code="69001", city="Lyon",
               siret="98765432100012", email="compta@client.example"),
    ])
    db.session.flush()
    db.session.add(BankAccount(label="Qonto", kind="bank", account_id=bank.id, qonto_account_id="qa1",
                               iban="FR7616958000011234567890123"))
    db.session.commit()
    external_config.set_many("qonto", {"login": "sci-1234", "secret_key": "qonto-secret"})
    external_config.set_scopes("qonto", ["transactions", "purchases", "sales"])
    return client


def _draft(admin, kind="invoice", qonto=True, label="Gestion locative du lot B — octobre 2026 (forfait)"):
    entity = Entity.query.filter_by(name="Client SARL").one()
    resp = admin.post(API, json={"kind": kind, "entity_id": entity.id, "issue_date": TODAY.isoformat(), "qonto_emit": qonto,
                                 "lines": [{"label": label, "unit_price": "500", "vat_rate": "0"}]})
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["item"]


def test_scopes(app, admin):
    session = admin.get("/api/v1/session").get_json()["instance"]["integrations"]
    assert session["scopes"]["qonto"] == ["purchases", "sales", "transactions"]
    detail = admin.get("/api/v1/integrations/qonto").get_json()["item"]
    assert {s["value"]: s["checked"] for s in detail["scopes"]} == {"transactions": True, "purchases": True, "sales": True}
    admin.post("/api/v1/integrations/qonto/scopes", json={"scopes": ["transactions"]})
    error = admin.post("/api/v1/purchases/sync").get_json()["error"]
    assert error["code"] == "integration_required" and error["scope"] == "purchases" and "Achats" in error["message"]
    assert admin.get(API).get_json()["meta"]["qonto"]["enabled"] is False
    assert admin.post("/api/v1/integrations/qonto/scopes", json={"scopes": ["nope"]}).status_code == 422
    # Périmètre Ventes décoché : la case « Émettre avec Qonto » est ignorée.
    assert _draft(admin)["qonto_emit"] is False


def test_issue_invoice_with_qonto(admin, fake):
    item = _draft(admin)
    assert item["qonto_emit"] is True
    resp = admin.post(f"{API}/{item['id']}/issue")
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()["item"]
    assert body["number"] == "F-QONTO-001" and body["status"] == "issued"
    created = next(c[1] for c in fake.calls if c[0] == "create_client")
    assert created["kind"] == "company" and created["tax_identification_number"] == "987654321"
    payload = next(c[1] for c in fake.calls if c[0] == "create_client_invoice")
    assert payload["status"] == "draft" and payload["payment_methods"] == {"iban": "FR7616958000011234567890123"}
    item0 = payload["items"][0]
    assert item0["title"] == "Gestion locative du lot B — octobre 2026" and item0["description"] == "(forfait)"  # 40 caractères
    assert item0["vat_exemption_reason"] == "S293B" and item0["unit_price"] == {"value": "500.00", "currency": "EUR"}
    sale = db.session.get(Sale, item["id"])
    assert sale.qonto_id == "f1" and sale.series_year is None and SaleCounter.query.count() == 0
    assert sale.journal_entry.source == "SALE" and Entity.query.filter_by(name="Client SARL").one().qonto_client_id == "c1"
    assert admin.get(f"{API}/{item['id']}/pdf").data == PDF  # PDF Qonto récupéré et conservé
    # La série de l'application n'a pas avancé.
    local = _draft(admin, qonto=False)
    assert admin.post(f"{API}/{local['id']}/issue").get_json()["item"]["number"] == f"F-{TODAY.year}-0001"
    # Client déjà connu de Qonto : pas de nouvelle création.
    second = _draft(admin)
    admin.post(f"{API}/{second['id']}/issue")
    assert sum(1 for c in fake.calls if c[0] == "create_client") == 1


def test_qonto_failure_leaves_draft(admin, fake):
    fake.fail_finalize = True
    item = _draft(admin)
    resp = admin.post(f"{API}/{item['id']}/issue")
    assert resp.status_code == 409 and "Qonto a refusé" in resp.get_json()["error"]["message"]
    assert ("delete", "draft1") in fake.calls  # pas de brouillon orphelin dans Qonto
    assert db.session.get(Sale, item["id"]).status == "draft" and JournalEntry.query.count() == 0


def test_credit_note_and_quote_by_qonto(admin, fake):
    item = _draft(admin)
    admin.post(f"{API}/{item['id']}/issue")
    note = admin.post(f"{API}/{item['id']}/credit-note", json={"reason": "Erreur"}).get_json()["item"]
    assert note["qonto_emit"] is True
    issued = admin.post(f"{API}/{note['id']}/issue").get_json()["item"]
    assert issued["number"] == "AV-QONTO-002"
    assert next(c[1] for c in fake.calls if c[0] == "create_credit_note")["invoice_id"] == "f1"
    assert db.session.get(Sale, item["id"]).status == "canceled"
    quote = _draft(admin, kind="quote")
    body = admin.post(f"{API}/{quote['id']}/issue").get_json()["item"]
    assert body["number"] == "D-QONTO-003" and body["status"] == "issued" and body["journal_entry"] is None


def test_payment_marks_paid_in_qonto(admin, fake):
    item = _draft(admin)
    admin.post(f"{API}/{item['id']}/issue")
    cash = BankAccount.query.one()
    resp = admin.post(f"{API}/{item['id']}/payments", json={"amount": "500", "bank_account_id": cash.id})
    assert resp.get_json()["item"]["status"] == "paid"
    assert ("mark_paid", "f1", TODAY.isoformat()) in fake.calls
    payment_id = resp.get_json()["item"]["payments"][0]["id"]
    admin.delete(f"/api/v1/sale-payments/{payment_id}")
    assert ("unmark_paid", "f1") in fake.calls


def test_send_through_qonto(admin, fake):
    item = _draft(admin)
    admin.post(f"{API}/{item['id']}/issue")
    external_config.set_enabled("smtp", False)  # inutile pour une pièce Qonto
    resp = admin.post(f"{API}/{item['id']}/send", json={"to": ["compta@client.example"], "subject": "Facture"})
    assert resp.status_code == 200, resp.get_json()
    sent = next(c for c in fake.calls if c[0] == "send")
    assert sent[1] == "f1" and sent[2]["send_to"] == ["compta@client.example"] and sent[2]["copy_to_self"] is False
    assert SaleEmail.query.one().channel == "qonto"


def test_sync_imports_invoices_created_in_qonto(admin, fake):
    fake.pages["/clients"] = [{"id": "c9", "kind": "company", "name": "Nouveau Client", "tax_identification_number": "111222333",
                               "billing_address": {"street_address": "9 rue Z", "zip_code": "13001", "city": "Marseille"}}]
    fake.pages["/products"] = [{"id": "p1", "title": "Loyer garage", "type": "service", "unit_price": {"value": "120.00"}, "vat_rate": "0"}]
    fake.pages["/client_invoices"] = [
        {"id": "q1", "number": "F-2026-QONTO", "status": "unpaid", "issue_date": TODAY.isoformat(), "due_date": TODAY.isoformat(),
         "client": {"id": "c9"}, "attachment_id": "att-q1",
         "items": [{"title": "Loyer garage", "quantity": "1", "unit_price": {"value": "120.00"}, "vat_rate": "0"}]},
        {"id": "q2", "status": "draft"},
    ]
    result = qonto_sales.sync()
    assert result["invoices_created"] == 1 and result["clients_linked"] == 1 and result["products_created"] == 1, result
    sale = Sale.query.filter_by(qonto_id="q1").one()
    assert sale.source == "qonto" and sale.number == "F-2026-QONTO" and sale.total_cents == 12000
    assert sale.entity.name == "Nouveau Client" and sale.journal_entry is not None and sale.pdf_path
    # Second passage : rien de neuf, statut mis à jour.
    fake.pages["/client_invoices"][0]["status"] = "paid"
    result = qonto_sales.sync()
    assert result["invoices_created"] == 0 and result["invoices_updated"] == 1
    assert Sale.query.filter_by(qonto_id="q1").one().qonto_status == "paid"
