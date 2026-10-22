"""Lot C.4 : prévisionnel de trésorerie sur 12 mois glissants — soldes de départ, factures non
réglées, budget restant, saisies manuelles répétées, alerte de solde négatif."""
from datetime import date

import pytest

from app.extensions import db
from app.models import (
    Account, BankAccount, BankTransaction, CashForecastItem, CustomerInvoice, Entity, FiscalYear, Journal, Purchase,
)
from app.services import budget, cash_forecast
from app.services.ledger import post_entry

TODAY = date(2026, 10, 15)


def _error(resp, status):
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()["error"]


@pytest.fixture()
def books(app):
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    accounts = {c: Account(code=c, label=f"Compte {c}", account_type="OTHER")
                for c in ("512", "530", "606", "6811", "706", "110")}
    db.session.add_all([fy, Journal(code="BQ", label="Banque"), Journal(code="AN", label="À-nouveaux"),
                        *accounts.values()])
    db.session.commit()
    ids = {c: a.id for c, a in accounts.items()}
    ba = BankAccount(label="CIC", account_id=ids["512"])
    db.session.add(ba)
    db.session.commit()
    bq, an = Journal.query.filter_by(code="BQ").one().id, Journal.query.filter_by(code="AN").one().id
    # Les à-nouveaux reprennent un solde déjà compté : exclus.
    post_entry(fy.id, an, date(2026, 1, 1), "AN", [{"account_id": ids["512"], "debit_cents": 999999},
                                                     {"account_id": ids["110"], "credit_cents": 999999}],
               source="OPENING")
    post_entry(fy.id, bq, date(2026, 3, 1), "Vente", [{"account_id": ids["512"], "debit_cents": 100000},
                                                       {"account_id": ids["706"], "credit_cents": 100000}])
    post_entry(fy.id, bq, date(2026, 10, 2), "Achat", [{"account_id": ids["606"], "debit_cents": 20000},
                                                        {"account_id": ids["512"], "credit_cents": 20000}])
    post_entry(fy.id, bq, date(2026, 11, 2), "Futur", [{"account_id": ids["606"], "debit_cents": 1},
                                                        {"account_id": ids["512"], "credit_cents": 1}])
    post_entry(fy.id, bq, date(2026, 4, 1), "Caisse", [{"account_id": ids["530"], "debit_cents": 5000},
                                                        {"account_id": ids["706"], "credit_cents": 5000}])
    db.session.add(BankTransaction(bank_account_id=ba.id, fitid="U1", transaction_date=date(2026, 10, 10),
                                   amount_cents=-3000, label="CB non saisie"))
    return {"fy": fy, "ba": ba, **ids}


def test_opening_balances(books):
    accounts = {a["account"]: a for a in cash_forecast.balances(TODAY)}
    assert accounts["512"] == {"label": "CIC", "account": "512", "ledger_cents": 80000, "unbooked_cents": -3000,
                               "balance_cents": 77000}
    assert accounts["530"]["balance_cents"] == 5000


