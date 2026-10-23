"""Module Ventes, lot S3 : devis (brouillon, émission sans écriture, statut, expiration, facture
reprenant le devis)."""
from datetime import date, timedelta

import pytest

from app.extensions import db
from app.models import Account, Entity, FiscalYear, JournalEntry, Sale
from app.services import organization, sale_documents

API = "/api/v1/sales"
TODAY = date.today()


@pytest.fixture()
def admin(app, login_as):
    client = login_as(role="admin")
    org = organization.get()
    org.address_line1, org.postal_code, org.city, org.siren = "1 rue A", "75001", "Paris", "123456789"
    db.session.add_all([
        Account(code="411", label="Clients", account_type="TIERS", is_header=True),
        Account(code="706", label="Prestations", account_type="PRODUIT"),
        FiscalYear(label="An", start_date=date(TODAY.year, 1, 1), end_date=date(TODAY.year, 12, 31)),
        Entity(name="Client SARL", entity_type="CLIENT", address_line1="2 av X", postal_code="69001", city="Lyon"),
    ])
    db.session.commit()
    return client


def _quote(admin, **header):
    entity = Entity.query.filter_by(name="Client SARL").one()
    resp = admin.post(API, json={"kind": "quote", "entity_id": entity.id, "issue_date": TODAY.isoformat(), **header,
                                 "lines": [{"label": "Audit", "quantity": "2", "unit": "jour", "unit_price": "500"}]})
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["item"]


def test_quote_issue_has_no_entry(admin):
    quote = _quote(admin)
    assert quote["kind"] == "quote" and quote["due_date"] is None
    assert quote["validity_date"] == (TODAY + timedelta(days=30)).isoformat()
    item = admin.post(f"{API}/{quote['id']}/issue").get_json()["item"]
    assert item["number"] == f"D-{TODAY.year}-0001" and item["status"] == "issued" and item["status_label"] == "Envoyé"
    assert item["journal_entry"] is None and JournalEntry.query.count() == 0
    sale = db.session.get(Sale, quote["id"])
    html = sale_documents.render_html(sale)
    assert "Bon pour accord" in html and "Valable jusqu" in html
    assert sale_documents.pdf_file(sale).read_bytes().startswith(b"%PDF")
    assert admin.delete(f"{API}/{quote['id']}").status_code == 409


def test_quote_list_and_expiry(admin):
    old = _quote(admin, issue_date=(TODAY - timedelta(days=40)).isoformat(),
                 validity_date=(TODAY - timedelta(days=10)).isoformat())
    admin.post(f"{API}/{old['id']}/issue")
    fresh = _quote(admin)
    admin.post(f"{API}/{fresh['id']}/issue")
    quotes = admin.get(f"{API}?kind=quote").get_json()["items"]
    assert {q["id"]: q["status"] for q in quotes} == {old["id"]: "expired", fresh["id"]: "issued"}
    assert [q["id"] for q in admin.get(f"{API}?kind=quote&status=expired").get_json()["items"]] == [old["id"]]
    assert admin.get(API).get_json()["items"] == []  # la liste par défaut : factures et avoirs


def test_accept_refuse_and_invoice(admin):
    quote = _quote(admin)
    assert admin.post(f"{API}/{quote['id']}/quote-status", json={"status": "accepted"}).status_code == 409  # brouillon
    admin.post(f"{API}/{quote['id']}/issue")
    assert admin.post(f"{API}/{quote['id']}/quote-status", json={"status": "refused"}).get_json()["item"]["status"] == "refused"
    assert admin.post(f"{API}/{quote['id']}/quote-status", json={"status": "accepted"}).get_json()["item"]["status"] == "accepted"
    resp = admin.post(f"{API}/{quote['id']}/to-invoice")
    assert resp.status_code == 201
    invoice = resp.get_json()["item"]
    assert invoice["kind"] == "invoice" and invoice["status"] == "draft" and invoice["total_cents"] == 100000
    assert invoice["quote"]["number"] == f"D-{TODAY.year}-0001" and invoice["purchase_order"] == f"Devis D-{TODAY.year}-0001"
    detail = admin.get(f"{API}/{quote['id']}").get_json()["item"]
    assert detail["status"] == "invoiced" and [i["id"] for i in detail["invoices"]] == [invoice["id"]]
    # Brouillon de facture abandonné : le devis redevient accepté.
    admin.delete(f"{API}/{invoice['id']}")
    assert admin.get(f"{API}/{quote['id']}").get_json()["item"]["status"] == "accepted"
    again = admin.post(f"{API}/{quote['id']}/to-invoice").get_json()["item"]
    assert admin.post(f"{API}/{again['id']}/issue").get_json()["item"]["number"] == f"F-{TODAY.year}-0001"
