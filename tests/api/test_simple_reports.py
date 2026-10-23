"""Lot D.4 : compte de résultat simplifié (catégories, N / N-1), situation de trésorerie cumulée,
verrouillage d'exercice en mode simple."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, BankAccount, FiscalYear, Instance, Journal
from app.services.ledger import post_entry

def _error(resp, status):
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()["error"]

@pytest.fixture()
def books(app):
    prev = FiscalYear(label="2025", start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    accounts = {c: Account(code=c, label=f"Compte {c}", account_type="OTHER") for c in ("512", "530", "756", "6061", "6288")}
    db.session.add_all([prev, fy, Journal(code="BQ", label="Banque"), *accounts.values()])
    db.session.commit()
    ids = {c: a.id for c, a in accounts.items()}
    db.session.add_all([BankAccount(label="CIC", account_id=ids["512"]),
                        BankAccount(label="Caisse", account_id=ids["530"], kind="cash")])
    db.session.commit()
    bq = Journal.query.one().id

    def op(year, day, treasury, account, cents):
        income = account.startswith("7")
        post_entry(year.id, bq, day, "Op", [
            {"account_id": ids[treasury], "debit_cents": cents if income else 0, "credit_cents": 0 if income else cents},
            {"account_id": ids[account], "debit_cents": 0 if income else cents, "credit_cents": cents if income else 0}])
    op(prev, date(2025, 5, 1), "512", "756", 10000)
    op(prev, date(2025, 6, 1), "512", "6061", 4000)
    op(fy, date(2026, 2, 1), "512", "756", 15000)
    op(fy, date(2026, 3, 1), "530", "756", 2000)
    op(fy, date(2026, 4, 1), "512", "6061", 3000)
    op(fy, date(2026, 4, 2), "512", "6288", 500)        # sans catégorie : sous son numéro
    return {"prev": prev, "fy": fy}

def test_income_statement(books, login_as):
    data = login_as().get(f"/api/v1/simple/reports/income-statement?fiscal_year_id={books['fy'].id}").get_json()

    rows = {r["label"]: (r["kind"], r["amount_cents"], r["previous_cents"]) for r in data["rows"]}
    assert rows["Cotisations"] == ("income", 17000, 10000)
    assert rows["Achats et fournitures"] == ("expense", 3000, 4000)
    assert rows["6288 Compte 6288"] == ("expense", 500, 0)
    assert data["result"] == {"amount_cents": 17000 - 3500, "previous_cents": 6000}
    assert data["previous_year"] == "2025" and [r["kind"] for r in data["rows"]][0] == "income"

def test_treasury_situation_is_cumulative(books, login_as):
    data = login_as().get(f"/api/v1/simple/reports/treasury?fiscal_year_id={books['fy'].id}").get_json()
    rows = {r["label"]: r for r in data["rows"]}
    assert (rows["CIC"]["start_cents"], rows["CIC"]["end_cents"]) == (6000, 6000 + 15000 - 3500)
    assert (rows["Caisse"]["start_cents"], rows["Caisse"]["end_cents"]) == (0, 2000)
    assert data["total"]["change_cents"] == data["result_cents"] == 13500

def test_lock_in_simple_mode(books, login_as):
    client = login_as(role="treasurer")
    url = f"/api/v1/fiscal-years/{books['fy'].id}/lock"
    assert "assistant" in _error(client.post(url, json={"locked": True}), 409)["message"]  # partie double
    Instance.query.one().bookkeeping = "simple"
    db.session.commit()
    assert client.post(url, json={"locked": True}).get_json()["item"]["status"] == "closed"
    _error(client.post(url, json={"locked": False}), 403)                      # déverrouiller : admin
    _error(client.post(f"/api/v1/fiscal-years/{books['fy'].id}/close", json={}), 409)  # pas d'assistant

def test_admin_unlocks(books, login_as):
    client = login_as(role="admin")
    Instance.query.one().bookkeeping = "simple"
    db.session.commit()
    url = f"/api/v1/fiscal-years/{books['fy'].id}/lock"
    client.post(url, json={"locked": True})
    assert client.post(url, json={"locked": False}).get_json()["item"]["status"] == "open"
