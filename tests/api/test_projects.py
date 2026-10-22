"""Lot C.1 : projets (CRUD, archivage), projet sur les lignes d'écriture, ventilation (équilibre
et FEC conservés), projet des lignes de facture d'achat et des règles."""
from datetime import date

import pytest

from app.extensions import db
from app.models import (
    Account, BankAccount, BankTransaction, Entity, FiscalYear, Journal, JournalEntry, JournalLine, Project,
    Purchase, PurchaseLine, Rule,
)
from app.services import fec, organization, purchase_posting, rules_engine
from app.services.ledger import post_entry


def _error(resp, status):
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()["error"]


@pytest.fixture()
def books(app):
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    accounts = {c: Account(code=c, label=f"Compte {c}", account_type="OTHER")
                for c in ("512", "6061", "6063", "706", "401", "44566")}
    db.session.add_all([fy, Journal(code="BQ", label="Banque"), Journal(code="AC", label="Achats"),
                        *accounts.values(), Project(name="Jardin"), Project(name="Festival")])
    db.session.commit()
    return {"fy": fy, **accounts}


def _ids():
    return {p.name: p.id for p in Project.query}


def test_project_crud_and_archive(books, login_as):
    client = login_as()
    created = client.post("/api/v1/projects", json={"name": "Chantier", "start_date": "2026-03-01",
                                                    "end_date": "2026-09-30", "manager": "Camille"})
    assert created.status_code == 201
    pid = created.get_json()["item"]["id"]
    assert _error(client.post("/api/v1/projects", json={"name": "chantier"}), 422)["fields"] == {
        "name": "Le projet « chantier » existe déjà."}
    _error(client.post("/api/v1/projects", json={"name": "X", "start_date": "2026-05-01", "end_date": "2026-01-01"}), 422)
    _error(client.post("/api/v1/projects", json={"name": " "}), 422)
    assert client.put(f"/api/v1/projects/{pid}", json={"name": "Chantier", "archived": True}).status_code == 200
    assert "Chantier" not in [o["label"] for o in client.get("/api/v1/projects/options").get_json()["items"]]
    assert client.delete(f"/api/v1/projects/{pid}").status_code == 200


def test_accountant_reads_projects_only(books, login_as):
    client = login_as(role="accountant")
    assert client.get("/api/v1/projects").status_code == 200
    _error(client.post("/api/v1/projects", json={"name": "Y"}), 403)


def test_entry_lines_carry_project(books, login_as):
    client = login_as()
    ids = _ids()
    form = client.get("/api/v1/entries/form").get_json()
    assert [o["label"] for o in form["options"]["projects"]] == ["Festival", "Jardin"]
    body = {"fiscal_year_id": books["fy"].id, "journal_id": Journal.query.filter_by(code="BQ").one().id,
            "entry_date": "2026-04-02", "description": "Graines",
            "lines": [{"account_id": books["6061"].id, "debit_cents": 3000, "project_id": ids["Jardin"]},
                      {"account_id": books["512"].id, "credit_cents": 3000}]}
    entry = client.post("/api/v1/entries", json=body).get_json()
    assert [l["project"] for l in entry["lines"]] == ["Jardin", None]
    bad = {**body, "lines": [{**body["lines"][0], "project_id": 999}, body["lines"][1]]}
    assert "lines[0].project_id" in _error(client.post("/api/v1/entries", json=bad), 422)["fields"]
    listing = client.get("/api/v1/projects").get_json()["items"]
    jardin = next(p for p in listing if p["name"] == "Jardin")
    assert (jardin["expense_cents"], jardin["income_cents"], jardin["result_cents"]) == (3000, 0, -3000)
    # Projet utilisé : suppression refusée (archivage proposé).
    assert "archivez" in _error(client.delete(f"/api/v1/projects/{ids['Jardin']}"), 409)["message"]


