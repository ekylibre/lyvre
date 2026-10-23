"""Module « Associés », lot A3 : facture réglée par un associé, notes de frais, apport par la
banque, relevé et soldes par exercice."""
import io
import json
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, BankAccount, BankTransaction, Entity, FiscalYear, Instance, Journal, JournalEntry, Purchase
from app.services import associates, purchase_entry
from werkzeug.datastructures import MultiDict


@pytest.fixture()
def books(app, login_as, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "instance_path", str(tmp_path))
    client = login_as(role="treasurer")
    Instance.query.one().has_associates = True
    for code, label, kind in (("455", "Associés", "TIERS"), ("401", "Fournisseurs", "TIERS"),
                              ("44566", "TVA déductible", "TIERS"), ("6061", "Fournitures non stockables", "EXPENSE"),
                              ("6068", "Autres achats", "EXPENSE"), ("512", "Banque", "BANK")):
        db.session.add(Account(code=code, label=label, account_type=kind))
    db.session.add_all([FiscalYear(label="2025", start_date=date(2025, 1, 1), end_date=date(2025, 12, 31)),
                        FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), vat_liable=True),
                        Journal(code="AC", label="Achats"), Journal(code="BQ", label="Banque")])
    db.session.commit()
    return client


def _invoice(total="70,59", untaxed="58,83", tax="11,76"):
    clean, errors = purchase_entry.validate_header(MultiDict({
        "entity_id": "new", "new_name": "EDF", "supplier_name": "EDF", "supplier_vat": "", "supplier_siret": "",
        "supplier_iban": "", "invoice_number": "10237045906", "issue_date": "2026-10-10", "due_date": "",
        "total": total, "untaxed": untaxed, "tax": tax}))
    assert errors == []
    p, outcome = purchase_entry.create(clean, [{"product_id": "", "account_code": "6061", "label": "Électricité",
                                                "untaxed": untaxed, "vat_rate": "20", "vat": tax}])
    assert outcome["posted"] == 1
    return p


def _lines(entry):
    return sorted((l.account.code, l.debit_cents, l.credit_cents) for l in entry.lines)


def test_invoice_paid_by_associate(books):
    lola = associates.create({"new_name": "Lola"})
    p = _invoice()
    detail = books.get(f"/api/v1/purchases/{p.id}").get_json()
    assert detail["associate_payment"]["blocker"] is None
    assert detail["associate_payment"]["associates"] == [{"value": str(lola.id), "label": "Lola"}]

    paid = books.post(f"/api/v1/purchases/{p.id}/associate-payment", json={"associate_id": lola.id, "paid_on": "2026-10-12"})
    assert paid.status_code == 200, paid.get_json()
    payment = Purchase.query.get(p.id).payments[0]
    entry = payment.journal_entry
    assert (payment.origin, payment.associate_id) == ("associate", lola.id)
    assert entry.journal.code == "AS" and entry.source == "ASSOCIATE" and entry.entry_date == date(2026, 10, 12)
    assert _lines(entry) == [("401001", 7059, 0), ("4551001", 0, 7059)]
    assert associates.balance(lola.account_id) == 7059  # la société doit 70,59 € à Lola

    detail = books.get(f"/api/v1/purchases/{p.id}").get_json()
    assert detail["awaiting_payment"] is False
    assert detail["payments"][0]["associate"]["name"] == "Lola" and detail["payments"][0]["status"] == "settled"
    assert "règlement" in detail["associate_payment"]["blocker"]
    again = books.post(f"/api/v1/purchases/{p.id}/associate-payment", json={"associate_id": lola.id, "paid_on": "2026-10-12"})
    assert again.status_code == 422

    statement = books.get(f"/api/v1/associates/{lola.id}/statement").get_json()
    assert statement["lines"][0]["origin"] == "Facture réglée" and statement["closing_cents"] == 7059

    undone = books.delete(f"/api/v1/purchases/{p.id}/payments/{payment.id}")
    assert undone.status_code == 200, undone.get_json()
    assert Purchase.query.get(p.id).payments == [] and associates.balance(lola.account_id) == 0
    assert JournalEntry.query.filter_by(source="ASSOCIATE").count() == 0


def test_payment_refused(books):
    lola = associates.create({"new_name": "Lola"})
    p = _invoice()
    for body, field in (({"associate_id": 999, "paid_on": "2026-10-12"}, "associate_id"),
                        ({"associate_id": lola.id, "paid_on": "2030-01-01"}, "paid_on"),
                        ({"associate_id": lola.id, "paid_on": "x"}, "paid_on")):
        resp = books.post(f"/api/v1/purchases/{p.id}/associate-payment", json=body)
        assert resp.status_code == 422 and field in resp.get_json()["error"]["fields"], body
    Instance.query.one().has_associates = False
    db.session.commit()
    assert books.post(f"/api/v1/purchases/{p.id}/associate-payment", json={}).status_code == 404
    assert books.get(f"/api/v1/purchases/{p.id}").get_json()["associate_payment"] is None


