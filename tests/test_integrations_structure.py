"""Intégrations selon la structure (lot I1) : applicabilité, interrupteur en base méta, repli .env
en développement seulement, initialisation d'une instance existante, proposition, création
d'instance, « intégration nécessaire », notifications."""
import json
from datetime import datetime

import pytest

from app.extensions import db
from app.models import Instance, IntegrationState, Notification, SyncJob
from app.models.sync_job import SYNC_KIND_QONTO
from app.services import external_config, notifications

API = "/api/v1/integrations"
QONTO = {"login": "sci-1234", "secret_key": "qonto-secret"}


def _instance():
    return Instance.query.filter_by(slug="test").one()


def _structure(chart, integrations=None):
    inst = _instance()
    inst.chart = chart
    inst.integrations = json.dumps({"enabled": integrations or [], "dismissed": []})
    db.session.commit()
    return inst


@pytest.fixture()
def admin(login_as):
    return login_as(role="admin")


# ------------------------------------------------------------- applicabilité

def test_sci_lists_only_its_integrations(admin):
    _structure("sci", ["qonto", "helloasso"])
    items = admin.get(API).get_json()["items"]
    assert [i["slug"] for i in items] == ["stancer", "odoo", "smtp", "qonto", "docuseal"]
    assert admin.get(f"{API}/helloasso").status_code == 404
    assert admin.post(f"{API}/ga4/enabled", json={"enabled": True}).status_code == 404
    # Non applicable : éteinte, même présente dans les interrupteurs.
    assert external_config.is_enabled("helloasso") is False and external_config.is_enabled("qonto") is True


def test_recommended_flag(admin):
    _structure("sci")
    items = {i["slug"]: i for i in admin.get(API).get_json()["items"]}
    assert items["qonto"]["recommended"] is True and items["smtp"]["recommended"] is False
    _structure("asso")
    items = {i["slug"]: i for i in admin.get(API).get_json()["items"]}
    assert items["helloasso"]["recommended"] is True and items["qonto"]["recommended"] is False


def test_switch_lives_in_meta(admin):
    _structure("asso")
    assert external_config.is_enabled("smtp") is False
    body = admin.post(f"{API}/smtp/enabled", json={"enabled": True}).get_json()
    assert body["item"]["enabled"] is True
    assert _instance().enabled_integrations() == {"smtp"}
    assert db.session.query(IntegrationState).filter_by(service="smtp").first() is None


# ------------------------------------------------------------- repli .env

def test_env_fallback_only_when_flag_is_set(app, instance):
    assert external_config.source("smtp", "host") == "env" and external_config.is_configured("smtp")
    app.config["INTEGRATIONS_ENV_FALLBACK"] = False
    external_config._cache().clear()  # cache de la requête
    assert external_config.source("smtp", "host") == "none"
    assert external_config.get("smtp", "host") is None and not external_config.is_configured("smtp")


def test_production_config_has_no_env_fallback():
    from app.config import ProductionConfig

    assert ProductionConfig.INTEGRATIONS_ENV_FALLBACK is False


# ------------------------------------------------------------- initialisation

def test_existing_instance_initialized_from_its_settings(admin):
    inst = _instance()
    inst.chart = "sci"
    external_config.set_many("qonto", QONTO)          # paramétrée en base : activée
    external_config.set_many("helloasso", {"client_id": "a", "client_secret": "b", "org_slug": "c"})  # autre structure
    external_config.set_many("odoo", {"url": "u", "db": "d", "username": "n", "api_key": "k"})
    db.session.add(IntegrationState(service="odoo", enabled=False))  # désactivée auparavant
    inst.integrations = None                           # jamais initialisée ; SMTP vient du .env seul
    db.session.commit()

    session = admin.get("/api/v1/session").get_json()
    assert session["instance"]["integrations"]["enabled"] == ["qonto"] and session["instance"]["integrations"]["proposed"] == []
    assert json.loads(_instance().integrations) == {"enabled": ["qonto"], "dismissed": []}


def test_initialization_on_first_tenant_request(admin):
    inst = _instance()
    external_config.set_many("stancer", {"secret_key": "sprod_x"})
    inst.integrations = None
    db.session.commit()
    admin.get("/api/v1/payouts")
    assert _instance().enabled_integrations() == {"stancer"}


# ------------------------------------------------------------- session, menus, proposition

def test_session_enabled_proposed_and_menus(app, login_as):
    treasurer = login_as()
    _structure("sci", ["odoo"])
    body = treasurer.get("/api/v1/session").get_json()
    integrations = body["instance"]["integrations"]
    assert (integrations["enabled"], integrations["proposed"]) == (["odoo"], [])  # pas admin
    keys = [m["key"] for m in body["nav"]]
    assert "odoo" in keys
    banque = next(m for m in body["nav"] if m["key"] == "banque")
    assert "payouts" not in [i.get("key") for i in banque["items"]]


