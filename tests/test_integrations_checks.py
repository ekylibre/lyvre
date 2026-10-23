"""Test de fonctionnement des intégrations : sondes (réseau simulé), erreurs lisibles, secrets masqués."""
import json
import smtplib
import socket
import xmlrpc.client

import pytest
import requests

from app.extensions import db
from app.models import IntegrationState
from app.services import external_config, integrations

# Interrupteurs d'intégration : ceux de l'instance de test (conftest), toutes activées.
pytestmark = pytest.mark.usefixtures("instance")

ODOO = {"url": "https://erp.example.org", "db": "prod", "username": "a@b.fr", "api_key": "odoo-secret-key"}


class FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self._payload = payload or {}
        self.status_code = status_code
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


def _http_error(status_code):
    return requests.HTTPError(f"HTTP {status_code}", response=FakeResponse(status_code=status_code))


# ------------------------------------------------------------------ run_check

def test_run_check_records_result(app, monkeypatch):
    external_config.set_many("odoo", ODOO)
    monkeypatch.setitem(integrations.PROBES, "odoo", lambda: "Connecté.")
    result = integrations.run_check("odoo")
    assert result.ok is True
    assert result.message == "Connecté."
    assert result.duration_ms >= 0
    state = db.session.query(IntegrationState).filter_by(service="odoo").one()
    assert state.check_ok is True
    assert state.check_message == "Connecté."
    assert state.checked_fingerprint == external_config.fingerprint("odoo")
    assert state.enabled is True


def test_run_check_refuses_disabled_without_calling_probe(app, monkeypatch):
    calls = []
    monkeypatch.setitem(integrations.PROBES, "smtp", lambda: calls.append(1) or "OK")
    external_config.set_enabled("smtp", False)
    result = integrations.run_check("smtp")
    assert result.ok is False
    assert "désactivée" in result.message
    assert calls == []
    assert db.session.query(IntegrationState).filter_by(service="smtp").first() is None  # aucun test enregistré


def test_run_check_refuses_incomplete_configuration(app, monkeypatch):
    calls = []
    monkeypatch.setitem(integrations.PROBES, "odoo", lambda: calls.append(1) or "OK")
    result = integrations.run_check("odoo")
    assert result.ok is False
    assert "url" in result.message and "api_key" in result.message
    assert calls == []
    assert db.session.query(IntegrationState).count() == 0


def test_run_check_unknown_service(app):
    with pytest.raises(ValueError):
        integrations.run_check("nope")


def test_run_check_masks_secret_and_truncates(app, monkeypatch):
    external_config.set_many("odoo", ODOO)

    def leak():
        raise RuntimeError("bad key odoo-secret-key " + "x" * 800)
    monkeypatch.setitem(integrations.PROBES, "odoo", leak)
    result = integrations.run_check("odoo")
    assert result.ok is False
    assert "odoo-secret-key" not in result.message
    assert integrations.MASK in result.message
    assert len(result.message) <= integrations.MAX_MESSAGE_LENGTH


def test_mask_ga4_private_key(app):
    creds = {"type": "service_account", "private_key": "-----BEGIN KEY-----abc", "private_key_id": "kid-42"}
    external_config.set_many("ga4", {"property_id": "123", "credentials_json": json.dumps(creds)})
    masked = integrations.mask_secrets("ga4", "key -----BEGIN KEY-----abc id kid-42")
    assert "BEGIN KEY" not in masked and "kid-42" not in masked


# ------------------------------------------------------------ describe_error

@pytest.mark.parametrize("exc, expected", [
    (requests.Timeout("read timed out"), "Délai dépassé"),
    (socket.timeout("timed out"), "Délai dépassé"),
    (requests.ConnectionError("Name or service not known"), "Serveur injoignable"),
    (ConnectionRefusedError(111, "Connection refused"), "Serveur injoignable"),
    (_http_error(401), "Identifiants refusés par Facebook (Page) (HTTP 401)"),
    (_http_error(403), "Identifiants refusés"),
    (_http_error(404), "vérifiez l'ID de la Page"),
    (_http_error(429), "Trop de requêtes"),
    (_http_error(502), "rencontre une erreur (HTTP 502)"),
    (ImportError("No module named 'x'", name="x"), "Dépendance manquante : x"),
    (ValueError("bizarre\nsuite"), "Erreur inattendue : ValueError — bizarre"),
])
def test_describe_error(app, exc, expected):
    assert expected in integrations.describe_error("facebook", exc)


def test_describe_error_smtp(app):
    auth = smtplib.SMTPAuthenticationError(535, b"5.7.8 bad credentials")
    assert integrations.describe_error("smtp", auth) == "Identifiant ou mot de passe SMTP refusé."
    other = smtplib.SMTPResponseException(554, b"no")
    assert "(554)" in integrations.describe_error("smtp", other)