def test_paid_by_associate_when_entering_the_invoice(books, monkeypatch):
    lola = associates.create({"new_name": "Lola"})
    from app.api import purchases as api_purchases
    monkeypatch.setattr(api_purchases, "_validated", lambda data: purchase_entry.validate_header(MultiDict({
        "entity_id": "new", "new_name": "EDF", "supplier_name": "EDF", "supplier_vat": "", "supplier_siret": "",
        "supplier_iban": "", "invoice_number": "F1", "issue_date": "2026-10-10", "due_date": "",
        "total": "12,00", "untaxed": "10,00", "tax": "2,00"}))[0:1] + (None,))
    resp = books.post("/api/v1/purchases", json={
        "rows": [{"product_id": "", "account_code": "6061", "label": "x", "untaxed": "10,00", "vat_rate": "20", "vat": "2,00"}],
        "paid_by_associate": {"associate_id": lola.id, "paid_on": "2026-10-11"}})
    assert resp.status_code == 201, resp.get_json()
    assert any("associé" in n["message"] for n in resp.get_json()["notices"])
    assert associates.balance(lola.account_id) == 1200


def test_expense_with_vat_and_receipt(books):
    lola = associates.create({"new_name": "Lola"})
    payload = {"associate_id": lola.id, "expense_date": "2026-03-04", "label": "Ampoules",
               "account_code": "6068", "untaxed": "10,00", "vat_rate": "20"}
    resp = books.post("/api/v1/associate-expenses", data={
        "payload": json.dumps(payload), "attachment": (io.BytesIO(b"%PDF-1.4 ticket"), "ticket.pdf")},
        content_type="multipart/form-data")
    assert resp.status_code == 201, resp.get_json()
    item = resp.get_json()["item"]
    assert (item["untaxed_cents"], item["vat_cents"], item["total_cents"]) == (1000, 200, 1200)
    entry = JournalEntry.query.get(item["entry"]["id"])
    assert _lines(entry) == [("44566", 200, 0), ("4551001", 0, 1200), ("6068", 1000, 0)]
    assert books.get(item["attachment"]["url"]).data == b"%PDF-1.4 ticket"
    assert books.get("/api/v1/associate-expenses").get_json()["items"][0]["label"] == "Ampoules"

    errors = books.post("/api/v1/associate-expenses", json={**payload, "account_code": "512"})
    assert errors.status_code == 422 and "account_code" in errors.get_json()["error"]["fields"]
    assert books.delete(f"/api/v1/associate-expenses/{item['id']}").status_code == 200
    assert associates.balance(lola.account_id) == 0


def test_bank_contribution_prefilled(books):
    lola = associates.create({"new_name": "Lola"})
    bank = BankAccount(label="Compte", account_id=Account.query.filter_by(code="512").one().id)
    db.session.add(bank)
    db.session.flush()
    for fitid, amount in (("a", 300000), ("b", -50000)):
        db.session.add(BankTransaction(bank_account_id=bank.id, fitid=fitid, transaction_date=date(2026, 5, 2),
                                       amount_cents=amount, label="VIR LOLA"))
    db.session.commit()
    inflow, outflow = BankTransaction.query.order_by(BankTransaction.fitid).all()
    form = books.get(f"/api/v1/entries/form?bt_id={inflow.id}&associate_id={lola.id}").get_json()
    lines = [(l["account"]["code"], l["debit_cents"], l["credit_cents"]) for l in form["initial"]["lines"]]
    assert lines == [("512", 300000, 0), ("4551001", 0, 300000)]
    form = books.get(f"/api/v1/entries/form?bt_id={outflow.id}&associate_id={lola.id}").get_json()
    assert [(l["account"]["code"], l["debit_cents"], l["credit_cents"]) for l in form["initial"]["lines"]] == [
        ("512", 0, 50000), ("4551001", 50000, 0)]


def test_balances_by_year(books):
    lola = associates.create({"new_name": "Lola"})
    p = _invoice()
    books.post(f"/api/v1/purchases/{p.id}/associate-payment", json={"associate_id": lola.id, "paid_on": "2026-10-12"})
    chart = books.get("/api/v1/associates/balances-by-year").get_json()
    assert chart == {"years": ["2025", "2026"], "series": [{"name": "Lola", "values": [0, 7059]}]}


def test_expense_without_entity_name_clash(books):
    # Une entité homonyme du fournisseur n'empêche pas de l'utiliser comme associé.
    db.session.add(Entity(name="EDF", entity_type="FOURNISSEUR"))
    db.session.commit()
    assert associates.create({"new_name": "EDF"}).entity.entity_type == "FOURNISSEUR"
