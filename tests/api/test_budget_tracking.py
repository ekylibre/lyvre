"""Lot C.3 : suivi budgétaire (prévu / réalisé / écart à date, par préfixe et projet, hors budget),
export tableur, compte de résultat d'un projet sur une période."""
from datetime import date
from io import BytesIO

import pytest
from openpyxl import load_workbook

from app.extensions import db
from app.models import Account, Entity, FiscalYear, Journal, JournalLine, Project, Purchase
from app.services import budget
from app.services.ledger import post_entry


def _error(resp, status):
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()["error"]


@pytest.fixture()
def books(app):
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    accounts = {c: Account(code=c, label=f"Compte {c}", account_type="OTHER")
                for c in ("60", "6061", "6063", "613", "6132", "706", "74", "512")}
    db.session.add_all([fy, Journal(code="BQ", label="Banque"), Project(name="Jardin"), *accounts.values()])
    db.session.commit()
    ids = {c: a.id for c, a in accounts.items()}
    jardin = Project.query.one()
    bq = Journal.query.one().id

    def entry(day, debit, credit, cents, project=None):
        return post_entry(fy.id, bq, day, "Op", [
            {"account_id": ids[debit], "debit_cents": cents, "project_id": project if debit[0] in "67" else None},
            {"account_id": ids[credit], "credit_cents": cents, "project_id": project if credit[0] in "67" else None}])

    entry(date(2026, 1, 15), "6061", "512", 3000, jardin.id)
    entry(date(2026, 2, 10), "6063", "512", 2000)
    entry(date(2026, 3, 5), "6132", "512", 5000)       # hors budget (613)
    entry(date(2026, 2, 20), "512", "706", 4000, jardin.id)
    entry(date(2026, 7, 1), "6061", "512", 9999)        # après la date de suivi
    budget.save(fy, None, [{"account_id": ids["60"], "annual_cents": 120000},
                           {"account_id": ids["706"], "months": [1000] * 12}])
    budget.save(fy, jardin, [{"account_id": ids["6061"], "annual_cents": 12000}])
    return {"fy": fy, "jardin": jardin, **ids}


def test_tracking_to_date(books, login_as):
    client = login_as()
    data = client.get(f"/api/v1/budgets/{books['fy'].id}/tracking?as_of=2026-03-15").get_json()
    assert data["elapsed_months"] == 3 and data["as_of"] == "2026-03-15"
    rows = {r["code"]: r for r in data["rows"]}
    assert rows["60"] == {**rows["60"], "planned_cents": 120000, "planned_to_date_cents": 30000,
                          "actual_cents": 5000, "gap_cents": -25000, "rate": 16.7, "unbudgeted": False}
    assert rows["706"]["planned_to_date_cents"] == 3000 and rows["706"]["actual_cents"] == 4000
    assert rows["613"]["unbudgeted"] and rows["613"]["actual_cents"] == 5000 and rows["613"]["rate"] is None
    assert [r["code"] for r in data["rows"]] == ["60", "613", "706"]  # charges budgétées, hors budget, produits
    assert data["summary"]["expense"]["actual_cents"] == 10000
    assert data["summary"]["result"]["actual_cents"] == 4000 - 10000
    assert data["export_url"].startswith("/budget/tracking.xlsx?fiscal_year_id=")


def test_tracking_by_project_and_bounds(books, login_as):
    client = login_as()
    url = f"/api/v1/budgets/{books['fy'].id}/tracking"
    data = client.get(f"{url}?project_id={books['jardin'].id}&as_of=2026-02-28").get_json()
    rows = {r["code"]: r for r in data["rows"]}
    assert rows["6061"]["actual_cents"] == 3000 and rows["6061"]["planned_to_date_cents"] == 2000
    assert rows["706"]["unbudgeted"] and rows["706"]["actual_cents"] == 4000  # produit du projet hors budget
    assert "6063" not in rows and "613" not in rows  # lignes sans projet exclues
    # Date hors exercice : bornée à l'exercice.
    assert client.get(f"{url}?as_of=2030-01-01").get_json()["as_of"] == "2026-12-31"
    _error(client.get(f"{url}?as_of=demain"), 422)


def test_tracking_export(books, login_as):
    client = login_as(role="accountant")
    resp = client.get(f"/budget/tracking.xlsx?fiscal_year_id={books['fy'].id}&as_of=2026-03-15")
    assert resp.status_code == 200 and "suivi-budget-2026.xlsx" in resp.headers["Content-Disposition"]
    ws = load_workbook(BytesIO(resp.data)).active
    assert [c.value for c in ws[1]][:4] == ["Nature", "Compte", "Poste", "Prévu (année)"]
    assert [c.value for c in ws[2]][:7] == ["Charges", "60", "Compte 60", 1200, 300, 50, -250]


def test_project_statement(books, login_as):
    entity = Entity(name="Jardinerie", entity_type="FOURNISSEUR")
    purchase = Purchase(qonto_id="si-1", invoice_number="F-1", issue_date=date(2026, 1, 15), total_cents=3000,
                        entity=entity, attachment_path="x.pdf")
    line = JournalLine.query.filter_by(project_id=books["jardin"].id, account_id=books["6061"]).first()
    purchase.journal_entry_id = line.entry_id
    db.session.add(purchase)
    db.session.commit()
    client = login_as()
    url = f"/api/v1/projects/{books['jardin'].id}/statement"
    data = client.get(f"{url}?start=2026-01-01&end=2026-03-31").get_json()
    assert data["totals"] == {"expense_cents": 3000, "income_cents": 4000, "result_cents": 1000}
    assert [(a["code"], a["amount_cents"]) for a in data["accounts"]] == [("6061", 3000), ("706", 4000)]
    assert data["lines"][0]["document_url"] == f"/purchases/{purchase.id}/attachment"
    assert data["lines"][1]["document_url"] is None
    whole = client.get(url).get_json()  # défaut : exercice en cours ; la charge de juillet est sans projet
    assert (whole["start"], whole["end"]) == ("2026-01-01", "2026-12-31") and whole["totals"]["expense_cents"] == 3000
    _error(client.get(f"{url}?start=2026-05-01&end=2026-01-01"), 422)
    resp = client.get(f"/projects/{books['jardin'].id}/statement.xlsx?start=2026-01-01&end=2026-03-31")
    wb = load_workbook(BytesIO(resp.data))
    assert wb.sheetnames == ["Compte de résultat", "Détail"]
    assert wb["Détail"]["G2"].value.endswith(f"/purchases/{purchase.id}/attachment")
