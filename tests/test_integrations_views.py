"""Écran des intégrations : index, détail, enregistrement + test, interrupteur, secrets."""
import pytest

from app.extensions import db
from app.models import ExternalConnection
from app.services import external_config, integrations

ODOO = {"url": "https://erp.example.org", "db": "prod", "username": "a@b.fr", "api_key": "odoo-secret-key"}


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


def test_index_lists_integrations_without_fields_or_checks(client, probes):
    html = client.get("/configuration/integrations/").get_data(as_text=True)
    for label in external_config.SERVICE_LABELS.values():
        assert label in html
    assert "<input" not in html and "<textarea" not in html
    assert "Non testée" in html  # SMTP via .env
    assert "À configurer" in html
    assert probes == []


def test_index_shows_disabled_and_error(client, monkeypatch):
    external_config.set_enabled("facebook", False)
    external_config.set_many("odoo", ODOO)

    def boom():
        raise RuntimeError("panne")
    monkeypatch.setitem(integrations.PROBES, "odoo", boom)
    integrations.run_check("odoo")
    html = client.get("/configuration/integrations/").get_data(as_text=True)
    assert "Désactivée" in html
    assert "En erreur" in html
    assert "Erreur inattendue : RuntimeError — panne" in html


@pytest.mark.parametrize("service", list(external_config.SERVICE_KEYS))
def test_detail_page(client, service):
    resp = client.get(f"/configuration/integrations/{service}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert external_config.SERVICE_LABELS[service] in html
    for key in external_config.SERVICE_KEYS[service]:
        assert f'name="{key}"' in html


def test_detail_unknown_service(client):
    assert client.get("/configuration/integrations/nope").status_code == 404
    assert client.post("/configuration/integrations/nope/check").status_code == 404


def test_save_runs_check_once_and_shows_result(client, probes):
    resp = client.post("/configuration/integrations/odoo", data=ODOO, follow_redirects=True)
    assert probes == ["odoo"]
    html = resp.get_data(as_text=True)
    assert "Tout va bien." in html
    assert "Opérationnelle" in html
    assert integrations.status("odoo") == integrations.STATUS_OK


def test_save_disabled_integration_does_not_check(client, probes):
    external_config.set_enabled("odoo", False)
    resp = client.post("/configuration/integrations/odoo", data=ODOO, follow_redirects=True)
    assert probes == []
    assert "désactivée, non testée" in resp.get_data(as_text=True)
    assert external_config.get("odoo", "url") == ODOO["url"]


def test_save_incomplete_configuration_warns(client, probes):
    resp = client.post("/configuration/integrations/odoo", data={"url": "https://x.org"},
                       follow_redirects=True)
    assert probes == []
    assert "Configuration incomplète" in resp.get_data(as_text=True)


def test_secret_never_rendered(client):
    external_config.set_many("odoo", ODOO)
    html = client.get("/configuration/integrations/odoo").get_data(as_text=True)
    assert "odoo-secret-key" not in html
    assert ODOO["url"] in html  # les champs non secrets restent pré-remplis
    assert 'name="clear_api_key"' in html


def test_empty_secret_keeps_value_and_clear_removes_it(client, probes):
    external_config.set_many("odoo", ODOO)
    client.post("/configuration/integrations/odoo", data={**ODOO, "api_key": ""})
    assert external_config.get("odoo", "api_key") == "odoo-secret-key"

    client.post("/configuration/integrations/odoo", data={**ODOO, "api_key": "", "clear_api_key": "1"})
    assert db.session.query(ExternalConnection).filter_by(service="odoo", key="api_key").first() is None


def test_env_fallback_is_not_copied_into_db(client, probes):
    # SMTP host vient du .env (conftest) : enregistrer sans le saisir ne le recopie pas.
    client.post("/configuration/integrations/smtp", data={"port": "2525"})
    assert external_config.source("smtp", "host") == "env"
    assert external_config.source("smtp", "port") == "db"


def test_toggle(client, probes):
    resp = client.post("/configuration/integrations/smtp/enabled", data={"enabled": "0"},
                       follow_redirects=True)
    assert external_config.is_enabled("smtp") is False
    assert "Intégration SMTP (relance email) désactivée." in resp.get_data(as_text=True)
    client.post("/configuration/integrations/smtp/enabled", data={"enabled": "1"})
    assert external_config.is_enabled("smtp") is True
    assert probes == []


def test_check_button(client, probes):
    resp = client.post("/configuration/integrations/smtp/check", follow_redirects=True)
    assert probes == ["smtp"]
    assert "Tout va bien." in resp.get_data(as_text=True)


def test_check_button_disabled_when_unavailable(client):
    html = client.get("/configuration/integrations/odoo").get_data(as_text=True)
    assert 'title="Configuration incomplète"' in html


def test_last_sync_section(client):
    html = client.get("/configuration/integrations/odoo").get_data(as_text=True)
    assert "Non suivie pour cette intégration." in html
    html = client.get("/configuration/integrations/stancer").get_data(as_text=True)
    assert "Aucune synchronisation lancée." in html


def test_legacy_url_redirects(client):
    resp = client.get("/configuration/external-connections/")
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith("/configuration/integrations/")


def test_non_admin_forbidden(login_as):
    client = login_as(is_admin=False)
    assert client.get("/configuration/integrations/").status_code == 403
    assert client.post("/configuration/integrations/smtp/check").status_code == 403


def test_local_dt_filter(app):
    from datetime import datetime

    local_dt = app.jinja_env.filters["local_dt"]
    assert local_dt(datetime(2026, 10, 20, 19, 52)) == "20/10/2026 21:52"  # heure d'été
    assert local_dt(datetime(2026, 12, 1, 8, 0)) == "01/12/2026 09:00"
    assert local_dt(None) == ""
