"""API des intégrations : liste, fiche, enregistrement + test, interrupteur, secrets jamais renvoyés."""
import json

import pytest

from app.extensions import db
from app.models import ExternalConnection, Instance
from app.services import external_config, integrations

ODOO = {"url": "https://erp.example.org", "db": "prod", "username": "a@b.fr", "api_key": "odoo-secret-key"}
API = "/api/v1/integrations"


@pytest.fixture()
def client(login_as):
    return login_as(is_admin=True)


@pytest.fixture()
def probes(monkeypatch):
    """Remplace toutes les sondes ; enregistre les services testés."""
    calls = []
    for service in integrations.PROBES:
        monkeypatch.setitem(integrations.PROBES, service,
                            lambda service=service: calls.append(service) or "Tout va bien.")
    return calls


def messages(resp):
    return " ".join(n["message"] for n in resp.get_json()["notices"])


def test_spa_pages(client):
    for url in ("/configuration/integrations/", "/configuration/integrations/odoo"):
        assert 'id="root"' in client.get(url).get_data(as_text=True)


def test_list_without_fields_or_checks(client, probes):
    items = {i["slug"]: i for i in client.get(API).get_json()["items"]}
    assert set(items) == set(external_config.SERVICE_KEYS)
    assert {i["label"] for i in items.values()} == set(external_config.SERVICE_LABELS.values())
    assert "fields" not in items["odoo"]
    assert items["smtp"]["status_label"] == "Non testée"  # SMTP via .env
    assert items["odoo"]["status_label"] == "À configurer"
    assert probes == []


def test_list_shows_disabled_and_error(client, monkeypatch):
    external_config.set_enabled("facebook", False)
    external_config.set_many("odoo", ODOO)

    def boom():
        raise RuntimeError("panne")
    monkeypatch.setitem(integrations.PROBES, "odoo", boom)
    integrations.run_check("odoo")
    items = {i["slug"]: i for i in client.get(API).get_json()["items"]}
    assert items["facebook"]["status_label"] == "Désactivée"
    assert items["odoo"]["status_label"] == "En erreur"
    assert items["odoo"]["last_check"]["message"] == "Erreur inattendue : RuntimeError — panne"


@pytest.mark.parametrize("service", list(external_config.SERVICE_KEYS))
def test_detail(client, service):
    body = client.get(f"{API}/{service}").get_json()
    assert body["item"]["label"] == external_config.SERVICE_LABELS[service]
    assert [f["key"] for f in body["fields"]] == list(external_config.SERVICE_KEYS[service])


def test_unknown_service(client):
    assert client.get(f"{API}/nope").status_code == 404
    assert client.post(f"{API}/nope/check").status_code == 404


def test_save_runs_check_once(client, probes):
    resp = client.put(f"{API}/odoo", json={"values": ODOO})
    assert probes == ["odoo"]
    assert "Tout va bien." in messages(resp)
    assert resp.get_json()["item"]["status_label"] == "Opérationnelle"
    assert integrations.status("odoo") == integrations.STATUS_OK


def test_save_disabled_integration_does_not_check(client, probes):
    external_config.set_enabled("odoo", False)
    resp = client.put(f"{API}/odoo", json={"values": ODOO})
    assert probes == [] and "désactivée, non testée" in messages(resp)
    assert external_config.get("odoo", "url") == ODOO["url"]


def test_save_incomplete_configuration_warns(client, probes):
    resp = client.put(f"{API}/odoo", json={"values": {"url": "https://x.org"}})
    assert probes == [] and "Configuration incomplète" in messages(resp)


def test_empty_secret_keeps_value_and_clear_removes_it(client, probes):
    external_config.set_many("odoo", ODOO)
    client.put(f"{API}/odoo", json={"values": {**ODOO, "api_key": ""}})
    assert external_config.get("odoo", "api_key") == "odoo-secret-key"
    client.put(f"{API}/odoo", json={"values": {**ODOO, "api_key": ""}, "clear": ["api_key"]})
    assert db.session.query(ExternalConnection).filter_by(service="odoo", key="api_key").first() is None


