"""Rattachement des comptes Qonto aux comptes bancaires (service + écran admin)."""
from datetime import date, datetime

import pytest

from app.extensions import db
from app.models import Account, BankAccount, BankTransaction, FiscalYear
from app.services import external_config, qonto_client, qonto_sync
from app.services.qonto_sync import QontoLinkError

QONTO = {"login": "org-1234", "secret_key": "qonto-secret-abcdef"}
IBAN = "FR7616958000011234567890123"
MAIN = {"id": "acc-main", "name": "Compte principal", "iban": IBAN, "status": "active",
        "main": True, "balance_cents": 596295}
OTHER = {"id": "acc-other", "name": "Épargne", "iban": "FR7616958000019999999999999",
         "status": "active", "main": False, "balance_cents": 1000}


@pytest.fixture()
def gl(app):
    account = Account(code="5121", label="Banque")
    db.session.add(account)
    db.session.commit()
    return account


@pytest.fixture()
def fake_qonto(app, monkeypatch):
    """Intégration configurée + client simulé renvoyant `state['accounts']`."""
    state = {"accounts": [MAIN, OTHER], "calls": 0, "error": None}

    class FakeClient:
        def bank_accounts(self):
            state["calls"] += 1
            if state["error"]:
                raise state["error"]
            return state["accounts"]

    external_config.set_many("qonto", QONTO)
    monkeypatch.setattr(qonto_client, "from_app_config", lambda **kw: FakeClient())
    return state


# ------------------------------------------------------------------ service

def test_normalize_iban():
    assert qonto_sync.normalize_iban(" fr76 1695 8000 ") == "FR7616958000"
    assert qonto_sync.normalize_iban("") is None


def test_default_sync_from_uses_open_fiscal_year(app):
    assert qonto_sync.default_sync_from(date(2026, 10, 20)) == date(2026, 1, 1)
    db.session.add(FiscalYear(label="2025-26", start_date=date(2025, 7, 1), end_date=date(2026, 6, 30)))
    db.session.add(FiscalYear(label="2026-27", start_date=date(2026, 7, 1), end_date=date(2027, 6, 30)))
    db.session.commit()
    assert qonto_sync.default_sync_from(date(2026, 10, 20)) == date(2026, 7, 1)


def test_list_accounts_proposes_same_iban(app, gl):
    ba = BankAccount(label="Banque Qonto", iban="FR76 1695 8000 0112 3456 7890 123", account_id=gl.id)
    db.session.add(ba)
    db.session.commit()
    views = {v.qonto_id: v for v in qonto_sync.list_accounts([MAIN, OTHER])}
    assert views["acc-main"].proposed == ba and views["acc-main"].linked is None
    assert views["acc-other"].proposed is None


def test_link_existing_account(app, gl):
    ba = BankAccount(label="Banque", account_id=gl.id)
    db.session.add(ba)
    db.session.commit()
    linked = qonto_sync.link_account(MAIN, bank_account_id=ba.id, sync_from=date(2026, 7, 1))
    assert linked.qonto_account_id == "acc-main"
    assert linked.iban == IBAN  # complété depuis Qonto
    assert linked.qonto_sync_from == date(2026, 7, 1)
    views = {v.qonto_id: v for v in qonto_sync.list_accounts([MAIN])}
    assert views["acc-main"].linked == ba


def test_link_creates_bank_account(app, gl):
    ba = qonto_sync.link_account(MAIN, label="", gl_account_id=gl.id)
    assert ba.label == "Qonto — Compte principal"
    assert (ba.iban, ba.account_id) == (IBAN, gl.id)
    assert ba.qonto_sync_from == date(date.today().year, 1, 1)


def test_link_refusals(app, gl):
    with pytest.raises(QontoLinkError, match="compte comptable"):
        qonto_sync.link_account(MAIN)
    qonto_sync.link_account(MAIN, gl_account_id=gl.id)
    with pytest.raises(QontoLinkError, match="déjà rattaché"):
        qonto_sync.link_account(MAIN, gl_account_id=gl.id)
    linked = BankAccount.query.filter_by(qonto_account_id="acc-main").one()
    with pytest.raises(QontoLinkError, match="autre compte Qonto"):
        qonto_sync.link_account(OTHER, bank_account_id=linked.id)


def test_unlink_keeps_transactions(app, gl):
    ba = qonto_sync.link_account(MAIN, gl_account_id=gl.id)
    db.session.add(BankTransaction(bank_account_id=ba.id, fitid="t1", transaction_date=date(2026, 8, 1),
                                   amount_cents=-500, source="qonto"))
    ba.qonto_synced_at = datetime(2026, 9, 1)
    db.session.commit()
    qonto_sync.unlink_account(ba)
    assert (ba.qonto_account_id, ba.qonto_synced_at) == (None, None)
    assert ba.transactions.count() == 1


