"""Notifications de fin de tâche en arrière-plan : création, destinataire, API."""
import json
from datetime import datetime, timedelta

import pytest

from app.extensions import db
from app.models import Notification, SyncJob
from app.models.sync_job import SYNC_KIND_PAYOUTS, SYNC_KIND_QONTO, SYNC_KIND_QONTO_INVOICES
from app.services import notifications, sync_jobs
from test_sync_jobs import ImmediateThread, _default_rows, _rows, other_instance  # noqa: F401


def _job(kind=SYNC_KIND_QONTO, status="done", result=None, message=None, **fields):
    job = SyncJob(kind=kind, status=status, message=message, finished_at=datetime.utcnow(),
                  result_json=json.dumps(result) if result is not None else None, **fields)
    db.session.add(job)
    db.session.commit()
    return job


# ------------------------------------------------------------------ contenu


def test_done_job_notifies_author_with_summary_and_link(app):
    job = _job(result={"created": 3, "updated": 1, "rules_posted": 2, "errors": []},
               bank_account_id=None, started_by_user_id=7)
    note = notifications.notify_job(job)
    assert (note.user_id, note.kind, note.level) == (7, "job_done", "success")
    assert note.title == "Synchronisation des transactions Qonto terminée"
    assert note.message == "3 transaction(s) importée(s), 1 mise(s) à jour, 2 écriture(s) de règle."
    assert note.url == "/bank-accounts/" and note.job_id == job.id and not note.is_read


def test_errors_in_result_give_a_warning(app):
    job = _job(SYNC_KIND_QONTO_INVOICES, result={"created": 1, "read": 2, "errors": ["Facture X : montant ?", "Y"]})
    note = notifications.notify_job(job)
    assert note.level == "warning" and note.title.endswith("terminée avec des erreurs")
    assert note.message.endswith("2 erreur(s), dont : Facture X : montant ?")
    assert note.url == "/purchases/" and note.user_id is None  # auteur inconnu : toute l'instance


def test_failed_job_gives_danger_with_job_message(app):
    note = notifications.notify_job(_job(SYNC_KIND_PAYOUTS, status="failed", message="Stancer injoignable"))
    assert (note.kind, note.level, note.message) == ("job_failed", "danger", "Stancer injoignable")
    assert note.title == "Synchronisation des versements Stancer : échec" and note.url == "/payouts/"


def test_running_job_is_not_notified(app):
    assert notifications.notify_job(_job(status="running")) is None
    assert Notification.query.count() == 0


def test_unknown_kind_has_generic_title(app):
    note = notifications.notify_job(_job("autre", result={}))
    assert note.title == "Tâche en arrière-plan terminée" and note.url is None


# ------------------------------------------------------------------ fil d'exécution


def test_thread_notifies_on_current_instance(app, other_instance):  # noqa: F811
    sync_jobs.start(app, SYNC_KIND_QONTO, lambda job_id: {"created": 1, "errors": []}, bank_account_id=None)
    assert _rows(other_instance, "SELECT kind, level, user_id FROM notifications") == [("job_done", "success", None)]
    assert _default_rows("SELECT COUNT(*) FROM notifications") == [(0,)]


def test_thread_failure_is_notified(app, other_instance):  # noqa: F811
    def work(job_id):
        raise RuntimeError("Plus de réseau")
    sync_jobs.start(app, SYNC_KIND_QONTO, work)
    assert _rows(other_instance, "SELECT level, message FROM notifications") == [("danger", "Plus de réseau")]


def test_notification_failure_does_not_change_job(app, other_instance, monkeypatch):  # noqa: F811
    def boom(job):
        raise RuntimeError("panne")
    monkeypatch.setattr(notifications, "notify_job", boom)
    sync_jobs.start(app, "test_kind", lambda job_id: {"ok": 1})
    assert _rows(other_instance, "SELECT status FROM sync_jobs") == [("done",)]


def test_job_records_the_user_who_started_it(app, login_as, monkeypatch):
    from app.models import BankAccount, Account
    from app.services import qonto_sync
    monkeypatch.setattr(sync_jobs.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(qonto_sync, "sync_bank_account", lambda ba_id, progress_cb=None: {"created": 0, "errors": []})
    client = login_as()
    account = Account(code="512100", label="Banque", account_type="ASSET")
    db.session.add(account)
    db.session.flush()
    ba = BankAccount(label="Qonto", account_id=account.id, qonto_account_id="acc-1")
    db.session.add(ba)
    db.session.commit()
    from app.services import external_config
    external_config.set_many("qonto", {"login": "org", "secret_key": "s"})
    resp = client.post(f"/api/v1/bank-accounts/{ba.id}/qonto/sync")
    assert resp.status_code == 200, resp.get_json()
    from app.models import User
    user = User.query.filter_by(email="user@example.org").one()
    assert SyncJob.query.one().started_by_user_id == user.id
    note = Notification.query.one()
    assert note.user_id == user.id and note.url == f"/bank-accounts/{ba.id}/transactions"


# ------------------------------------------------------------------ API


@pytest.fixture()
def client(login_as):
    return login_as()


def _me():
    from app.models import User
    return User.query.filter_by(email="user@example.org").one().id


def _note(user_id, title="N", read=False, created=None):
    note = Notification(user_id=user_id, kind="job_done", level="success", title=title,
                        created_at=created or datetime.utcnow(), read_at=datetime.utcnow() if read else None)
    db.session.add(note)
    db.session.commit()
    return note


def test_api_lists_own_and_instance_notifications_only(client):
    me = _me()
    _note(me, "à moi", created=datetime(2026, 10, 1))
    _note(None, "pour tous", created=datetime(2026, 10, 2))
    _note(me + 100, "à un autre")
    _note(me, "déjà lue", read=True, created=datetime(2026, 9, 1))
    body = client.get("/api/v1/notifications").get_json()
    assert [n["title"] for n in body["items"]] == ["pour tous", "à moi", "déjà lue"]
    assert body["meta"]["unread"] == 2
    assert [n["title"] for n in client.get("/api/v1/notifications?unread=1").get_json()["items"]] == ["pour tous", "à moi"]
    assert len(client.get("/api/v1/notifications?limit=1").get_json()["items"]) == 1


def test_api_mark_read(client):
    me = _me()
    mine, other = _note(me, "à moi"), _note(me + 100, "à un autre")
    body = client.post("/api/v1/notifications/read", json={"ids": [mine.id, other.id]}).get_json()
    assert body == {"marked": 1, "meta": {"unread": 0}}  # celle d'un autre n'est pas touchée
    assert db.session.get(Notification, other.id).read_at is None
    _note(me, "deux"), _note(None, "trois")
    assert client.post("/api/v1/notifications/read", json={}).get_json()["marked"] == 2
    assert client.post("/api/v1/notifications/read", json={"ids": "1"}).status_code == 422


def test_api_requires_login(app):
    assert app.test_client().get("/api/v1/notifications").status_code == 401


def test_purge_old_read_notifications(app):
    old = _note(1, "vieille", read=True)
    old.read_at = datetime.utcnow() - timedelta(days=notifications.RETENTION_DAYS + 1)
    unread_old = _note(1, "non lue", created=datetime.utcnow() - timedelta(days=400))
    db.session.commit()
    notifications.purge()
    db.session.commit()
    assert [n.title for n in Notification.query.all()] == [unread_old.title]
