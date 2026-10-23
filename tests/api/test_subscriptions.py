"""Achats, lot S6 : abonnements (échéances attendues créées une fois, facture et prélèvement
rattachés, échéance manquante, rattachement à la main, ignorée), coûts et rappel de préavis."""
from datetime import date, timedelta

import pytest

from app.extensions import db
from app.models import Account, BankAccount, BankTransaction, Entity, Purchase, SubscriptionPeriod
from app.services import recurrence, subscriptions

TODAY = date.today()
API = "/api/v1/subscriptions"


@pytest.fixture()
def admin(app, login_as):
    client = login_as(role="admin")
    bank = Account(code="512", label="Banque", account_type="TRESORERIE")
    db.session.add_all([bank, Entity(name="Orange SA", entity_type="FOURNISSEUR")])
    db.session.flush()
    db.session.add(BankAccount(label="Banque", kind="bank", account_id=bank.id))
    db.session.commit()
    return client


def _orange():
    return Entity.query.filter_by(name="Orange SA").one()


def _create(admin, **fields):
    start = recurrence.add_months(TODAY.replace(day=1), -3, 1)
    body = {"label": "Box internet", "entity_id": _orange().id, "category": "internet", "amount": "45",
            "amount_fixed": True, "frequency": "monthly", "due_day": 5, "start_date": start.isoformat(), **fields}
    resp = admin.post(API, json=body)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["item"]


def test_periods_and_matching(admin):
    sub = _create(admin)
    periods = sorted(sub["periods"], key=lambda p: p["due_date"])
    assert len(periods) in (3, 4)  # 3 mois passés, et ce mois-ci si le 5 est passé
    assert periods[0]["status"] == "missing" and periods[0]["expected_cents"] == 4500
    # Facture du fournisseur et prélèvement du même montant autour de la première échéance.
    first = date.fromisoformat(periods[0]["due_date"])
    db.session.add(Purchase(source="manual", entity_id=_orange().id, issue_date=first - timedelta(days=2), total_cents=4500,
                            invoice_number="FAC-1"))
    db.session.add(BankTransaction(bank_account_id=BankAccount.query.one().id, fitid="P1", transaction_date=first + timedelta(days=3),
                                   amount_cents=-4500, label="PRLV SEPA ORANGE SA", source="ofx"))
    db.session.commit()
    detail = admin.get(f"{API}/{sub['id']}").get_json()["item"]
    matched = next(p for p in detail["periods"] if p["due_date"] == first.isoformat())
    assert matched["status"] == "paid" and matched["purchase"]["number"] == "FAC-1" and matched["transaction"]["amount_cents"] == -4500
    # Idempotent : pas de nouvelle échéance ni de double rattachement.
    again = admin.get(f"{API}/{sub['id']}").get_json()["item"]
    assert len(again["periods"]) == len(detail["periods"])
    assert SubscriptionPeriod.query.filter(SubscriptionPeriod.purchase_id.isnot(None)).count() == 1


def test_estimated_amount_and_manual_link(admin):
    sub = _create(admin, amount_fixed=False, amount="100", label="Électricité", category="energy")
    period = min(sub["periods"], key=lambda p: p["due_date"])
    due = date.fromisoformat(period["due_date"])
    db.session.add(Purchase(source="manual", entity_id=_orange().id, issue_date=due, total_cents=11800, invoice_number="E-1"))
    db.session.add(Purchase(source="manual", entity_id=_orange().id, issue_date=due + timedelta(days=60), total_cents=50000,
                            invoice_number="AUTRE"))
    db.session.commit()
    detail = admin.get(f"{API}/{sub['id']}").get_json()["item"]
    first = next(p for p in detail["periods"] if p["due_date"] == period["due_date"])
    assert first["status"] == "invoiced" and first["purchase"]["number"] == "E-1"  # 118 € à ±30 % de 100 €
    other = next(p for p in detail["periods"] if p["status"] == "missing" and p["id"] != first["id"])
    options = admin.get(f"/api/v1/subscription-periods/{other['id']}/candidates").get_json()
    assert options["purchases"]
    big = Purchase.query.filter_by(invoice_number="AUTRE").one()
    resp = admin.post(f"/api/v1/subscription-periods/{other['id']}/link", json={"purchase_id": big.id})
    assert resp.status_code == 200
    assert admin.post(f"/api/v1/subscription-periods/{first['id']}/link", json={"purchase_id": big.id}).status_code == 409
    skipped = admin.post(f"/api/v1/subscription-periods/{other['id']}/skip", json={"skipped": True}).get_json()["item"]
    assert next(p for p in skipped["periods"] if p["id"] == other["id"])["status"] == "skipped"


def test_summary_and_notice_alert(admin):
    _create(admin)  # 45 €/mois
    _create(admin, label="Assurance", category="insurance", amount="600", frequency="yearly",
            renewal_date=(TODAY + timedelta(days=60)).isoformat(), notice_days=30)
    body = admin.get(API).get_json()
    summary = body["meta"]["summary"]
    assert summary["monthly_cents"] == 4500 + 5000 and summary["yearly_cents"] == (4500 + 5000) * 12
    assert [c["category"] for c in summary["by_category"]] == ["insurance", "internet"]
    insurance = next(s for s in body["items"] if s["label"] == "Assurance")
    assert insurance["notice_deadline"] == (TODAY + timedelta(days=30)).isoformat() and insurance["notice_alert"] is True
    assert summary["notice_alerts"] == 1


def test_update_keeps_linked_periods(admin):
    sub = _create(admin)
    period = SubscriptionPeriod.query.order_by(SubscriptionPeriod.due_date).first()
    subscriptions.skip(period)
    resp = admin.patch(f"{API}/{sub['id']}", json={"amount": "50"})
    assert resp.status_code == 200
    amounts = {p["expected_cents"] for p in resp.get_json()["item"]["periods"] if p["status"] != "skipped"}
    assert amounts == {5000}
    assert admin.post(API, json={"label": "", "entity_id": _orange().id, "amount": "10"}).status_code == 422
