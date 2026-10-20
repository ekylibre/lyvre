"""Pages de saisie : l'îlot EntryForm reçoit ses props, l'ancien formulaire n'existe plus."""
import json
import re
from datetime import date
from html import unescape

import pytest

from app.extensions import db
from app.models import Account, BankAccount, BankTransaction, FiscalYear, Journal
from app.services.ledger import post_validated_entry, validate_entry_payload


@pytest.fixture()
def client(app):
    app.config["LOGIN_DISABLED"] = True
    return app.test_client()


@pytest.fixture()
def base(session):
    today = date.today()
    fy = FiscalYear(label="Courant", start_date=date(today.year, 1, 1),
                    end_date=date(today.year, 12, 31))
    old = FiscalYear(label="Clos", start_date=date(2000, 1, 1), end_date=date(2000, 12, 31),
                     closed=True)
    ac, bq = Journal(code="AC", label="Achats"), Journal(code="BQ", label="Banque")
    bank, expense = Account(code="512", label="Banque"), Account(code="606", label="Achats")
    session.add_all([fy, old, ac, bq, bank, expense])
    session.flush()
    ba = BankAccount(label="Courant", account_id=bank.id)
    session.add(ba)
    session.flush()
    bt = BankTransaction(bank_account_id=ba.id, fitid="T1", amount_cents=-4200,
                         transaction_date=date(today.year, 2, 3), label="CB LEROY")
    session.add(bt)
    session.commit()
    return {"fy": fy, "ac": ac, "bq": bq, "bank": bank, "expense": expense, "ba": ba, "bt": bt}


def _props(html):
    m = re.search(r'data-island="entry-form" data-props="([^"]*)"', html)
    assert m, "îlot entry-form absent"
    return json.loads(unescape(m.group(1)))


def test_new_entry_page_props(client, base):
    resp = client.get("/entries/new")
    assert resp.status_code == 200
    props = _props(resp.get_data(as_text=True))
    assert props["mode"] == "create"
    assert [f["label"] for f in props["fiscalYears"]] == ["Courant"]  # exercices ouverts
    assert [j["code"] for j in props["journals"]] == ["AC", "BQ"]
    assert props["initial"]["fiscal_year_id"] == base["fy"].id
    assert props["initial"]["entry_date"] == date.today().isoformat()
    assert props["urls"] == {"api": "/api/v1", "cancel": "/entries/"}
    assert "bankTransaction" not in props


def test_new_entry_from_bank_transaction(client, base):
    props = _props(client.get(f"/entries/new?bt_id={base['bt'].id}").get_data(as_text=True))
    assert props["bankTransaction"]["amount_cents"] == -4200
    assert props["initial"]["journal_id"] == base["bq"].id
    line = props["initial"]["lines"][0]
    assert line["account"]["code"] == "512"
    assert (line["debit_cents"], line["credit_cents"]) == (0, 4200)
    back = f"/reconciliation/?bank_account_id={base['ba'].id}"
    assert props["urls"]["afterSave"] == props["urls"]["cancel"] == back


def test_new_entry_from_reconciled_transaction_redirects(client, base):
    base["bt"].reconciled = True
    db.session.commit()
    resp = client.get(f"/entries/new?bt_id={base['bt'].id}")
    assert resp.status_code == 302 and "/reconciliation/" in resp.headers["Location"]


def _entry(base, **over):
    data = {
        "fiscal_year_id": base["fy"].id, "journal_id": base["ac"].id,
        "entry_date": date(date.today().year, 2, 3).isoformat(), "description": "CB",
        "lines": [
            {"account_id": base["expense"].id, "debit_cents": 4200},
            {"account_id": base["bank"].id, "credit_cents": 4200},
        ],
    }
    data.update(over)
    clean, errors = validate_entry_payload(data)
    assert not errors
    return clean


def test_edit_entry_page_props(client, base):
    entry = post_validated_entry(_entry(base))
    props = _props(client.get(f"/entries/{entry.id}/edit").get_data(as_text=True))
    assert props["mode"] == "edit" and props["entryId"] == entry.id
    assert props["reference"] == entry.reference
    assert [l["account"]["code"] for l in props["initial"]["lines"]] == ["606", "512"]
    assert props["urls"]["cancel"] == f"/entries/{entry.id}"


def test_edit_reconciled_entry_redirects_with_message(client, base):
    entry = post_validated_entry(_entry(base), bank_transaction=base["bt"])
    resp = client.get(f"/entries/{entry.id}/edit")
    assert resp.status_code == 302 and resp.headers["Location"] == f"/entries/{entry.id}"


def test_page_loads_island_assets(client, base, monkeypatch):
    import app.frontend as frontend

    monkeypatch.setattr(frontend, "_load_manifest",
                        lambda: {"src/main.tsx": {"file": "assets/main-test.js"}})
    html = client.get("/entries/new").get_data(as_text=True)
    main = html.split('id="page-content"', 1)[1]
    assert '<script type="module" src="/static/dist/assets/main-test.js"></script>' in main


@pytest.mark.parametrize("method, url", [
    ("get", "/entries/new-line"),
    ("get", "/accounts/search?q=6"),
])
def test_legacy_routes_removed(client, base, method, url):
    assert getattr(client, method)(url).status_code == 404


def test_legacy_html_post_removed(client, base):
    assert client.post("/entries/new", data={}).status_code == 405