def test_dismiss_removes_the_proposal(admin):
    _structure("sci")
    assert admin.get("/api/v1/session").get_json()["instance"]["integrations"]["proposed"] == ["qonto"]
    assert admin.post(f"{API}/qonto/dismiss").status_code == 200
    assert admin.get("/api/v1/session").get_json()["instance"]["integrations"]["proposed"] == []
    admin.post(f"{API}/qonto/enabled", json={"enabled": True})
    assert _instance().dismissed_integrations() == {"qonto"}  # écartée reste mémorisé


def test_dismiss_admin_only(login_as):
    client = login_as()
    assert client.post(f"{API}/qonto/dismiss").status_code == 403


# ------------------------------------------------------------- création d'instance

def test_instance_creation_with_integrations(app, login_as, monkeypatch, tmp_path):
    from app.services import instance_provisioning

    monkeypatch.setattr(app, "instance_path", str(tmp_path / "instance"))
    monkeypatch.setattr(instance_provisioning, "BASE_DIR", tmp_path)
    monkeypatch.setattr("app.api.instances.provision_sqlite_database", lambda url, chart: None)
    client = login_as(is_admin=True)

    meta = client.get("/api/v1/instances").get_json()["meta"]["integrations_by_chart"]
    assert [(i["value"], i["recommended"]) for i in meta["sci"]] == [
        ("stancer", False), ("odoo", False), ("smtp", False), ("qonto", True), ("docuseal", False)]
    assert "helloasso" in [i["value"] for i in meta["asso"]]

    assert client.post("/api/v1/instances", json={"slug": "sci-a", "label": "A", "chart": "sci"}).status_code == 201
    assert Instance.query.filter_by(slug="sci-a").one().enabled_integrations() == {"qonto"}  # défaut : recommandées
    client.post("/api/v1/instances", json={"slug": "sci-b", "label": "B", "chart": "sci",
                                           "integrations": ["smtp", "helloasso"]})
    assert Instance.query.filter_by(slug="sci-b").one().enabled_integrations() == {"smtp"}  # HelloAsso ignorée
    resp = client.post("/api/v1/instances", json={"slug": "sci-c", "label": "C", "chart": "sci", "integrations": "qonto"})
    assert resp.status_code == 422


# ------------------------------------------------------------- intégration nécessaire

def test_required_vs_unconfigured(admin):
    _structure("asso")
    error = admin.post("/api/v1/members/reminders", json={"ids": []}).get_json()["error"]
    assert error == {"code": "integration_required", "service": "smtp",
                     "message": "Cette action nécessite l'intégration SMTP (emails), désactivée."}
    _structure("asso", ["odoo"])
    error = admin.post("/api/v1/members/odoo-notes", json={"ids": []}).get_json()["error"]
    assert error["code"] == "conflict" and "Odoo non configurée" in error["message"]


def test_disabled_integration_state_is_silent(admin):
    _structure("asso")
    assert admin.get("/api/v1/payouts").get_json()["meta"]["stancer"] == {
        "enabled": False, "available": False, "message": None}
    _structure("asso", ["stancer"])
    stancer = admin.get("/api/v1/payouts").get_json()["meta"]["stancer"]
    assert stancer["enabled"] is True and stancer["available"] is False and "non configurée" in stancer["message"]


# ------------------------------------------------------------- notifications

def test_no_notification_for_a_disabled_integration(admin):
    _structure("sci")
    job = SyncJob(kind=SYNC_KIND_QONTO, status="done", finished_at=datetime.utcnow())
    db.session.add(job)
    db.session.commit()
    assert notifications.notify_job(job) is None and Notification.query.count() == 0
    _structure("sci", ["qonto"])
    assert notifications.notify_job(job) is not None


# ------------------------------------------------------------- script de constat

def test_report_script_lists_keys_never_values(app, instance, monkeypatch):
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "integrations_report", Path(__file__).resolve().parent.parent / "scripts" / "integrations_report.py")
    report = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report)
    external_config.set_many("qonto", QONTO)
    for name in ("ODOO_URL", "ODOO_DB", "ODOO_USERNAME"):  # .env chargé par un autre test (run.py)
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ODOO_API_KEY", "odoo-secret-value")
    instance.integrations = None
    db.session.commit()
    lines = report._report(instance)
    text = "\n".join(lines)
    assert "interrupteurs non initialisés" in lines[0]
    assert "Qonto : activée" in text and "Odoo : désactivée ; fournies par le .env, absentes de la base : api_key" in text
    assert "qonto-secret" not in text and "odoo-secret-value" not in text
    assert instance.integrations is None  # lecture seule
