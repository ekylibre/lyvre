"""Tests de la configuration SMTP en base (service external_config 'smtp')."""
from app.services import external_config


def test_smtp_service_declared():
    assert "smtp" in external_config.SERVICE_KEYS
    assert external_config.SERVICE_KEYS["smtp"] == [
        "host", "port", "use_tls", "username", "password", "sender",
    ]
    assert external_config.SERVICE_REQUIRED_KEYS["smtp"] == ["host", "sender"]
    assert external_config.SERVICE_LABELS["smtp"]


def test_smtp_env_fallback_configured(app):
    # Repli .env (conftest) -> configuré.
    assert external_config.is_configured("smtp") is True
    assert external_config.source("smtp", "host") == "env"


def test_smtp_db_overrides_env(app):
    external_config.set_many("smtp", {
        "host": "smtp.tenant.local",
        "port": "2525",
        "use_tls": "false",
        "username": "u@tenant.local",
        "password": "secret",
        "sender": "Tenant <noreply@tenant.local>",
    })
    assert external_config.get("smtp", "host") == "smtp.tenant.local"
    assert external_config.source("smtp", "host") == "db"

    from app.services import membership_reminders as mr
    s = mr.smtp_settings()
    assert s["host"] == "smtp.tenant.local"
    assert s["port"] == 2525
    assert s["use_tls"] is False
    assert s["sender"] == "Tenant <noreply@tenant.local>"


def test_smtp_clearing_db_falls_back_to_env(app):
    external_config.set_many("smtp", {"host": "smtp.tenant.local", "sender": "a@b.fr"})
    assert external_config.source("smtp", "host") == "db"
    # Vider -> suppression DB -> repli .env reprend.
    external_config.set_many("smtp", {k: "" for k in external_config.SERVICE_KEYS["smtp"]})
    assert external_config.source("smtp", "host") == "env"