def test_forecast_months(books, login_as):
    fy = books["fy"]
    entity = Entity(name="EDF", entity_type="FOURNISSEUR")
    db.session.add_all([
        Purchase(source="manual", invoice_number="F-OLD", issue_date=date(2026, 8, 1), due_date=date(2026, 9, 1),
                 total_cents=15000, entity=entity),                                 # échue : mois en cours
        Purchase(source="manual", invoice_number="F-DEC", issue_date=date(2026, 10, 1), due_date=date(2026, 12, 5),
                 total_cents=4000, entity=entity),
        Purchase(source="qonto", qonto_id="q1", invoice_number="F-PAID", issue_date=date(2026, 10, 1),
                 total_cents=7000, qonto_status="paid", entity=entity),
        Purchase(source="manual", invoice_number="AV-1", issue_date=date(2026, 10, 1), total_cents=500,
                 is_credit_note=True, entity=entity),
        CustomerInvoice(odoo_id=1, name="FAC/1", state="posted", partner_name="Mairie", invoice_date=date(2026, 10, 1),
                        invoice_date_due=date(2026, 11, 30), amount_total_cents=60000, amount_residual_cents=60000),
        CustomerInvoice(odoo_id=2, name="FAC/2", state="posted", invoice_date=date(2026, 9, 1), amount_residual_cents=0),
        CashForecastItem(date=date(2026, 11, 5), label="Loyer", amount_cents=-80000, repeat_monthly_until=date(2027, 2, 28)),
        CashForecastItem(date=date(2026, 6, 5), label="Passé", amount_cents=-1),
    ])
    budget.save(fy, None, [{"account_id": books["606"], "months": [30000] * 12},
                           {"account_id": books["6811"], "annual_cents": 120000},  # dotation : sans trésorerie
                           {"account_id": books["706"], "months": [10000] * 12}])
    db.session.commit()
    data = login_as().get("/api/v1/cash-forecast?today=2026-10-15").get_json()
    assert data["opening_cents"] == 77000 + 5000
    months = data["months"]
    assert [m["month"] for m in months][:3] == ["2026-10-01", "2026-11-01", "2026-12-01"] and len(months) == 12
    oct_, nov, dec, jan = months[0], months[1], months[2], months[3]
    # Octobre : facture échue + budget restant (30 000 − 20 000 réalisés), produits du mois (aucun réalisé).
    assert oct_["outflows"]["purchases"] == 15000 and oct_["inflows"]["purchases"] == 500
    assert oct_["outflows"]["budget"] == 10000 and oct_["inflows"]["budget"] == 10000
    assert nov["inflows"]["customers"] == 60000 and nov["outflows"]["manual"] == 80000
    assert nov["outflows"]["budget"] == 30000  # 6811 exclu
    assert dec["outflows"]["purchases"] == 4000
    assert jan["outflows"]["budget"] == 0 and jan["outflows"]["manual"] == 80000  # pas de budget 2027
    assert months[5]["outflows"]["manual"] == 0  # répétition jusqu'en février
    assert oct_["closing_cents"] == 82000 - 15000 + 500 - 10000 + 10000
    assert nov["opening_cents"] == oct_["closing_cents"]
    assert data["first_negative"]["month"] == "2026-12-01"
    assert any(d["label"] == "EDF — F-OLD" and d["url"].startswith("/purchases/") for d in oct_["details"])


def test_manual_items_crud(books, login_as):
    client = login_as()
    created = client.post("/api/v1/cash-forecast/items", json={
        "date": "2026-11-01", "label": "Subvention", "amount_cents": 500000, "bank_account_id": books["ba"].id})
    assert created.status_code == 201
    item_id = created.get_json()["item"]["id"]
    _error(client.post("/api/v1/cash-forecast/items", json={"date": "2026-11-01", "label": "X", "amount_cents": 0}), 422)
    _error(client.post("/api/v1/cash-forecast/items", json={"label": "X", "amount_cents": 5}), 422)
    _error(client.post("/api/v1/cash-forecast/items", json={"date": "2026-11-01", "label": "X", "amount_cents": 5,
                                                            "repeat_monthly_until": "2026-01-01"}), 422)
    assert client.put(f"/api/v1/cash-forecast/items/{item_id}", json={
        "date": "2026-12-01", "label": "Subvention région", "amount_cents": 400000}).status_code == 200
    assert client.get("/api/v1/cash-forecast?today=2026-10-15").get_json()["items"][0]["label"] == "Subvention région"
    assert client.delete(f"/api/v1/cash-forecast/items/{item_id}").status_code == 200
    assert CashForecastItem.query.count() == 0


def test_accountant_reads_only(books, login_as):
    client = login_as(role="accountant")
    assert client.get("/api/v1/cash-forecast").status_code == 200
    _error(client.post("/api/v1/cash-forecast/items", json={}), 403)
