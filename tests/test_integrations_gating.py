"""Une intégration désactivée est indisponible partout : clients, synchros, écrans."""
import pytest

from app.extensions import db
from app.models import SyncJob
from app.services import external_config

# Interrupteurs d'intégration : ceux de l'instance de test (conftest), toutes activées.
pytestmark = pytest.mark.usefixtures("instance")

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


def test_enabled_integration_uses_env_fallback_in_development(app):
    # Intégrations activées (instance de test) : la config .env suffit en développement.
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
    assert admin.get("/api/v1/payouts").get_json()["meta"]["stancer"]["available"] is True

    external_config.set_enabled("stancer", False)
    stancer = admin.get("/api/v1/payouts").get_json()["meta"]["stancer"]
    assert stancer == {"enabled": False, "available": False, "message": None}  # désactivée : rien à afficher

    resp = admin.post("/api/v1/payouts/sync")
    error = resp.get_json()["error"]
    assert resp.status_code == 409 and error["code"] == "integration_required" and "Stancer, désactivée" in error["message"]
    assert db.session.query(SyncJob).count() == 0

def test_orders_and_invoices_unconfigured_notice(admin):
    for url in ("/api/v1/orders", "/api/v1/customer-invoices"):
        odoo = admin.get(url).get_json()["meta"]["odoo"]
        assert odoo["available"] is False and "non configurée" in odoo["message"], url
        resp = admin.post(url + "/sync")
        assert resp.status_code == 409 and "Odoo" in resp.get_json()["error"]["message"], url


def test_impact_sync_sources_unavailable(admin):
    meta = admin.get("/api/v1/impact").get_json()["meta"]
    assert meta["ga4"]["available"] is False and meta["facebook"]["available"] is False
