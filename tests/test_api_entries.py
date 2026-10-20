"""API de saisie : recherches et écritures (/api/v1)."""
from datetime import date

import pytest

from app.extensions import db
from app.models import (
    Account, BankAccount, BankTransaction, Entity, FiscalYear, Journal, JournalEntry,
)


@pytest.fixture()
def client(app):
    app.config["LOGIN_DISABLED"] = True
    return app.test_client()


@pytest.fixture()
def base(session):
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    jr = Journal(code="AC", label="Achats")
    accounts = [
        Account(code="512", label="Banque"),
        Account(code="5121", label="Crédit Agricole"),
        Account(code="606", label="Achats non stockés"),
        Account(code="6061", label="Électricité, eau, énergie"),
        Account(code="60", label="Achats", is_header=True),
    ]
    session.add_all([fy, jr, *accounts])
    session.flush()
    ba = BankAccount(label="Courant", account_id=accounts[0].id)
    session.add_all([ba, Entity(name="EDF", entity_type="FOURNISSEUR", email="pro@edf.fr"),
                     Entity(name="Élise Martin", entity_type="ADHERENT")])
    session.commit()
    return {"fy": fy, "jr": jr, "acc": {a.code: a for a in accounts}, "ba": ba}


def body(b, **over):
    data = {
        "fiscal_year_id": b["fy"].id, "journal_id": b["jr"].id, "entry_date": "2026-03-15",
        "description": "Facture EDF",
        "lines": [
            {"account_id": b["acc"]["6061"].id, "label": "EDF", "debit_cents": 8450, "credit_cents": 0},
            {"account_id": b["acc"]["512"].id, "label": "EDF", "debit_cents": 0, "credit_cents": 8450},
        ],
    }
    data.update(over)
    return data


# --- recherches -------------------------------------------------------------


def test_accounts_by_code_prefix_then_label(client, base):
    codes = [r["code"] for r in client.get("/api/v1/accounts?q=6").get_json()["results"]]
    assert codes == ["606", "6061"]  # en-tête 60 exclu


def test_accounts_label_search_ignores_accents_and_case(client, base):
    res = client.get("/api/v1/accounts?q=electricite").get_json()["results"]
    assert [r["code"] for r in res] == ["6061"]
    res = client.get("/api/v1/accounts?q=crédit agri").get_json()["results"]
    assert [r["code"] for r in res] == ["5121"]


def test_accounts_limit(client, base):
    assert len(client.get("/api/v1/accounts?limit=2").get_json()["results"]) == 2
    assert len(client.get("/api/v1/accounts?limit=0").get_json()["results"]) == 1


def test_entities_search(client, base):
    res = client.get("/api/v1/entities?q=elise").get_json()["results"]
    assert [r["name"] for r in res] == ["Élise Martin"]
    res = client.get("/api/v1/entities?q=edf.fr").get_json()["results"]
    assert res[0]["name"] == "EDF" and res[0]["type"] == "FOURNISSEUR"


# --- écritures --------------------------------------------------------------


def test_validate_dry_run(client, base):
    resp = client.post("/api/v1/entries/validate", json=body(base, entry_date="2027-01-01"))
    assert resp.status_code == 200
    assert "hors de l'exercice" in resp.get_json()["errors"]["entry_date"]
    assert client.post("/api/v1/entries/validate", json=body(base)).get_json() == {"errors": {}}
    assert JournalEntry.query.count() == 0


def test_create_entry(client, base):
    resp = client.post("/api/v1/entries", json=body(base))
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["reference"] == "AC-2026-0001"
    assert resp.headers["Location"] == data["url"] == f"/entries/{data['id']}"
    assert [l["account_code"] for l in data["lines"]] == ["6061", "512"]
    assert data["reconciled"] is False and data["editable"] is True


def test_create_invalid_entry_returns_field_errors(client, base):
    lines = body(base)["lines"]
    lines[0]["account_id"] = base["acc"]["60"].id
    resp = client.post("/api/v1/entries", json=body(base, lines=lines))
    assert resp.status_code == 422
    err = resp.get_json()["error"]
    assert err["code"] == "validation_error"
    assert "regroupement" in err["fields"]["lines[0].account_id"]


def test_create_and_reconcile_bank_transaction(client, base):
    bt = BankTransaction(bank_account_id=base["ba"].id, fitid="X1", amount_cents=-8450,
                         transaction_date=date(2026, 3, 15), label="PRLV EDF")
    db.session.add(bt)
    db.session.commit()

    resp = client.post("/api/v1/entries", json=body(base, bank_transaction_id=bt.id))
    assert resp.status_code == 201 and resp.get_json()["reconciled"] is True
    assert db.session.get(BankTransaction, bt.id).reconciled is True

    # Transaction déjà rapprochée → conflit, rien n'est créé.
    resp = client.post("/api/v1/entries", json=body(base, bank_transaction_id=bt.id))
    assert resp.status_code == 409 and "déjà rapprochée" in resp.get_json()["error"]["message"]
    assert JournalEntry.query.count() == 1

    assert client.post("/api/v1/entries", json=body(base, bank_transaction_id=999)).status_code == 404


def test_get_and_update_entry(client, base):
    entry_id = client.post("/api/v1/entries", json=body(base)).get_json()["id"]
    assert client.get(f"/api/v1/entries/{entry_id}").get_json()["description"] == "Facture EDF"

    lines = body(base)["lines"]
    lines[0]["debit_cents"] = lines[1]["credit_cents"] = 1000
    resp = client.put(f"/api/v1/entries/{entry_id}", json=body(base, lines=lines, description="Corrigée"))
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["description"] == "Corrigée"
    assert sorted(l["debit_cents"] for l in data["lines"]) == [0, 1000]

    assert client.get("/api/v1/entries/999").status_code == 404


def test_update_reconciled_entry_is_conflict(client, base):
    bt = BankTransaction(bank_account_id=base["ba"].id, fitid="X2", amount_cents=-8450,
                         transaction_date=date(2026, 3, 15))
    db.session.add(bt)
    db.session.commit()
    entry_id = client.post("/api/v1/entries", json=body(base, bank_transaction_id=bt.id)).get_json()["id"]
    resp = client.put(f"/api/v1/entries/{entry_id}", json=body(base))
    assert resp.status_code == 409 and "rapprochée" in resp.get_json()["error"]["message"]


def test_entries_api_requires_login(app):
    resp = app.test_client().post("/api/v1/entries", json={})
    assert resp.status_code == 401
