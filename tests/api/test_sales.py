"""Module Ventes, lot S1 : brouillons, totaux, émission (numéro continu, écriture VE, PDF Factur-X),
avoirs, verrouillage des pièces émises, envoi par email (faux SMTP), réglages de facturation."""
from datetime import date

import facturx
import pytest

from app.extensions import db
from app.models import Account, Entity, FiscalYear, JournalEntry, Organization, Product, Sale, SaleCounter, SaleEmail
from app.services import external_config, organization, sale_documents

API = "/api/v1/sales"


@pytest.fixture()
def admin(app, login_as):
    client = login_as(role="admin")
    org = organization.get()
    org.name, org.address_line1, org.postal_code, org.city, org.siren = "SCI Exemple", "1 rue A", "75001", "Paris", "123456789"
    db.session.add_all([
        Account(code="411", label="Clients", account_type="TIERS", is_header=True),
        Account(code="4457", label="TVA collectée", account_type="TIERS"),
        Account(code="706", label="Prestations de services", account_type="PRODUIT"),
        Account(code="707", label="Ventes de marchandises", account_type="PRODUIT"),
        FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), vat_liable=True,
                   vat_on_receipts=True),
        Entity(name="Client SARL", entity_type="CLIENT", address_line1="2 avenue X", postal_code="69001",
               city="Lyon", siret="98765432100012", email="compta@client.example"),
    ])
    db.session.commit()
    client.put("/api/v1/billing-settings", json={"iban": "FR76 3000 6000 0112 3456 7890 189"})
    _vat_number("FR32123456789")
    return client


def _vat_number(vat):
    """TVA du vendeur : mention de la Structure (lot G2)."""
    from app.services import organization
    organization.get().vat_number = vat
    db.session.commit()


def _client():
    return Entity.query.filter_by(name="Client SARL").one()


def _draft(admin, lines=None, **header):
    body = {"entity_id": _client().id, "issue_date": "2026-10-23", **header,
            "lines": lines or [
                {"label": "Conseil", "quantity": "2,5", "unit": "heure", "unit_price": "80", "vat_rate": "20", "account_code": "706"},
                {"label": "Fournitures", "quantity": "3", "unit_price": "10,01", "discount": "10", "vat_rate": "5,5",
                 "account_code": "707", "nature": "goods"},
            ]}
    resp = admin.post(API, json=body)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["item"]


def _lines(entry):
    return sorted((l.account.code, l.debit_cents, l.credit_cents) for l in entry.lines)


def test_draft_totals_and_vat_by_rate(admin):
    item = _draft(admin)
    # 2,5 h × 80 = 200,00 ; 3 × 10,01 − 10 % = 27,03 ; TVA 40,00 + 1,49 (par taux).
    assert (item["untaxed_cents"], item["tax_cents"], item["total_cents"]) == (22703, 4149, 26852)
    assert item["status"] == "draft" and item["number"] is None
    assert item["due_date"] == "2026-11-22"  # 30 jours par défaut
    assert item["issue_problems"] == []


def test_issue_number_entry_pdf(admin):
    item = _draft(admin)
    resp = admin.post(f"{API}/{item['id']}/issue")
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()["item"]
    assert body["number"] == "F-2026-0001" and body["status"] == "issued"
    sale = db.session.get(Sale, item["id"])
    assert _client().customer_account_code == "411001"
    # Services à l'encaissement (44574), biens en 44571.
    assert _lines(sale.journal_entry) == [("411001", 26852, 0), ("44571", 0, 149), ("44574", 0, 4000),
                                          ("706", 0, 20000), ("707", 0, 2703)]
    assert sale.journal_entry.journal.code == "VE" and sale.journal_entry.source == "SALE"
    name, xml = facturx.get_xml_from_pdf(sale_documents.pdf_file(sale).read_bytes(), check_xsd=True)
    assert b"F-2026-0001" in xml and b"268.52" in xml
    pdf = admin.get(f"{API}/{item['id']}/pdf")
    assert pdf.status_code == 200 and pdf.mimetype == "application/pdf"

    # Pièce émise : ni modifiée, ni supprimée, ni son écriture.
    assert admin.patch(f"{API}/{item['id']}", json={"entity_id": _client().id, "lines": []}).status_code == 409
    assert admin.delete(f"{API}/{item['id']}").status_code == 409
    assert admin.delete(f"/api/v1/entries/{sale.journal_entry_id}").status_code in (200, 409, 422)
    assert db.session.get(JournalEntry, sale.journal_entry_id) is not None
    second = _draft(admin)
    assert admin.post(f"{API}/{second['id']}/issue").get_json()["item"]["number"] == "F-2026-0002"


