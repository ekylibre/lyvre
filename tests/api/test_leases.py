"""Module Ventes, lot S5 : factures récurrentes (échéances préparées une seule fois, période dans la
désignation, émission en lot), baux (avis d'échéance, dépôt de garantie 165), quittances et reçus."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, BankAccount, Entity, FiscalYear, JournalEntry, Lease, Recurrence, RentReceipt, Sale
from app.services import external_config, organization, recurrence

TODAY = date.today()


@pytest.fixture()
def admin(app, login_as):
    client = login_as(role="admin")
    org = organization.get()
    org.address_line1, org.postal_code, org.city, org.siren = "1 allée des Chênes", "75001", "Paris", "123456789"
    org.signatory_name = "Gérant Exemple"
    bank = Account(code="512", label="Banque", account_type="TRESORERIE")
    db.session.add_all([
        Account(code="411", label="Clients", account_type="TIERS", is_header=True),
        Account(code="706", label="Loyers", account_type="PRODUIT"),
        Account(code="708", label="Charges refacturées", account_type="PRODUIT"), bank,
        FiscalYear(label="An", start_date=date(TODAY.year - 1, 1, 1), end_date=date(TODAY.year, 12, 31)),
        Entity(name="Locataire Martin", entity_type="CLIENT", address_line1="3 rue B", postal_code="75002", city="Paris",
               person_kind="individual", email="martin@example.org"),
    ])
    db.session.flush()
    db.session.add(BankAccount(label="Banque", kind="bank", account_id=bank.id))
    db.session.commit()
    return client


def _tenant():
    return Entity.query.filter_by(name="Locataire Martin").one()


def _months_ago(n):
    return recurrence.add_months(TODAY.replace(day=1), -n, 1)


def test_recurrence_prepares_each_period_once(admin):
    start = _months_ago(2)
    resp = admin.post("/api/v1/recurrences", json={
        "label": "Abonnement maintenance", "entity_id": _tenant().id, "frequency": "monthly", "due_day": 1,
        "start_date": start.isoformat(), "in_advance": True,
        "lines": [{"label": "Maintenance {periode}", "unit_price": "100", "vat_rate": "0"}]})
    assert resp.status_code == 201, resp.get_json()
    due = admin.get("/api/v1/sales/due").get_json()
    assert due["meta"]["prepared"] == 3 and len(due["items"]) == 3  # 3 mois : il y a 2 mois, le mois dernier, ce mois
    assert admin.get("/api/v1/sales/due").get_json()["meta"]["prepared"] == 0  # jamais deux fois
    sales = Sale.query.filter(Sale.recurrence_id.isnot(None)).order_by(Sale.service_start).all()
    assert sales[0].service_start == start and sales[0].lines[0].label == f"Maintenance {recurrence.MONTHS[start.month - 1]} {start.year}"
    assert all(s.issue_date == TODAY for s in sales)
    result = admin.post("/api/v1/sales/issue-batch", json={"ids": [s.id for s in sales]}).get_json()["result"]
    assert result["issued"] == 3 and Sale.query.filter_by(status="issued").count() == 3
    assert admin.get("/api/v1/sales/due").get_json()["items"] == []


def test_quarterly_in_arrears_and_end_date():
    rec = Recurrence(label="x", frequency="quarterly", due_day=10, start_date=date(2026, 1, 1), in_advance=False,
                     next_date=date(2026, 4, 10))
    assert recurrence.period_of(rec, date(2026, 4, 10)) == (date(2026, 1, 1), date(2026, 3, 31))
    assert recurrence.period_label(rec, date(2026, 1, 1)) == "T1 2026"
    rec.in_advance, rec.frequency = True, "yearly"
    assert recurrence.period_of(rec, date(2026, 4, 10)) == (date(2026, 1, 1), date(2026, 12, 31))
    assert recurrence.first_due(date(2026, 3, 15), 5) == date(2026, 4, 5)


def test_lease_invoices_deposit_and_receipts(admin, monkeypatch):
    resp = admin.post("/api/v1/leases", json={
        "entity_id": _tenant().id, "unit_label": "Appartement 2B", "address_line1": "10 rue des Lilas",
        "postal_code": "75011", "city": "Paris", "start_date": _months_ago(0).isoformat(), "rent": "800", "charges": "50",
        "deposit": "1600", "due_day": 1})
    assert resp.status_code == 201, resp.get_json()
    lease = resp.get_json()["item"]
    assert (lease["rent_account_code"], lease["charges_account_code"]) == ("706", "708")
    # PATCH des lignes d'un loyer : par le bail seulement.
    rec_id = Lease.query.one().recurrence_id
    assert admin.patch(f"/api/v1/recurrences/{rec_id}", json={"lines": []}).status_code == 409

    due = admin.get("/api/v1/sales/due").get_json()["items"]
    assert len(due) == 1 and due[0]["total_cents"] == 85000
    sale = db.session.get(Sale, due[0]["id"])
    assert sale.lease_id == lease["id"] and [l.account.code for l in sale.lines] == ["706", "708"]
    assert sale.lines[0].label.startswith("Loyer ") and sale.lines[0].label.endswith("— Appartement 2B")
    admin.post("/api/v1/sales/issue-batch", json={"ids": [sale.id]})

    bank = BankAccount.query.one()
    resp = admin.post(f"/api/v1/leases/{lease['id']}/deposit", json={"paid_on": TODAY.isoformat(), "bank_account_id": bank.id})
    assert resp.status_code == 200, resp.get_json()
    entry = db.session.get(JournalEntry, Lease.query.one().deposit_entry_id)
    assert sorted((l.account.code, l.debit_cents, l.credit_cents) for l in entry.lines) == [("165", 0, 160000), ("512", 160000, 0)]
    assert admin.post(f"/api/v1/leases/{lease['id']}/deposit", json={"bank_account_id": bank.id}).status_code == 409

    # Rien de payé : pas de quittance. Paiement partiel : reçu. Solde : quittance.
    assert admin.post(f"/api/v1/sales/{sale.id}/rent-receipt").status_code == 409
    admin.post(f"/api/v1/sales/{sale.id}/payments", json={"amount": "500", "bank_account_id": bank.id})
    recu = admin.post(f"/api/v1/sales/{sale.id}/rent-receipt").get_json()["item"]
    assert recu["kind"] == "recu" and recu["paid_cents"] == 50000
    admin.post(f"/api/v1/sales/{sale.id}/payments", json={"amount": "350", "bank_account_id": bank.id})
    quittance = admin.post(f"/api/v1/sales/{sale.id}/rent-receipt").get_json()["item"]
    assert quittance["kind"] == "quittance" and quittance["paid_cents"] == 85000
    row = db.session.get(RentReceipt, quittance["id"])
    assert (row.rent_cents, row.charges_cents) == (80000, 5000)
    pdf = admin.get(quittance["pdf_url"])
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF")
    again = admin.post(f"/api/v1/sales/{sale.id}/rent-receipt").get_json()["item"]
    assert again["id"] == quittance["id"]  # même pièce, pas de doublon
    detail = admin.get(f"/api/v1/leases/{lease['id']}").get_json()["item"]
    assert [r["kind"] for r in detail["receipts"]] == ["quittance", "recu"] and detail["invoices"][0]["status"] == "paid"

    sent = []

    class FakeSMTP:
        def send_message(self, message):
            sent.append(message)

        def quit(self):
            pass
    from app.services import membership_reminders
    monkeypatch.setattr(membership_reminders, "_open_smtp", lambda settings, timeout=20: FakeSMTP())
    external_config.set_enabled("smtp", True)
    assert admin.post(f"/api/v1/rent-receipts/{quittance['id']}/send", json={}).status_code == 200
    assert sent[0]["To"] == "martin@example.org" and sent[0]["Subject"].startswith("Quittance de loyer")


def test_lease_requires_rent_and_unit(admin):
    resp = admin.post("/api/v1/leases", json={"entity_id": _tenant().id, "start_date": TODAY.isoformat(), "rent": "800"})
    assert resp.status_code == 422
    resp = admin.post("/api/v1/leases", json={"entity_id": _tenant().id, "unit_label": "Garage", "start_date": TODAY.isoformat()})
    assert resp.status_code == 422 and "Loyer" in resp.get_json()["error"]["message"]
    assert Lease.query.count() == 0 and Recurrence.query.count() == 0