def test_env_fallback_is_not_copied_into_db(client, probes):
    # SMTP host vient du .env (conftest) : enregistrer sans le saisir ne le recopie pas.
    client.put(f"{API}/smtp", json={"values": {"port": "2525"}})
    assert external_config.source("smtp", "host") == "env"
    assert external_config.source("smtp", "port") == "db"


def test_toggle(client, probes):
    resp = client.post(f"{API}/smtp/enabled", json={"enabled": False})
    assert external_config.is_enabled("smtp") is False
    assert "Intégration SMTP (relance email) désactivée." in messages(resp)
    client.post(f"{API}/smtp/enabled", json={"enabled": True})
    assert external_config.is_enabled("smtp") is True
    assert probes == []


def test_check(client, probes):
    resp = client.post(f"{API}/smtp/check")
    assert probes == ["smtp"] and "Tout va bien." in messages(resp)
    assert resp.get_json()["item"]["last_check"]["ok"] is True
    assert client.post(f"{API}/odoo/check").status_code == 409  # configuration incomplète
    assert probes == ["smtp"]


def test_last_sync(client):
    assert client.get(f"{API}/odoo").get_json()["item"]["sync_tracked"] is False
    stancer = client.get(f"{API}/stancer").get_json()["item"]
    assert stancer["sync_tracked"] is True and stancer["last_sync"] is None


def test_qonto_field_help(client):
    fields = {f["key"]: f for f in client.get(f"{API}/qonto").get_json()["fields"]}
    assert fields["login"]["label"] == "Identifiant (login)"
    assert fields["staging_token"]["label"] == "Jeton bac à sable (optionnel)"
    assert fields["secret_key"]["help"] == "Clé API générée dans Qonto"
    stancer = {f["key"]: f for f in client.get(f"{API}/stancer").get_json()["fields"]}
    assert stancer["secret_key"]["help"].startswith("Format sk_xxx")  # l'aide par clé reste celle de Stancer


def test_legacy_url_redirects(client):
    resp = client.get("/configuration/external-connections/")
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith("/configuration/integrations/")


def test_non_admin_forbidden(login_as):
    client = login_as(is_admin=False)
    assert client.get(API).status_code == 403
    assert client.post(f"{API}/smtp/check").status_code == 403


def test_no_secret_in_any_api_response(client, probes):
    """CP H : aucun secret (base ou .env) dans les réponses de l'API de configuration."""
    secrets = {}
    for service, key in external_config.SECRET_KEYS:
        secrets[(service, key)] = f"SECRET-{service}-{key}-7f3a"
    for service in external_config.SERVICE_KEYS:
        external_config.set_many(service, {key: value for (s, key), value in secrets.items() if s == service})
    pg = Instance(slug="pg", label="PG", database_url="postgresql://compta:SECRET-pg-password@db.local/asso")
    db.session.add(pg)
    db.session.commit()

    bodies = [client.get(API), client.get("/api/v1/instances"), client.get(f"/api/v1/instances/{pg.id}")]
    for service in external_config.SERVICE_KEYS:
        bodies += [client.get(f"{API}/{service}"), client.put(f"{API}/{service}", json={"values": {}}),
                   client.post(f"{API}/{service}/enabled", json={"enabled": True}), client.post(f"{API}/{service}/check")]
    text = "\n".join(json.dumps(r.get_json()) for r in bodies)
    assert "SECRET-" not in text
    assert "compta:***@db.local" in text
    # Les secrets sont toujours en base (rien d'effacé en enregistrant des champs vides).
    assert all(external_config.get(s, k) == v for (s, k), v in secrets.items())


def test_local_dt_filter(app):
    from datetime import datetime

    local_dt = app.jinja_env.filters["local_dt"]
    assert local_dt(datetime(2026, 10, 20, 19, 52)) == "20/10/2026 21:52"  # heure d'été
    assert local_dt(datetime(2026, 12, 1, 8, 0)) == "01/12/2026 09:00"
    assert local_dt(None) == ""
