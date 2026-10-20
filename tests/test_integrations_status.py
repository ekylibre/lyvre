"""Activation, empreinte et statut des intégrations (external_config, integrations)."""
import json
from datetime import datetime, timedelta

import pytest

from app.extensions import db
from app.models import IntegrationState, SyncJob
from app.services import external_config, integrations


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


# --------------------------------------------------------------------- statuts

ODOO = {"url": "https://erp.example.org", "db": "prod", "username": "a@b.fr", "api_key": "k-123456"}


def _probe_ok(monkeypatch, service, message="OK"):
    monkeypatch.setitem(integrations.PROBES, service, lambda: message)


def _probe_fail(monkeypatch, service, exc):
    def boom():
        raise exc
    monkeypatch.setitem(integrations.PROBES, service, boom)


def test_status_disabled_wins(app):
    external_config.set_enabled("odoo", False)
    assert integrations.status("odoo") == integrations.STATUS_DISABLED


def test_status_unconfigured(app):
    assert integrations.status("odoo") == integrations.STATUS_UNCONFIGURED


def test_status_untested_then_ok(app, monkeypatch):
    external_config.set_many("odoo", ODOO)
    assert integrations.status("odoo") == integrations.STATUS_UNTESTED
    _probe_ok(monkeypatch, "odoo")
    integrations.run_check("odoo")
    assert integrations.status("odoo") == integrations.STATUS_OK


def test_status_error(app, monkeypatch):
    external_config.set_many("odoo", ODOO)
    _probe_fail(monkeypatch, "odoo", RuntimeError("boom"))
    assert integrations.run_check("odoo").ok is False
    assert integrations.status("odoo") == integrations.STATUS_ERROR


def test_failed_check_on_modified_config_is_untested(app, monkeypatch):
    external_config.set_many("odoo", ODOO)
    _probe_fail(monkeypatch, "odoo", RuntimeError("boom"))
    integrations.run_check("odoo")
    external_config.set_many("odoo", {**ODOO, "api_key": "k-654321"})
    view = integrations.detail("odoo")
    assert view.status == integrations.STATUS_UNTESTED
    assert view.check_outdated is True
    assert view.last_check is not None and view.last_check.ok is False


def test_disabling_keeps_last_check(app, monkeypatch):
    external_config.set_many("odoo", ODOO)
    _probe_ok(monkeypatch, "odoo")
    integrations.run_check("odoo")
    external_config.set_enabled("odoo", False)
    assert integrations.status("odoo") == integrations.STATUS_DISABLED
    external_config.set_enabled("odoo", True)
    assert integrations.status("odoo") == integrations.STATUS_OK


def test_overview_lists_every_service_in_order(app):
    views = integrations.overview()
    assert [v.slug for v in views] == list(external_config.SERVICE_KEYS)
    smtp = next(v for v in views if v.slug == "smtp")
    assert smtp.status == integrations.STATUS_UNTESTED  # configuré par .env
    assert smtp.status_label == "Non testée"
    assert smtp.description


def test_last_sync_not_tracked(app):
    view = integrations.detail("odoo")
    assert view.sync_tracked is False
    assert view.last_sync is None


def test_last_sync_stancer_latest_job(app):
    old = SyncJob(kind="payouts", status="done", started_at=datetime.utcnow() - timedelta(days=1))
    new = SyncJob(kind="payout_payments", status="failed", message="HTTP 500",
                  started_at=datetime.utcnow())
    db.session.add_all([old, new, SyncJob(kind="metrics", status="done")])
    db.session.commit()
    info = integrations.last_sync("stancer")
    assert info.status == "failed"
    assert info.message == "HTTP 500"
    assert info.endpoint == "payouts.index"


def test_last_sync_metrics_split_by_source(app):
    db.session.add(SyncJob(kind="metrics", status="done", result_json=json.dumps({
        "ga4": {"imported": 5, "errors": []},
        "facebook": {"imported": 0, "errors": ["Facebook : token expiré"]},
    })))
    db.session.commit()
    ga4 = integrations.last_sync("ga4")
    facebook = integrations.last_sync("facebook")
    assert (ga4.imported, ga4.errors) == (5, [])
    assert (facebook.imported, facebook.errors) == (0, ["Facebook : token expiré"])
    assert facebook.endpoint == "impact.index"
    assert integrations.last_sync("stancer") is None