def test_failed_issue_consumes_no_number(admin, monkeypatch):
    item = _draft(admin)
    org = organization.get()
    org.siren = None
    db.session.commit()
    resp = admin.post(f"{API}/{item['id']}/issue")
    assert resp.status_code == 409 and "SIREN" in resp.get_json()["error"]["message"]
    org = db.session.query(Organization).first()
    org.siren = "123456789"
    db.session.commit()

    def boom(sale):
        raise RuntimeError("PDF impossible")
    monkeypatch.setattr(sale_documents, "store_pdf", boom)
    with pytest.raises(RuntimeError):
        admin.post(f"{API}/{item['id']}/issue")
    assert SaleCounter.query.count() == 0 and JournalEntry.query.count() == 0
    assert db.session.get(Sale, item["id"]).status == "draft"
    monkeypatch.undo()
    assert admin.post(f"{API}/{item['id']}/issue").get_json()["item"]["number"] == "F-2026-0001"


def test_not_vat_liable_uses_293b(admin):
    fy = FiscalYear.query.one()
    fy.vat_liable = False
    db.session.commit()
    item = _draft(admin)
    assert item["tax_cents"] == 0 and item["vat_mode"] == "none"
    admin.post(f"{API}/{item['id']}/issue")
    sale = db.session.get(Sale, item["id"])
    assert _lines(sale.journal_entry) == [("411001", 22703, 0), ("706", 0, 20000), ("707", 0, 2703)]
    assert "293 B" in sale_documents.render_html(sale)


def test_vat_on_debits(admin):
    admin.patch(f"/api/v1/fiscal-years/{FiscalYear.query.one().id}", json={"vat_on_receipts": False})
    item = _draft(admin)
    admin.post(f"{API}/{item['id']}/issue")
    codes = {code for code, _, _ in _lines(db.session.get(Sale, item["id"]).journal_entry)}
    assert "44571" in codes and "44574" not in codes
    assert "d'après les débits" in sale_documents.render_html(db.session.get(Sale, item["id"]))


def test_credit_notes(admin):
    item = _draft(admin)
    admin.post(f"{API}/{item['id']}/issue")
    invoice = db.session.get(Sale, item["id"])
    partial = admin.post(f"{API}/{item['id']}/credit-note", json={"reason": "Remise accordée",
                                                                 "line_ids": [invoice.lines[1].id]}).get_json()["item"]
    assert partial["kind"] == "credit_note" and partial["total_cents"] == 2852
    issued = admin.post(f"{API}/{partial['id']}/issue").get_json()["item"]
    assert issued["number"] == "AV-2026-0001" and db.session.get(Sale, item["id"]).status == "issued"
    # Avoir de plus de la moitié : la facture n'est pas annulée pour autant (régression).
    half = admin.post(f"{API}/{item['id']}/credit-note", json={"reason": "Geste", "line_ids": [invoice.lines[0].id]}).get_json()["item"]
    resp = admin.patch(f"{API}/{half['id']}", json={"entity_id": half["client"]["id"], "issue_date": half["issue_date"],
                                                   "lines": [{"label": "Geste", "unit_price": "12", "vat_rate": "20", "account_code": "706"}]})
    assert resp.status_code == 200, resp.get_json()
    assert admin.post(f"{API}/{half['id']}/issue").status_code == 200
    assert db.session.get(Sale, item["id"]).status == "issued"
    note = db.session.get(Sale, partial["id"])
    assert _lines(note.journal_entry) == [("411001", 0, 2852), ("44571", 149, 0), ("707", 2703, 0)]
    name, xml = facturx.get_xml_from_pdf(sale_documents.pdf_file(note).read_bytes(), check_xsd=True)
    assert b"<ram:TypeCode>381</ram:TypeCode>" in xml and b"F-2026-0001" in xml

    full = admin.post(f"{API}/{item['id']}/credit-note", json={"reason": "Annulation"}).get_json()["item"]
    resp = admin.post(f"{API}/{full['id']}/issue")
    assert resp.status_code == 409 and "dépasse" in resp.get_json()["error"]["message"]
    rest = admin.post(f"{API}/{item['id']}/credit-note", json={"reason": "Annulation",
                                                              "line_ids": [invoice.lines[0].id]}).get_json()["item"]
    resp = admin.patch(f"{API}/{rest['id']}", json={"entity_id": rest["client"]["id"], "issue_date": rest["issue_date"],
                                                   "lines": [{"label": "Solde", "unit_price": "188", "vat_rate": "20", "account_code": "706"}]})
    assert resp.status_code == 200 and resp.get_json()["item"]["total_cents"] == 22560  # 268,52 − 28,52 − 14,40
    admin.delete(f"{API}/{full['id']}")
    resp = admin.post(f"{API}/{rest['id']}/issue")
    assert resp.status_code == 200, resp.get_json()
    assert db.session.get(Sale, item["id"]).status == "canceled"  # avoirs = montant de la facture