def test_set_sync_from_earlier_resets_cursor(app, gl):
    ba = qonto_sync.link_account(MAIN, gl_account_id=gl.id, sync_from=date(2026, 7, 1))
    ba.qonto_synced_at = datetime(2026, 10, 1)
    db.session.commit()
    qonto_sync.set_sync_from(ba, date(2026, 8, 1))
    assert ba.qonto_synced_at is not None  # date avancée : curseur conservé
    qonto_sync.set_sync_from(ba, date(2026, 1, 1))
    assert ba.qonto_synced_at is None


# ------------------------------------------------------------------- écrans

def test_qonto_page_lists_accounts(login_as, gl, fake_qonto):
    client = login_as(is_admin=True)
    html = client.get("/bank-accounts/qonto").get_data(as_text=True)
    assert "Compte principal" in html and "Épargne" in html
    assert IBAN in html
    assert "X XXX,XX €" in html
    assert fake_qonto["calls"] == 1


def test_qonto_page_unavailable_makes_no_call(login_as, gl, fake_qonto):
    external_config.set_enabled("qonto", False)
    client = login_as(is_admin=True)
    html = client.get("/bank-accounts/qonto").get_data(as_text=True)
    assert "Intégration <strong>Qonto</strong>" in html and "désactivée" in html
    assert fake_qonto["calls"] == 0


def test_qonto_page_shows_api_error(login_as, gl, fake_qonto):
    fake_qonto["error"] = qonto_client.QontoAuthError("refusé")
    client = login_as(is_admin=True)
    html = client.get("/bank-accounts/qonto").get_data(as_text=True)
    assert "refusé" in html


def test_link_route_creates_and_links(login_as, gl, fake_qonto):
    client = login_as(is_admin=True)
    resp = client.post("/bank-accounts/qonto/link", data={
        "qonto_account_id": "acc-main", "mode": "new", "label": "Qonto SCI",
        "gl_account_id": gl.id, "sync_from": "2026-07-01",
    }, follow_redirects=True)
    html = resp.get_data(as_text=True)
    assert "rattaché à « Qonto SCI »" in html and "01/07/2026" in html
    ba = BankAccount.query.filter_by(qonto_account_id="acc-main").one()
    assert ba.label == "Qonto SCI"
    assert "✓ Rattaché à" in html


def test_link_route_unknown_qonto_account(login_as, gl, fake_qonto):
    client = login_as(is_admin=True)
    resp = client.post("/bank-accounts/qonto/link", data={"qonto_account_id": "nope", "mode": "new",
                                                          "gl_account_id": gl.id},
                       follow_redirects=True)
    assert "Compte Qonto introuvable." in resp.get_data(as_text=True)
    assert BankAccount.query.count() == 0


def test_edit_page_qonto_section_and_unlink(login_as, gl, fake_qonto):
    ba = qonto_sync.link_account(MAIN, gl_account_id=gl.id, sync_from=date(2026, 7, 1))
    client = login_as(is_admin=True)
    html = client.get(f"/bank-accounts/{ba.id}/edit").get_data(as_text=True)
    assert "acc-main" in html and "Détacher de Qonto" in html and "2026-07-01" in html

    client.post(f"/bank-accounts/{ba.id}/qonto/settings", data={"sync_from": "2026-03-01"})
    assert BankAccount.query.get(ba.id).qonto_sync_from == date(2026, 3, 1)

    client.post(f"/bank-accounts/{ba.id}/qonto/unlink")
    assert BankAccount.query.get(ba.id).qonto_account_id is None


def test_index_shows_qonto_badge_and_admin_link(login_as, gl, fake_qonto):
    qonto_sync.link_account(MAIN, gl_account_id=gl.id)
    client = login_as(is_admin=True)
    html = client.get("/bank-accounts/").get_data(as_text=True)
    assert "Comptes Qonto" in html and 'title="Synchronisé avec Qonto"' in html


def test_qonto_routes_admin_only(login_as, gl, fake_qonto):
    client = login_as(is_admin=False)
    assert client.get("/bank-accounts/qonto").status_code == 403
    assert client.post("/bank-accounts/qonto/link", data={}).status_code == 403
    html = client.get("/bank-accounts/").get_data(as_text=True)
    assert "Comptes Qonto" not in html


def test_qonto_page_preselects_512(login_as, fake_qonto):
    for code in ("51", "511", "512", "5121"):
        db.session.add(Account(code=code, label=f"Compte {code}"))
    db.session.commit()
    client = login_as(is_admin=True)
    html = client.get("/bank-accounts/qonto").get_data(as_text=True)
    selected = Account.query.filter_by(code="512").one()
    assert f'value="{selected.id}" selected' in html