def test_split_line_keeps_balance_and_fec(books, login_as, app, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "instance_path", str(tmp_path))
    org = organization.get()
    org.siren = "732829320"
    db.session.commit()
    ids = _ids()
    bq = Journal.query.filter_by(code="BQ").one()
    entry = post_entry(books["fy"].id, bq.id, date(2026, 5, 3), "Matériel", [
        {"account_id": books["6063"].id, "label": "Outils", "debit_cents": 10000},
        {"account_id": books["512"].id, "credit_cents": 10000}])
    ba = BankAccount(label="CIC", account_id=books["512"].id)
    db.session.add(ba)
    db.session.flush()
    bank_line = next(l for l in entry.lines if l.account_id == books["512"].id)
    db.session.add(BankTransaction(bank_account_id=ba.id, fitid="T1", transaction_date=date(2026, 5, 3),
                                   amount_cents=-10000, label="CB", reconciled=True, journal_line_id=bank_line.id))
    db.session.commit()
    before = fec.preview(books["fy"])
    client = login_as()
    charge = next(l for l in entry.lines if l.account_id == books["6063"].id)
    url = f"/api/v1/entries/{entry.id}/lines/{charge.id}/split"
    assert "100,00 €" in _error(client.post(url, json={"parts": [{"project_id": ids["Jardin"], "amount_cents": 6000},
                                                                {"project_id": ids["Festival"], "amount_cents": 3000}]}),
                              422)["message"]
    _error(client.post(url, json={"parts": [{"project_id": ids["Jardin"], "amount_cents": 10000}]}), 422)
    _error(client.post(f"/api/v1/entries/{entry.id}/lines/{bank_line.id}/split",
                       json={"parts": [{"amount_cents": 5000}, {"amount_cents": 5000}]}), 409)  # ligne rapprochée
    assert client.post(url, json={"parts": [{"project_id": ids["Jardin"], "amount_cents": 6000},
                                            {"project_id": ids["Festival"], "amount_cents": 3000},
                                            {"project_id": None, "amount_cents": 1000}]}).status_code == 200
    lines = JournalLine.query.filter_by(entry_id=entry.id, account_id=books["6063"].id).order_by(JournalLine.id).all()
    assert [(l.debit_cents, l.project_id, l.label) for l in lines] == [
        (6000, ids["Jardin"], "Outils"), (3000, ids["Festival"], "Outils"), (1000, None, "Outils")]
    db.session.refresh(entry)
    assert sum(l.debit_cents for l in entry.lines) == sum(l.credit_cents for l in entry.lines) == 10000
    after = fec.preview(books["fy"])
    assert after[1] == [] and after[3] == []  # pas d'erreur, relecture conforme
    assert (after[0].total_debit_cents, after[0].total_credit_cents) == (before[0].total_debit_cents,
                                                                       before[0].total_credit_cents)
    assert after[0].lines == before[0].lines + 2
    # Affectation simple d'une ligne, possible sur une écriture rapprochée.
    assert client.put(f"/api/v1/entries/{entry.id}/lines/{lines[2].id}/project",
                      json={"project_id": ids["Jardin"]}).status_code == 200
    db.session.refresh(lines[2])
    assert lines[2].project_id == ids["Jardin"]


def test_purchase_line_project_reaches_entry(books):
    ids = _ids()
    entity = Entity(name="Jardinerie", entity_type="FOURNISSEUR")
    purchase = Purchase(qonto_id="si-1", invoice_number="F-1", issue_date=date(2026, 6, 1), total_cents=1200,
                        entity=entity)
    db.session.add(purchase)
    db.session.commit()
    purchase_posting.save_lines(purchase, [{"account_code": "6061", "label": "Terreau", "untaxed": "10,00",
                                            "vat_rate": "20", "vat": "", "project_id": str(ids["Jardin"])}])
    db.session.refresh(purchase)
    assert purchase.lines[0].project_id == ids["Jardin"]
    charge = next(l for l in purchase.journal_entry.lines if l.account.code == "6061")
    assert charge.project_id == ids["Jardin"]
    assert all(l.project_id is None for l in purchase.journal_entry.lines if l.account.code != "6061")


def test_rule_sets_project(books, login_as):
    ids = _ids()
    client = login_as()
    rule = {"name": "Graines", "label_contains": "GRAINES", "account_code": "6061", "project_id": ids["Jardin"]}
    assert client.post("/api/v1/rules", json=rule).status_code == 201
    assert client.get("/api/v1/rules").get_json()["items"][0]["project"] == "Jardin"
    assert "compte" in _error(client.post("/api/v1/rules", json={**rule, "name": "B", "account_code": ""}),
                              422)["message"]
    ba = BankAccount(label="CIC", account_id=books["512"].id)
    db.session.add(ba)
    db.session.flush()
    txn = BankTransaction(bank_account_id=ba.id, fitid="G1", transaction_date=date(2026, 3, 9),
                          amount_cents=-2500, label="CB GRAINES BIO")
    db.session.add(txn)
    db.session.commit()
    rules_engine.apply_rules([txn])
    entry = JournalEntry.query.one()
    assert {l.account.code: l.project_id for l in entry.lines} == {"512": None, "6061": ids["Jardin"]}
    assert Rule.query.one().project_id == ids["Jardin"]
