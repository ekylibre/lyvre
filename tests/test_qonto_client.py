"""Client Qonto : authentification, bac à sable, pagination, 429, erreurs (aucun appel réseau)."""
import json
from datetime import datetime

import pytest
import requests

from app.services import external_config, integrations, qonto_client
from app.services.qonto_client import (
    QontoAuthError, QontoClient, QontoConfigError, QontoError, format_datetime,
)

# Interrupteurs d'intégration : ceux de l'instance de test (conftest), toutes activées.
pytestmark = pytest.mark.usefixtures("instance")

QONTO = {"login": "seconde-nature-1234", "secret_key": "qonto-secret-abcdef"}


class FakeResponse:
    def __init__(self, payload=None, status_code=200, headers=None):
        self._payload = payload if payload is not None else {}
        self.status_code = status_code
        self.headers = headers or {}
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload


class FakeSession:
    """Session requests simulée : renvoie les réponses dans l'ordre, enregistre les appels."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.headers = {}
        self.calls = []

    def post(self, url, data=None, files=None, timeout=None):
        self.calls.append({"url": url, "data": data, "files": files, "timeout": timeout})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _client(*responses, **kwargs):
    session = FakeSession(*responses)
    sleeps = []
    client = QontoClient("login", "secret", session=session, sleep=sleeps.append, **kwargs)
    return client, session, sleeps


def test_auth_header_and_production_url():
    client, session, _ = _client(FakeResponse({"organization": {"slug": "x", "bank_accounts": []}}))
    client.organization()
    assert session.headers["Authorization"] == "login:secret"
    assert "X-Qonto-Staging-Token" not in session.headers
    assert session.calls[0]["url"] == "https://thirdparty.qonto.com/v2/organization"


def test_sandbox_url_and_header():
    session = FakeSession(FakeResponse({"organization": {}}))
    client = QontoClient("login", "secret", staging_token="stg-123", session=session)
    client.organization()
    assert session.headers["X-Qonto-Staging-Token"] == "stg-123"
    assert session.calls[0]["url"].startswith("https://thirdparty-sandbox.staging.qonto.co/v2/")


def test_bank_accounts():
    accounts = [{"id": "a1", "iban": "FR76..."}]
    client, _, _ = _client(FakeResponse({"organization": {"bank_accounts": accounts}}))
    assert client.bank_accounts() == accounts


def test_list_transactions_params():
    client, session, _ = _client(FakeResponse({"transactions": [{"id": "t1"}], "meta": {"next_page": None}}))
    items, meta = client.list_transactions(
        "acc-1", statuses=("completed", "reversed"),
        updated_from=datetime(2026, 10, 1, 8, 30), settled_to=datetime(2026, 10, 31),
    )
    params = session.calls[0]["params"]
    assert params["bank_account_id"] == "acc-1"
    assert params["status[]"] == ["completed", "reversed"]
    assert params["updated_at_from"] == "2026-10-01T08:30:00.000Z"
    assert params["settled_at_to"] == "2026-10-31T00:00:00.000Z"
    assert "settled_at_from" not in params
    assert params["per_page"] == 100 and params["page"] == 1
    assert items == [{"id": "t1"}] and meta == {"next_page": None}


def test_iter_transactions_follows_next_page():
    client, session, _ = _client(
        FakeResponse({"transactions": [{"id": "t1"}], "meta": {"next_page": 2, "total_count": 2}}),
        FakeResponse({"transactions": [{"id": "t2"}], "meta": {"next_page": None, "total_count": 2}}),
    )
    pages = list(client.iter_transactions("acc-1"))
    assert [[t["id"] for t in items] for items, _ in pages] == [["t1"], ["t2"]]
    assert [c["params"]["page"] for c in session.calls] == [1, 2]


def test_list_supplier_invoices_params():
    invoices = [{"id": "si-1", "total_amount": {"value": "22.10", "currency": "EUR"}}]
    client, session, _ = _client(
        FakeResponse({"supplier_invoices": invoices, "meta": {"next_page": 2}}))
    items, meta = client.list_supplier_invoices(
        page=3, updated_from=datetime(2026, 10, 1, 8, 30), created_to=datetime(2026, 11, 1))
    call = session.calls[0]
    assert call["url"] == "https://thirdparty.qonto.com/v2/supplier_invoices"
    params = call["params"]
    assert params["filter[updated_at_from]"] == "2026-10-01T08:30:00.000Z"
    assert params["filter[created_at_to]"] == "2026-11-01T00:00:00.000Z"
    assert "filter[updated_at_to]" not in params and "filter[created_at_from]" not in params
    assert params["sort_by"] == "updated_at:asc"
    assert params["page"] == 3 and params["per_page"] == 100
    assert items == invoices and meta == {"next_page": 2}


def test_list_supplier_invoices_empty_payload():
    client, _, _ = _client(FakeResponse({}))
    assert client.list_supplier_invoices() == ([], {})


def test_429_waits_retry_after_then_succeeds():
    client, session, sleeps = _client(
        FakeResponse(status_code=429, headers={"Retry-After": "3"}),
        FakeResponse(status_code=429),
        FakeResponse({"organization": {"slug": "ok"}}),
    )
    assert client.organization() == {"slug": "ok"}
    assert sleeps == [3.0, 4]
    assert len(session.calls) == 3


def test_429_gives_up_after_retries():
    client, _, sleeps = _client(*[FakeResponse(status_code=429) for _ in range(4)])
    with pytest.raises(QontoError, match="429"):
        client.organization()
    assert sleeps == [2, 4, 8]


def test_401_never_retried():
    client, session, sleeps = _client(FakeResponse(status_code=401), FakeResponse({}))
    with pytest.raises(QontoAuthError):
        client.organization()
    assert len(session.calls) == 1 and sleeps == []


def test_server_error_and_network_retried_then_raise():
    client, session, sleeps = _client(
        requests.ConnectionError("reset"), FakeResponse(status_code=502), FakeResponse(status_code=503),
    )
    with pytest.raises(QontoError, match="503"):
        client.organization()
    assert len(session.calls) == 3 and sleeps == [2, 4]


def test_no_retry_mode():
    client, session, sleeps = _client(FakeResponse(status_code=429), retry=False)
    with pytest.raises(QontoError):
        client.organization()
    assert len(session.calls) == 1 and sleeps == []


def test_format_datetime_converts_aware_to_utc():
    from zoneinfo import ZoneInfo

    paris = datetime(2026, 7, 1, 2, 0, tzinfo=ZoneInfo("Europe/Paris"))
    assert format_datetime(paris) == "2026-07-01T00:00:00.000Z"


# ----------------------------------------------------------- configuration

def test_from_app_config(app):
    with pytest.raises(QontoConfigError, match="login, secret_key"):
        qonto_client.from_app_config()
    external_config.set_many("qonto", QONTO)
    client = qonto_client.from_app_config()
    assert client.base_url == qonto_client.PRODUCTION_BASE
    external_config.set_enabled("qonto", False)
    with pytest.raises(QontoConfigError, match="Qonto désactivée"):
        qonto_client.from_app_config()


# ------------------------------------------------------------------- sonde

def _patch_session(monkeypatch, *responses):
    session = FakeSession(*responses)
    monkeypatch.setattr(qonto_client.requests, "Session", lambda: session)
    return session


def test_probe_qonto_ok(app, monkeypatch):
    external_config.set_many("qonto", {**QONTO, "staging_token": "stg-token-1"})
    session = _patch_session(monkeypatch, FakeResponse({"organization": {
        "legal_name": "Seconde Nature", "bank_accounts": [{"id": "a"}, {"id": "b"}],
    }}))
    result = integrations.run_check("qonto")
    assert result.ok is True
    assert result.message == "Organisation « Seconde Nature » accessible (bac à sable), 2 compte(s)."
    assert session.calls[0]["timeout"] == integrations.CHECK_TIMEOUT


def test_probe_qonto_refused_with_detail_and_masked(app, monkeypatch):
    external_config.set_many("qonto", QONTO)
    body = {"errors": [{"code": "unauthorized", "detail": "bad key qonto-secret-abcdef"}]}
    session = _patch_session(monkeypatch, FakeResponse(body, 401), FakeResponse({}))
    result = integrations.run_check("qonto")
    assert result.ok is False
    assert result.message.startswith("Identifiants refusés par Qonto (HTTP 401). Détail : bad key")
    assert "qonto-secret-abcdef" not in result.message
    assert len(session.calls) == 1


def test_probe_qonto_rate_limited_is_not_retried(app, monkeypatch):
    external_config.set_many("qonto", QONTO)
    session = _patch_session(monkeypatch, FakeResponse(status_code=429), FakeResponse({}))
    result = integrations.run_check("qonto")
    assert result.message.startswith("Trop de requêtes vers Qonto")
    assert len(session.calls) == 1


# ------------------------------------------------------------------ dépôt de facture

def test_create_supplier_invoice_multipart():
    created = {"id": "si-new", "status": "to_review", "file_name": "free.pdf"}
    client, session, _ = _client(FakeResponse({"supplier_invoices": [created], "errors": []}))
    assert client.create_supplier_invoice(b"%PDF-1.4", "free.pdf", "application/pdf", "key-1") == created
    call = session.calls[0]
    assert call["url"] == "https://thirdparty.qonto.com/v2/supplier_invoices/bulk"
    assert call["data"] == {"supplier_invoices[][idempotency_key]": "key-1"}
    assert call["files"] == [("supplier_invoices[][file]", ("free.pdf", b"%PDF-1.4", "application/pdf"))]


def test_create_supplier_invoice_errors_in_200():
    body = {"supplier_invoices": [], "errors": [
        {"code": "invalid", "detail": "File is too large or wrong content type",
         "source": {"pointer": "/supplier_invoices/idempotency_key/key-1/file"}}]}
    client, _, _ = _client(FakeResponse(body))
    with pytest.raises(QontoError, match="File is too large"):
        client.create_supplier_invoice(b"x", "a.pdf", "application/pdf", "key-1")
    client, _, _ = _client(FakeResponse({"supplier_invoices": [], "errors": []}))
    with pytest.raises(QontoError, match="aucune facture"):
        client.create_supplier_invoice(b"x", "a.pdf", "application/pdf", "key-1")


def test_create_supplier_invoice_http_errors():
    client, _, _ = _client(FakeResponse({"errors": [{"code": "bad_request", "detail": "Missing file"}]},
                                        status_code=400))
    with pytest.raises(QontoError, match="HTTP 400 : Missing file"):
        client.create_supplier_invoice(b"x", "a.pdf", "application/pdf", "key-1")
    client, _, _ = _client(FakeResponse({}, status_code=403))
    with pytest.raises(QontoAuthError):
        client.create_supplier_invoice(b"x", "a.pdf", "application/pdf", "key-1")


def test_create_supplier_invoice_retried_with_same_key_on_5xx():
    created = {"id": "si-new"}
    client, session, sleeps = _client(FakeResponse(status_code=503),
                                      FakeResponse({"supplier_invoices": [created], "errors": []}))
    assert client.create_supplier_invoice(b"x", "a.pdf", "application/pdf", "key-1")["id"] == "si-new"
    assert [c["data"] for c in session.calls] == [{"supplier_invoices[][idempotency_key]": "key-1"}] * 2