def test_chronology_and_closed_year(admin):
    late = _draft(admin, issue_date="2026-10-23")
    admin.post(f"{API}/{late['id']}/issue")
    early = _draft(admin, issue_date="2026-10-01")
    resp = admin.post(f"{API}/{early['id']}/issue")
    assert resp.status_code == 409 and "antérieure" in resp.get_json()["error"]["message"]
    outside = _draft(admin, issue_date="2027-01-05")
    assert "Aucun exercice" in admin.post(f"{API}/{outside['id']}/issue").get_json()["error"]["message"]


def test_validation_errors(admin):
    resp = admin.post(API, json={"entity_id": _client().id, "lines": [{"label": "", "unit_price": "10"}]})
    assert resp.status_code == 422
    resp = admin.post(API, json={"entity_id": _client().id, "lines": [{"label": "X", "unit_price": "10", "account_code": "601"}]})
    assert resp.status_code == 422 and "compte de vente" in resp.get_json()["error"]["message"]
    resp = admin.post(API, json={"new_client_name": "Nouveau client", "lines": [{"label": "X", "unit_price": "10"}]})
    assert resp.status_code == 201 and Entity.query.filter_by(name="Nouveau client").one().entity_type == "CLIENT"
    item = resp.get_json()["item"]
    assert any("Adresse du client" in p for p in item["issue_problems"])
    assert item["lines"][0]["account_code"] == "706"  # compte de vente par défaut du plan


def test_product_fills_line(admin):
    product = Product(name="Audit", kind="sale", sale_account_id=Account.query.filter_by(code="706").one().id,
                      vat_rate_bp=2000, sale_price_cents=50000, unit="jour", nature="services")
    db.session.add(product)
    db.session.commit()
    item = _draft(admin, lines=[{"product_id": str(product.id), "label": "Audit", "unit_price": "500", "vat_rate": "20"}])
    assert item["lines"][0]["account_code"] == "706"
    options = admin.get(f"{API}/form-options").get_json()
    assert options["products"][0]["price"] == "500,00" and options["vat_mode"] == "receipts"


def test_send_by_email(admin, monkeypatch):
    item = _draft(admin)
    admin.post(f"{API}/{item['id']}/issue")
    external_config.set_enabled("smtp", False)
    resp = admin.post(f"{API}/{item['id']}/send", json={"to": ["compta@client.example"]})
    assert resp.status_code == 409 and resp.get_json()["error"]["code"] == "integration_required"
    external_config.set_enabled("smtp", True)

    sent = []

    class FakeSMTP:
        def send_message(self, message):
            sent.append(message)

        def quit(self):
            pass
    from app.services import membership_reminders
    monkeypatch.setattr(membership_reminders, "_open_smtp", lambda settings, timeout=20: FakeSMTP())
    resp = admin.post(f"{API}/{item['id']}/send", json={"to": ["compta@client.example"], "cc": ["moi@example.org"],
                                                       "subject": "Votre facture", "body": "Bonjour"})
    assert resp.status_code == 200, resp.get_json()
    message = sent[0]
    assert message["To"] == "compta@client.example" and message["Cc"] == "moi@example.org"
    attachment = next(message.iter_attachments())
    assert attachment.get_filename() == "facture-F-2026-0001.pdf"
    assert SaleEmail.query.one().status == "sent" and db.session.get(Sale, item["id"]).sent_at is not None
    assert admin.post(f"{API}/{item['id']}/send", json={"to": ["pas-une-adresse"]}).status_code == 422

    batch = admin.post(f"{API}/send", json={"ids": [item["id"]]}).get_json()
    assert batch["result"]["sent"] == 1 and sent[-1]["To"] == "compta@client.example"


def test_billing_settings(admin):
    body = admin.get("/api/v1/billing-settings").get_json()["item"]
    assert body["iban"] == "FR7630006000011234567890189" and body["payment_terms_days"] == 30
    assert admin.put("/api/v1/billing-settings", json={"iban": "FR00 1234"}).status_code == 422
    resp = admin.put("/api/v1/billing-settings", json={"legal_form": "SCI", "share_capital": "274 890,00",
                                                       "payment_terms_days": 45})
    assert resp.status_code == 200 and "share_capital" not in resp.get_json()["item"]  # mentions : Structure
    item = _draft(admin)
    assert item["due_date"] == "2026-12-07"


def test_accountant_read_only(admin):
    from app.models import InstanceMembership

    item = _draft(admin)
    InstanceMembership.query.one().role = "accountant"  # même utilisateur, devenu expert-comptable
    db.session.commit()
    assert admin.get(API).status_code == 200
    assert admin.post(f"{API}/{item['id']}/issue").status_code == 403
