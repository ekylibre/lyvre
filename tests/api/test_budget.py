"""Lot C.2 : budget — grille annuelle ou mensuelle par compte, globale ou par projet,
enregistrement puis rechargement, contrôles, copie de l'exercice précédent."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, BudgetLine, FiscalYear, Journal, Project
from app.services import budget
from app.services.ledger import post_entry


def _error(resp, status):
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()["error"]


@pytest.fixture()
def books(app):
    prev = FiscalYear(label="2025", start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    accounts = {c: Account(code=c, label=f"Compte {c}", account_type="OTHER")
                for c in ("60", "606", "6061", "6063", "64", "641", "706", "74", "512")}
    db.session.add_all([prev, fy, Journal(code="BQ", label="Banque"), Project(name="Jardin"), *accounts.values()])
    db.session.commit()
    return {"prev": prev, "fy": fy, **{c: a.id for c, a in accounts.items()}}


def test_months_and_spread(books):
    assert [m["label"] for m in budget.months(books["fy"])][:3] == ["janv. 26", "févr. 26", "mars 26"]
    odd = FiscalYear(label="X", start_date=date(2026, 7, 1), end_date=date(2027, 12, 31))
    assert len(budget.months(odd)) == 18
    assert budget.spread(1000, 12) == [84] * 4 + [83] * 8 and sum(budget.spread(1000, 12)) == 1000


def test_save_and_reload(books, login_as):
    client = login_as()
    url = f"/api/v1/budgets/{books['fy'].id}"
    monthly = [10000] * 6 + [0] * 6
    body = {"project_id": None, "rows": [
        {"account_id": books["606"], "annual_cents": 120000},
        {"account_id": books["641"], "months": monthly},
        {"account_id": books["706"], "annual_cents": 300000},
        {"account_id": books["74"], "annual_cents": 0}]}  # ligne vide ignorée
    saved = client.put(url, json=body).get_json()
    assert saved["totals"] == {"expense_cents": 180000, "income_cents": 300000, "result_cents": 120000}
    reloaded = client.get(url).get_json()
    rows = {r["code"]: r for r in reloaded["rows"]}
    assert list(rows) == ["606", "641", "706"]
    assert rows["606"]["mode"] == "annual" and rows["606"]["months"] == [10000] * 12
    assert rows["641"]["mode"] == "monthly" and rows["641"]["months"] == monthly
    assert BudgetLine.query.count() == 1 + 6 + 1
    assert "60 — Compte 60" in [a["label"] for a in reloaded["accounts"]]  # regroupements proposés
    # Budget du projet : périmètre distinct, le budget général n'est pas touché.
    jardin = Project.query.one().id
    client.put(url, json={"project_id": jardin, "rows": [{"account_id": books["6061"], "annual_cents": 5000}]})
    assert [r["code"] for r in client.get(f"{url}?project_id={jardin}").get_json()["rows"]] == ["6061"]
    assert len(client.get(url).get_json()["rows"]) == 3
    # Enregistrer une grille vide la vide.
    client.put(url, json={"project_id": None, "rows": []})
    assert client.get(url).get_json()["rows"] == []
    assert "budget" in _error(client.delete(f"/api/v1/projects/{jardin}"), 409)["message"]


def test_validation(books, login_as):
    client = login_as()
    url = f"/api/v1/budgets/{books['fy'].id}"
    put = lambda rows: client.put(url, json={"rows": rows})  # noqa: E731
    assert "regroupe" in _error(put([{"account_id": books["60"], "annual_cents": 1},
                                     {"account_id": books["6063"], "annual_cents": 1}]), 422)["message"]
    _error(put([{"account_id": books["606"], "annual_cents": 1}, {"account_id": books["606"], "annual_cents": 2}]), 422)
    assert _error(put([{"account_id": books["512"], "annual_cents": 1}]), 422)["fields"] == {
        "rows[0].account_id": "Compte 512 : compte de charge (6) ou de produit (7) attendu."}
    _error(put([{"account_id": books["606"], "months": [1, 2]}]), 422)
    _error(put([{"account_id": books["606"], "annual_cents": -5}]), 422)
    _error(client.get(f"{url}?project_id=999"), 422)
    _error(client.put(url, json={"rows": "x"}), 422)


def test_accountant_reads_only(books, login_as):
    client = login_as(role="accountant")
    assert client.get(f"/api/v1/budgets/{books['fy'].id}").status_code == 200
    _error(client.put(f"/api/v1/budgets/{books['fy'].id}", json={"rows": []}), 403)


def test_copy_from_previous_year(books, login_as):
    client = login_as()
    prev, fy = books["prev"], books["fy"]
    budget.save(prev, None, [{"account_id": books["606"], "months": [500] * 12},
                             {"account_id": books["706"], "annual_cents": 9000}])
    bq = Journal.query.one().id
    post_entry(prev.id, bq, date(2025, 2, 10), "Graines", [
        {"account_id": books["6061"], "debit_cents": 1200}, {"account_id": books["512"], "credit_cents": 1200}])
    post_entry(prev.id, bq, date(2025, 2, 20), "Outils", [
        {"account_id": books["6063"], "debit_cents": 800}, {"account_id": books["512"], "credit_cents": 800}])
    post_entry(prev.id, bq, date(2025, 5, 2), "Vente", [
        {"account_id": books["512"], "debit_cents": 4000}, {"account_id": books["706"], "credit_cents": 4000}])
    url = f"/api/v1/budgets/{fy.id}/copy"
    from_budget = {r["code"]: r for r in client.get(f"{url}?source=budget").get_json()["rows"]}
    assert from_budget["606"]["months"] == [500] * 12 and from_budget["706"]["annual_cents"] == 9000
    actual = client.get(f"{url}?source=actual").get_json()
    rows = {r["code"]: r for r in actual["rows"]}
    assert set(rows) == {"606", "706"}  # 6061 et 6063 regroupés sous 606
    assert rows["606"]["months"][1] == 2000 and rows["606"]["total_cents"] == 2000
    assert rows["706"]["months"][4] == 4000
    assert actual["previous_fiscal_year"] == "2025"
    assert BudgetLine.query.filter_by(fiscal_year_id=fy.id).count() == 0  # rien d'enregistré
    _error(client.get(f"/api/v1/budgets/{prev.id}/copy?source=actual"), 422)  # pas d'exercice avant 2025
    _error(client.get(f"{url}?source=autre"), 422)
