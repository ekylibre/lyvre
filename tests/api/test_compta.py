"""API de la compta (phase D) : écritures (liste, fiche, formulaire, suppression),
états financiers, tableau de bord ; pages servies par la SPA."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, BankAccount, BankTransaction, FiscalYear, Journal, JournalEntry
from app.services.ledger import post_validated_entry, validate_entry_payload


def _error(resp, status):
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()["error"]


@pytest.fixture()
def client(login_as):
    return login_as()


@pytest.fixture()
def base(app):
    today = date.today()
    fy = FiscalYear(label="Courant", start_date=date(today.year, 1, 1), end_date=date(today.year, 12, 31))
    old = FiscalYear(label="Clos", start_date=date(2000, 1, 1), end_date=date(2000, 12, 31), closed=True)
    ac, bq = Journal(code="AC", label="Achats"), Journal(code="BQ", label="Banque")
    bank = Account(code="512", label="Banque", account_type="ASSET")
    expense = Account(code="606", label="Achats", account_type="EXPENSE")
    db.session.add_all([fy, old, ac, bq, bank, expense])
    db.session.flush()
    ba = BankAccount(label="Courant", account_id=bank.id)
    db.session.add(ba)
    db.session.flush()
    bt = BankTransaction(bank_account_id=ba.id, fitid="T1", amount_cents=-4200,
                         transaction_date=date(today.year, 2, 3), label="CB LEROY")
    db.session.add(bt)
    db.session.commit()
    return {"fy": fy, "old": old, "ac": ac, "bq": bq, "bank": bank, "expense": expense, "ba": ba, "bt": bt}


def _entry(base, day=3, description="CB", amount=4200):
    clean, errors = validate_entry_payload({
        "fiscal_year_id": base["fy"].id, "journal_id": base["ac"].id,
        "entry_date": date(date.today().year, 2, day).isoformat(), "description": description,
        "lines": [{"account_id": base["expense"].id, "debit_cents": amount},
                  {"account_id": base["bank"].id, "credit_cents": amount}]})
    assert not errors
    return post_validated_entry(clean)


@pytest.mark.parametrize("url", [
    "/", "/entries/", "/entries/new", "/entries/5", "/entries/5/edit", "/reports/balance",
    "/reports/grand-livre", "/reports/bilan", "/reports/compte-de-resultat",
])
def test_pages_served_by_spa(client, url):
    assert '<div id="root"></div>' in client.get(url).get_data(as_text=True)


# ------------------------------------------------------------------ formulaire


def test_form_for_new_entry(client, base):
    body = client.get("/api/v1/entries/form").get_json()
    assert body["mode"] == "create"
    assert [f["label"] for f in body["options"]["fiscalYears"]] == ["Courant"]  # exercices ouverts
    assert [j["code"] for j in body["options"]["journals"]] == ["AC", "BQ"]
    assert body["options"]["recentsScope"] == "test"
    assert body["initial"]["fiscal_year_id"] == base["fy"].id
    assert body["initial"]["entry_date"] == date.today().isoformat()
    assert "bank_transaction" not in body


def test_form_from_bank_transaction(client, base):
    body = client.get(f"/api/v1/entries/form?bt_id={base['bt'].id}").get_json()
    assert body["bank_transaction"]["amount_cents"] == -4200
    assert body["bank_transaction"]["return_url"] == f"/reconciliation/?bank_account_id={base['ba'].id}"
    assert body["initial"]["journal_id"] == base["bq"].id
    line = body["initial"]["lines"][0]
    assert line["account"]["code"] == "512" and (line["debit_cents"], line["credit_cents"]) == (0, 4200)
    base["bt"].reconciled = True
    db.session.commit()
    assert "déjà rapprochée" in _error(client.get(f"/api/v1/entries/form?bt_id={base['bt'].id}"), 409)["message"]
    assert _error(client.get("/api/v1/entries/form?bt_id=999"), 404)


def test_form_for_edit_and_refusals(client, base):
    entry = _entry(base)
    body = client.get(f"/api/v1/entries/form?entry_id={entry.id}").get_json()
    assert body["mode"] == "edit" and body["entry_id"] == entry.id and body["reference"] == entry.reference
    assert [l["account"]["code"] for l in body["initial"]["lines"]] == ["606", "512"]

    clean, _ = validate_entry_payload({
        "fiscal_year_id": base["fy"].id, "journal_id": base["bq"].id,
        "entry_date": date(date.today().year, 2, 3).isoformat(), "description": "CB",
        "lines": [{"account_id": base["expense"].id, "debit_cents": 4200},
                  {"account_id": base["bank"].id, "credit_cents": 4200}]})
    reconciled = post_validated_entry(clean, bank_transaction=base["bt"])
    assert "rapprochée" in _error(client.get(f"/api/v1/entries/form?entry_id={reconciled.id}"), 409)["message"]


# ------------------------------------------------------------------ liste, fiche, suppression


def test_entries_list_filters_and_pagination(client, base):
    first = _entry(base, day=2, description="Facture EDF mars")
    second = _entry(base, day=9, description="Cotisation assurance")
    body = client.get("/api/v1/entries").get_json()
    assert body["meta"]["fy_id"] == base["fy"].id and body["total"] == 2
    assert [e["reference"] for e in body["items"]] == [second.reference, first.reference]
    assert body["items"][0]["total_debit_cents"] == 4200 and body["items"][0]["journal"] == "AC"
    assert {m["value"] for m in body["meta"]["months"]} >= {f"{date.today().year}-02"}
    assert [e["reference"] for e in client.get("/api/v1/entries?q=edf").get_json()["items"]] == [first.reference]
    assert client.get(f"/api/v1/entries?q={second.reference}").get_json()["total"] == 1
    page = client.get("/api/v1/entries?per_page=1&page=2&sort=asc").get_json()
    assert page["total"] == 2 and [e["reference"] for e in page["items"]] == [second.reference]
    assert client.get(f"/api/v1/entries?fy_id={base['old'].id}").get_json()["total"] == 0


def test_entry_detail_and_delete(client, base):
    entry = _entry(base)
    body = client.get(f"/api/v1/entries/{entry.id}").get_json()
    assert body["journal"] == "AC — Achats" and body["fiscal_year"] == "Courant"
    assert body["total_debit_cents"] == body["total_credit_cents"] == 4200 and body["is_balanced"]
    resp = client.delete(f"/api/v1/entries/{entry.id}")
    assert resp.status_code == 200 and resp.get_json()["notices"][0]["message"] == f"Écriture {entry.reference} supprimée."
    assert db.session.get(JournalEntry, entry.id) is None
    assert _error(client.delete(f"/api/v1/entries/{entry.id}"), 404)


def test_delete_refused_in_closed_year(client, base):
    entry = _entry(base)
    base["fy"].closed = True
    db.session.commit()
    assert "clôturé" in _error(client.delete(f"/api/v1/entries/{entry.id}"), 409)["message"]


# ------------------------------------------------------------------ états et tableau de bord


def test_balance_ledger_and_cdr(client, base):
    entry = _entry(base)
    balance = client.get("/api/v1/reports/balance").get_json()
    rows = {r["code"]: r for r in balance["items"]}
    assert rows["606"]["balance_debit_cents"] == 4200 and rows["512"]["balance_credit_cents"] == 4200
    assert balance["meta"]["fiscal_year"]["label"] == "Courant"

    ledger = client.get(f"/api/v1/reports/grand-livre?account_id={base['expense'].id}").get_json()
    assert ledger["account"]["code"] == "606"
    assert ledger["items"][0]["reference"] == entry.reference and ledger["items"][0]["running_cents"] == 4200
    assert ledger["items"][0]["url"] == f"/entries/{entry.id}"
    assert {"value": str(base["expense"].id), "label": "606 — Achats"} in ledger["meta"]["accounts"]

    cdr = client.get("/api/v1/reports/compte-de-resultat").get_json()
    assert cdr["meta"]["export_urls"]["csv"] == f"/reports/compte-de-resultat.csv?fy_id={base['fy'].id}"
    assert any(r["kind"] == "result" for r in cdr["items"]) and all("indent" in r for r in cdr["items"])
    assert _error(client.get("/api/v1/reports/balance?fy_id=999"), 404)
    assert client.get(cdr["meta"]["export_urls"]["csv"]).status_code == 200


def test_dashboard(client, base):
    _entry(base)
    body = client.get("/api/v1/dashboard").get_json()
    assert body["meta"]["fiscal_year"]["label"] == "Courant"
    assert set(body["stats"]) == {"total_sales_cents", "new_members", "resultat_courant_cents", "total_payouts_cents"}
    assert body["stats"]["resultat_courant_cents"] == -4200
    february = next(m for m in body["monthly"] if m["month"] == f"02/{date.today().year}")
    assert february["charges"] == 42.0 and february["net"] == -42.0
    assert body["recent_entries"][0]["url"].startswith("/entries/")


def test_dashboard_without_fiscal_year(client):
    body = client.get("/api/v1/dashboard").get_json()
    assert body["stats"] is None and body["meta"]["fiscal_years"] == []