def test_describe_error_odoo(app):
    from app.services.odoo_client import OdooConfigError

    fault = xmlrpc.client.Fault(2, "AccessDenied\nTraceback ...")
    assert integrations.describe_error("odoo", fault) == "Odoo a répondu une erreur : AccessDenied"
    proto = xmlrpc.client.ProtocolError("erp/xmlrpc", 404, "Not Found", {})
    assert "vérifiez l'URL" in integrations.describe_error("odoo", proto)
    assert integrations.describe_error("odoo", OdooConfigError("Authentification Odoo refusée")) \
        == "Authentification Odoo refusée"


def test_describe_error_google(app):
    from google.api_core import exceptions as gexc

    assert "Identifiants refusés" in integrations.describe_error("ga4", gexc.PermissionDenied("no"))
    assert "vérifiez l'ID de propriété" in integrations.describe_error("ga4", gexc.NotFound("no"))
    assert "Délai dépassé" in integrations.describe_error("ga4", gexc.DeadlineExceeded("slow"))


# ------------------------------------------------- sondes, réseau simulé

def test_probe_stancer(app, monkeypatch):
    from app.services import stancer_sync

    external_config.set_many("stancer", {"secret_key": "sprod_abcdef", "mode": "test"})
    calls = {}

    def fake_get(url, auth, params, timeout):
        calls.update(url=url, auth=auth, params=params, timeout=timeout)
        return FakeResponse({"payouts": []})
    monkeypatch.setattr(stancer_sync.requests, "get", fake_get)
    result = integrations.run_check("stancer")
    assert result.ok is True
    assert calls["url"].endswith("/payouts")
    assert calls["params"] == {"limit": 1}
    assert calls["timeout"] == integrations.CHECK_TIMEOUT
    assert "clé live" in result.message and "mode configuré est test" in result.message


def test_probe_stancer_refused(app, monkeypatch):
    from app.services import stancer_sync

    external_config.set_many("stancer", {"secret_key": "sprod_abcdef"})
    monkeypatch.setattr(stancer_sync.requests, "get",
                        lambda url, **kw: FakeResponse(status_code=401))
    result = integrations.run_check("stancer")
    assert result.ok is False
    assert result.message == "Identifiants refusés par Stancer (HTTP 401)."


def test_probe_odoo(app, monkeypatch):
    from app.services import odoo_client

    proxies = []

    class FakeProxy:
        def __init__(self, url, allow_none=False, transport=None):
            self.transport = transport
            proxies.append(self)

        def version(self):
            return {"server_version": "17.0"}

        def authenticate(self, db_name, login, password, ctx):
            return 5

    monkeypatch.setattr(odoo_client, "ServerProxy", FakeProxy)
    external_config.set_many("odoo", ODOO)
    result = integrations.run_check("odoo")
    assert result.message == "Connecté à Odoo 17.0 (utilisateur n° 5)."
    assert all(p.transport is not None for p in proxies)


def test_odoo_timeout_transport_sets_connection_timeout():
    from app.services.odoo_client import _timeout_transport

    conn = _timeout_transport("https://erp.example.org/", 7).make_connection("erp.example.org")
    assert conn.timeout == 7


def test_probe_helloasso(app, monkeypatch):
    from app.services import helloasso_client

    external_config.set_many("helloasso", {
        "client_id": "cid", "client_secret": "ha-secret", "org_slug": "seconde-nature",
    })
    seen = {}

    def fake_post(url, data, headers, timeout):
        seen["post_timeout"] = timeout
        return FakeResponse({"access_token": "tok", "expires_in": 1800})

    def fake_get(url, headers, params, timeout):
        seen.update(url=url, get_timeout=timeout)
        return FakeResponse({"name": "Seconde Nature"})
    monkeypatch.setattr(helloasso_client.requests, "post", fake_post)
    monkeypatch.setattr(helloasso_client.requests, "get", fake_get)
    result = integrations.run_check("helloasso")
    assert result.message == "Organisation « Seconde Nature » accessible."
    assert seen["url"].endswith("/v5/organizations/seconde-nature")
    # Deux appels : le budget de la sonde est partagé.
    assert seen["post_timeout"] + seen["get_timeout"] == integrations.CHECK_TIMEOUT


class FakeSMTP:
    """Faux serveur SMTP : enregistre les étapes et les délais appliqués au socket."""

    instances = []

    def __init__(self, host, port, timeout=None):
        self.timeout = timeout
        self.steps = [("connect", host, port)]
        self.sock = self
        self.timeouts = []
        FakeSMTP.instances.append(self)

    def settimeout(self, value):
        self.timeouts.append(value)

    def starttls(self):
        self.steps.append("starttls")

    def login(self, user, password):
        self.steps.append("login")

    def noop(self):
        self.steps.append("noop")
        return (250, b"OK")

    def quit(self):
        self.steps.append("quit")

    def close(self):
        self.steps.append("close")


