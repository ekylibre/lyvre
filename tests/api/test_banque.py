"""API de la banque (phase E) : comptes bancaires, transactions, Stancer, import OFX ;
pages servies par la SPA."""
import io
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, BankAccount, BankTransaction, Payment, Payout
from app.services import external_config


def _error(resp, status):
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()["error"]


@pytest.fixture()
def client(login_as):
    return login_as()


@pytest.fixture()
def bank(app):
    account = Account(code="512100", label="Banque", account_type="ASSET")
    db.session.add_all([account, Account(code="51", label="Banques", is_header=True)])
    db.session.commit()
    return account


@pytest.mark.parametrize("url", [
    "/bank-accounts/", "/bank-accounts/new", "/bank-accounts/3/edit", "/bank-accounts/3/transactions",
    "/bank-accounts/3/counterparties", "/reconciliation/", "/payouts/", "/payouts/4", "/imports/ofx",
])
def test_pages_served_by_spa(client, url):
    assert '<div id="root"></div>' in client.get(url).get_data(as_text=True)


def test_qonto_page_is_admin_spa_page(login_as):
    assert '<div id="root"></div>' in login_as(is_admin=True).get("/bank-accounts/qonto").get_data(as_text=True)


def test_bank_accounts_crud(client, bank):
    resp = client.post("/api/v1/bank-accounts", json={"label": "CIC", "iban": "fr76 3000 6000", "account_id": str(bank.id)})
    item = resp.get_json()["item"]
    assert resp.status_code == 201 and item["iban"] == "FR7630006000" and item["account"]["code"] == "512100"
    body = client.get("/api/v1/bank-accounts").get_json()
    assert body["items"][0]["transactions"] == 0 and body["items"][0]["qonto"] is None
    assert body["meta"]["gl_accounts"] == [{"value": str(bank.id), "label": "512100 — Banque"}]  # sans regroupement
    assert "account_id" in _error(client.post("/api/v1/bank-accounts", json={"label": "X"}), 422)["fields"]
    assert "label" in _error(client.post("/api/v1/bank-accounts", json={"account_id": bank.id}), 422)["fields"]

    upd = client.patch(f"/api/v1/bank-accounts/{item['id']}", json={"label": "CIC courant", "iban": "", "account_id": bank.id})
    assert upd.get_json()["item"]["label"] == "CIC courant" and upd.get_json()["item"]["iban"] is None

    db.session.add(BankTransaction(bank_account_id=item["id"], fitid="t1", transaction_date=date(2026, 3, 1), amount_cents=-500))
    db.session.commit()
    assert "1 transaction(s)" in _error(client.delete(f"/api/v1/bank-accounts/{item['id']}"), 409)["message"]
    other = client.post("/api/v1/bank-accounts", json={"label": "Vide", "account_id": bank.id}).get_json()["item"]
    assert client.delete(f"/api/v1/bank-accounts/{other['id']}").status_code == 200


def test_transactions_filters(client, bank):
    ba = BankAccount(label="CIC", account_id=bank.id)
    db.session.add(ba)
    db.session.flush()
    db.session.add_all([
        BankTransaction(bank_account_id=ba.id, fitid="a", transaction_date=date(2026, 3, 1), amount_cents=-500, label="Débit"),
        BankTransaction(bank_account_id=ba.id, fitid="b", transaction_date=date(2026, 3, 5), amount_cents=900, label="Crédit",
                        reconciled=True),
    ])
    db.session.commit()
    url = f"/api/v1/bank-accounts/{ba.id}/transactions"
    assert [t["label"] for t in client.get(f"{url}?status=all&sort=desc").get_json()["transactions"]] == ["Crédit", "Débit"]
    assert [t["label"] for t in client.get(url).get_json()["transactions"]] == ["Débit"]  # à rapprocher par défaut
    assert [t["label"] for t in client.get(f"{url}?status=all&no_invoice=1").get_json()["transactions"]] == ["Débit"]
    detail = client.get(f"/api/v1/bank-accounts/{ba.id}").get_json()
    assert detail["item"]["unreconciled"] == 1 and detail["qonto_job"] is None and detail["proposal_count"] == 0
    assert _error(client.get("/api/v1/bank-accounts/999"), 404)


def test_qonto_sync_refused_without_link(client, bank):
    ba = BankAccount(label="CIC", account_id=bank.id)
    db.session.add(ba)
    db.session.commit()
    assert "pas rattaché" in _error(client.post(f"/api/v1/bank-accounts/{ba.id}/qonto/sync"), 409)["message"]


def test_payouts_list_detail_and_sync_refused(client):
    payout = Payout(stancer_id="po_1", amount_cents=10000, fees_cents=150, status="paid", date_payout=date(2026, 3, 2))
    db.session.add(payout)
    db.session.flush()
    db.session.add(Payment(stancer_id="pay_1", payout_id=payout.id, amount_cents=10150, status="captured",
                           method="card", customer_name="Alice"))
    db.session.commit()
    body = client.get("/api/v1/payouts").get_json()
    assert body["items"][0]["status_label"] == "Versé" and body["items"][0]["payments"] == 1
    detail = client.get(f"/api/v1/payouts/{payout.id}").get_json()
    assert detail["payments"][0]["customer"] == "Alice" and detail["payments"][0]["status_label"] == "Capturé"
    external_config.set_enabled("stancer", False)
    assert _error(client.post(f"/api/v1/payouts/{payout.id}/sync-payments"), 409)
    assert _error(client.get("/api/v1/payouts/999"), 404)


def test_ofx_import_errors(client, bank):
    ba = BankAccount(label="CIC", account_id=bank.id)
    db.session.add(ba)
    db.session.commit()
    post = lambda data: client.post("/api/v1/imports/ofx", data=data, content_type="multipart/form-data")  # noqa: E731
    assert "bank_account_id" in _error(post({}), 422)["fields"]
    assert "ofx_file" in _error(post({"bank_account_id": str(ba.id)}), 422)["fields"]
    err = _error(post({"bank_account_id": str(ba.id), "ofx_file": (io.BytesIO(b"pas un ofx"), "x.ofx")}), 422)
    assert "illisible" in err["message"]
    assert _error(post({"bank_account_id": "999", "ofx_file": (io.BytesIO(b"x"), "x.ofx")}), 404)
