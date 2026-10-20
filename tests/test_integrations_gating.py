"""Une intégration désactivée est indisponible partout : clients, synchros, écrans."""
import pytest

from app.extensions import db
from app.models import SyncJob
from app.services import external_config

ODOO = {"url": "https://erp.example.org", "db": "prod", "username": "a@b.fr", "api_key": "k-123456"}
HELLOASSO = {"client_id": "cid", "client_secret": "secret", "org_slug": "asso"}


@pytest.fixture()
def admin(login_as):
    return login_as(is_admin=True)


# ------------------------------------------------------------------ messages

def test_unavailable_reason_and_message(app):
    assert external_config.unavailable_reason("smtp") is None  # .env (conftest)
    assert external_config.unavailable_message("smtp") is None
    assert external_config.unavailable_reason("odoo") == "unconfigured"
    assert external_config.unavailable_message("odoo") == (
        "Intégration Odoo non configurée (Configuration › Intégrations)."
    )
    external_config.set_many("odoo", ODOO)
    external_config.set_enabled("odoo", False)
    assert external_config.unavailable_reason("odoo") == "disabled"
    assert "Odoo désactivée" in external_config.unavailable_message("odoo")


def test_existing_instance_without_rows_is_unchanged(app):
    # US5 : aucune ligne integration_states → tout est activé, la config .env suffit.
    from app.services import membership_reminders

    assert membership_reminders.smtp_configured() is True
    assert external_config.is_available("helloasso") is False  # pas de client_id en test


# ------------------------------------------------------------------ fabriques

def test_odoo_factory_refuses_when_disabled(app):
    from app.services import odoo_client, odoo_partner_update

    external_config.set_many("odoo", ODOO)
    assert odoo_partner_update.is_configured() is True
    external_config.set_enabled("odoo", False)
    assert odoo_partner_update.is_configured() is False
    with pytest.raises(odoo_client.OdooConfigError, match="Odoo désactivée"):
        odoo_client.from_app_config()


def test_helloasso_factory_refuses_when_disabled(app):
    from app.services import helloasso_client

    external_config.set_many("helloasso", HELLOASSO)
    helloasso_client.from_app_config()
    external_config.set_enabled("helloasso", False)
    with pytest.raises(helloasso_client.HelloAssoConfigError, match="HelloAsso désactivée"):
        helloasso_client.from_app_config()


def test_ga4_and_facebook_factories_refuse_when_disabled(app):
    from app.services import facebook_client, ga4_client

    external_config.set_many("ga4", {"property_id": "1", "credentials_json": "{}"})
    external_config.set_many("facebook", {"page_id": "1", "page_token": "tok"})
    external_config.set_enabled("ga4", False)
    external_config.set_enabled("facebook", False)
    with pytest.raises(ga4_client.GA4ConfigError, match="désactivée"):
        ga4_client.from_app_config()
    with pytest.raises(facebook_client.FacebookConfigError, match="désactivée"):
        facebook_client.from_app_config()


def test_stancer_refuses_when_disabled(app):
    from app.services import stancer_sync

    external_config.set_many("stancer", {"secret_key": "sprod_x"})
    assert stancer_sync._get_secret_key() == "sprod_x"
    external_config.set_enabled("stancer", False)
    with pytest.raises(RuntimeError, match="Stancer désactivée"):
        stancer_sync._get_secret_key()


def test_smtp_disabled_overrides_env(app):
    from app.services import membership_reminders

    external_config.set_enabled("smtp", False)
    assert membership_reminders.smtp_configured() is False


def test_metrics_sync_skips_disabled_sources_silently(app):
    from app.services import metrics_sync

    external_config.set_enabled("ga4", False)
    external_config.set_enabled("facebook", False)
    result = metrics_sync.sync_metrics(2026, 10)
    assert result["ga4"] == {"imported": 0, "errors": [], "disabled": True}
    assert result["facebook"] == {"imported": 0, "errors": [], "disabled": True}


# ------------------------------------------------------------------ écrans

def test_payouts_disabled_notice_and_no_sync(admin):
    external_config.set_many("stancer", {"secret_key": "sprod_x"})
    html = admin.get("/payouts/").get_data(as_text=True)
    assert "Stancer</strong>" not in html  # disponible : pas de bandeau

    external_config.set_enabled("stancer", False)
    html = admin.get("/payouts/").get_data(as_text=True)
    assert "Intégration <strong>Stancer</strong>" in html and "désactivée" in html
    assert "/configuration/integrations/stancer" in html

    resp = admin.post("/payouts/sync", headers={"HX-Request": "true"})
    assert "Stancer désactivée" in resp.get_data(as_text=True)
    assert db.session.query(SyncJob).count() == 0


def test_orders_and_invoices_unconfigured_notice(admin):
    for url in ("/orders/", "/customer-invoices/"):
        html = admin.get(url).get_data(as_text=True)
        assert "Intégration <strong>Odoo</strong>" in html, url
        assert "non configurée" in html, url


def test_entities_helloasso_disabled_notice(admin):
    external_config.set_many("helloasso", HELLOASSO)
    external_config.set_enabled("helloasso", False)
    html = admin.get("/entities/").get_data(as_text=True)
    assert "Intégration <strong>HelloAsso</strong>" in html and "désactivée" in html


def test_members_smtp_disabled_notice(admin):
    external_config.set_enabled("smtp", False)
    html = admin.get("/entities/members").get_data(as_text=True)
    assert "Intégration <strong>SMTP (relance email)</strong>" in html
    assert "relance email indisponible" in html


def test_non_admin_sees_no_integration_link(login_as):
    client = login_as(is_admin=False)
    external_config.set_enabled("smtp", False)
    html = client.get("/entities/members").get_data(as_text=True)
    assert "Contactez un administrateur." in html
    assert "/configuration/integrations/smtp" not in html


def test_impact_sync_buttons_disabled(admin):
    html = admin.get("/impact/").get_data(as_text=True)
    assert 'title="GA4 et Facebook indisponibles"' in html
    assert 'title="GA4 indisponible"' in html