def test_probe_smtp(app, monkeypatch):
    FakeSMTP.instances = []
    monkeypatch.setattr(integrations.smtplib, "SMTP", FakeSMTP)
    external_config.set_many("smtp", {"host": "smtp.example.org", "sender": "a@b.fr",
                                      "username": "u", "password": "p", "use_tls": "true"})
    result = integrations.run_check("smtp")
    assert result.ok is True
    assert result.message == "Serveur smtp.example.org:587 joignable, TLS activé, authentifié."
    server = FakeSMTP.instances[0]
    assert server.steps == [("connect", "smtp.example.org", 587), "starttls", "login", "noop", "quit"]
    # Un seul délai pour toute la sonde : chaque étape reçoit le temps restant.
    assert server.timeout <= integrations.CHECK_TIMEOUT
    assert all(t <= integrations.CHECK_TIMEOUT for t in server.timeouts)
    assert server.timeouts == sorted(server.timeouts, reverse=True)


def test_probe_smtp_deadline_exceeded(app, monkeypatch):
    class SlowSMTP(FakeSMTP):
        def starttls(self):
            clock["now"] += integrations.CHECK_TIMEOUT  # le handshake consomme tout le budget

    clock = {"now": 1000.0}
    monkeypatch.setattr(integrations.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(integrations.smtplib, "SMTP", SlowSMTP)
    result = integrations.run_check("smtp")
    assert result.ok is False
    assert result.message.startswith("Délai dépassé (10 s)")


def test_probe_smtp_failure(app, monkeypatch):
    class Refused(FakeSMTP):
        def __init__(self, host, port, timeout=None):
            raise ConnectionRefusedError(111, "Connection refused")

    monkeypatch.setattr(integrations.smtplib, "SMTP", Refused)
    result = integrations.run_check("smtp")
    assert result.ok is False
    assert result.message.startswith("Serveur injoignable")


def test_describe_error_smtp_disconnected(app):
    closed = smtplib.SMTPServerDisconnected("Connection unexpectedly closed")
    assert integrations.describe_error("smtp", closed).startswith("Le serveur SMTP a fermé")
    timed_out = smtplib.SMTPServerDisconnected("Connection unexpectedly closed: timed out")
    assert integrations.describe_error("smtp", timed_out).startswith("Délai dépassé")


def test_probe_ga4(app, monkeypatch):
    from app.services import ga4_client

    external_config.set_many("ga4", {"property_id": "472641442", "credentials_json": '{"type": "x"}'})
    seen = {}
    monkeypatch.setattr(ga4_client.GA4Client, "ping",
                        lambda self, timeout=None: seen.update(timeout=timeout))
    result = integrations.run_check("ga4")
    assert result.message == "Propriété 472641442 accessible."
    assert seen["timeout"] == integrations.CHECK_TIMEOUT


def test_probe_ga4_invalid_json(app):
    external_config.set_many("ga4", {"property_id": "1", "credentials_json": "pas du json"})
    result = integrations.run_check("ga4")
    assert result.ok is False
    assert result.message.startswith("credentials_json invalide")


def test_probe_facebook(app, monkeypatch):
    from app.services import facebook_client

    external_config.set_many("facebook", {"page_id": "123", "page_token": "fb-token-xyz"})
    seen = {}

    def fake_get(url, params, timeout):
        seen.update(url=url, params=params, timeout=timeout)
        return FakeResponse({"name": "Seconde Nature", "id": "123"})
    monkeypatch.setattr(facebook_client.requests, "get", fake_get)
    result = integrations.run_check("facebook")
    assert result.message == "Page « Seconde Nature » accessible."
    assert seen["params"]["fields"] == "name"
    assert seen["timeout"] == integrations.CHECK_TIMEOUT


def test_describe_error_appends_api_detail(app):
    graph = FakeResponse({"error": {"message": "Invalid OAuth access token.", "code": 190}}, 400)
    message = integrations.describe_error("facebook", requests.HTTPError("400", response=graph))
    assert message == "Facebook (Page) a répondu HTTP 400. Détail : Invalid OAuth access token."


def test_probe_helloasso_token_refused(app, monkeypatch):
    from app.services import helloasso_client

    external_config.set_many("helloasso", {
        "client_id": "cid", "client_secret": "ha-secret", "org_slug": "seconde-nature",
    })
    body = {"error": "unauthorized_client", "error_description": "Invalid client_id 'cid'"}
    monkeypatch.setattr(helloasso_client.requests, "post",
                        lambda url, **kw: FakeResponse(body, 401))
    result = integrations.run_check("helloasso")
    assert result.message == (
        "Identifiants refusés par HelloAsso (HTTP 401). Détail : Invalid client_id 'cid'"
    )
