"""Activation et empreinte des intégrations (external_config, table integration_states)."""
import pytest

from app.extensions import db
from app.models import IntegrationState
from app.services import external_config


def test_every_service_has_a_description():
    assert set(external_config.SERVICE_DESCRIPTIONS) == set(external_config.SERVICE_KEYS)


def test_secret_keys_belong_to_their_service():
    for service, key in external_config.SECRET_KEYS:
        assert key in external_config.SERVICE_KEYS[service]


def test_enabled_by_default_without_row(app):
    assert db.session.query(IntegrationState).count() == 0
    for service in external_config.SERVICE_KEYS:
        assert external_config.is_enabled(service) is True


def test_set_enabled_round_trip(app):
    external_config.set_enabled("odoo", False)
    assert external_config.is_enabled("odoo") is False
    assert external_config.is_enabled("stancer") is True
    external_config.set_enabled("odoo", True)
    assert external_config.is_enabled("odoo") is True
    assert db.session.query(IntegrationState).filter_by(service="odoo").count() == 1


def test_set_enabled_unknown_service(app):
    with pytest.raises(ValueError):
        external_config.set_enabled("nope", False)


def test_switch_takes_precedence_over_env_fallback(app):
    # SMTP est configuré par le repli .env (conftest).
    assert external_config.source("smtp", "host") == "env"
    assert external_config.is_available("smtp") is True
    external_config.set_enabled("smtp", False)
    assert external_config.is_configured("smtp") is True
    assert external_config.is_available("smtp") is False


def test_available_requires_configuration(app):
    assert external_config.is_enabled("odoo") is True
    assert external_config.is_configured("odoo") is False
    assert external_config.is_available("odoo") is False


def test_fingerprint_stable_and_changes_with_db_value(app):
    before = external_config.fingerprint("odoo")
    assert before == external_config.fingerprint("odoo")
    assert len(before) == 64
    external_config.set_many("odoo", {"url": "https://erp.example.org"})
    assert external_config.fingerprint("odoo") != before


def test_fingerprint_changes_with_env_fallback(app):
    before = external_config.fingerprint("smtp")
    app.config["MAIL_SERVER"] = "smtp.other.example.org"
    external_config._cache().clear()
    assert external_config.fingerprint("smtp") != before


def test_fingerprint_ignores_switch(app):
    before = external_config.fingerprint("smtp")
    external_config.set_enabled("smtp", False)
    assert external_config.fingerprint("smtp") == before
