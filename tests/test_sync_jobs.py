"""Synchronisations en arrière-plan : le fil d'exécution écrit dans la base de l'instance courante."""
import os

import pytest
import requests
from flask import g
from sqlalchemy import text

from app.extensions import db
from app.models import Instance, Journal, SyncJob
from app.services import stancer_async, stancer_sync, sync_jobs
from app.tenant import get_tenant_engine


class ImmediateThread:
    """Remplace threading.Thread : exécute la cible au start(), pour des tests déterministes."""

    def __init__(self, target, args=(), daemon=None):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


@pytest.fixture()
def other_instance(app, tmp_path, monkeypatch):
    """Instance B dont la base n'est PAS la base par défaut, sélectionnée comme dans une requête."""
    monkeypatch.setattr(sync_jobs.threading, "Thread", ImmediateThread)
    instance = Instance(slug="b", label="B", database_url=f"sqlite:///{tmp_path / 'b.db'}")
    db.session.add(instance)
    db.session.commit()
    engine = get_tenant_engine(instance)
    db.metadata.create_all(engine)
    with app.test_request_context():
        g.current_instance = instance
        g.tenant_engine = engine
        yield engine


def _rows(engine, sql):
    with engine.connect() as conn:
        return conn.execute(text(sql)).all()


def _default_rows(sql):
    with db.engines[None].connect() as conn:
        return conn.execute(text(sql)).all()


def test_job_and_data_written_to_current_instance(app, other_instance):
    def work(job_id):
        db.session.add(Journal(code="QZ", label="Écrit par le fil"))
        db.session.commit()
        return {"ok": 1}

    job = sync_jobs.start(app, "test_kind", work, message="Go")
    assert _rows(other_instance, "SELECT kind, status, result_json FROM sync_jobs") == [
        ("test_kind", "done", '{"ok": 1}')
    ]
    assert _rows(other_instance, "SELECT code FROM journals") == [("QZ",)]
    # Rien dans la base par défaut.
    assert _default_rows("SELECT COUNT(*) FROM sync_jobs") == [(0,)]
    assert _default_rows("SELECT COUNT(*) FROM journals WHERE code = 'QZ'") == [(0,)]
    assert job.id is not None


def test_failure_marks_job_failed(app, other_instance):
    def work(job_id):
        raise RuntimeError("Plus de réseau")

    sync_jobs.start(app, "test_kind", work)
    assert _rows(other_instance, "SELECT status, message FROM sync_jobs") == [
        ("failed", "Plus de réseau")
    ]


def test_running_job_is_returned_instead_of_starting_another(app, other_instance):
    job = SyncJob(kind="test_kind", status="running")
    db.session.add(job)
    db.session.commit()
    calls = []
    again = sync_jobs.start(app, "test_kind", lambda job_id: calls.append(job_id))
    assert again.id == job.id
    assert calls == []


def test_progress_callback_is_throttled(app, other_instance):
    job = SyncJob(kind="test_kind", status="running")
    db.session.add(job)
    db.session.commit()
    cb = sync_jobs.progress_callback(job.id, throttle=2)
    cb(1, 10, "un")
    assert db.session.get(SyncJob, job.id).progress_done == 0
    cb(2, 10, "deux")
    db.session.refresh(job)
    assert (job.progress_done, job.progress_total, job.message) == (2, 10, "deux")


def test_stancer_sync_runs_on_current_instance(app, other_instance, monkeypatch):
    monkeypatch.setattr(stancer_sync, "sync_payouts",
                        lambda progress_cb=None: {"imported": 3, "updated": 0, "total": 3})
    stancer_async.start_sync_payouts(app)
    assert _rows(other_instance, "SELECT kind, status FROM sync_jobs") == [("payouts", "done")]
    assert _default_rows("SELECT COUNT(*) FROM sync_jobs") == [(0,)]


def test_stancer_http_error_message(app, other_instance, monkeypatch):
    response = requests.Response()
    response.status_code = 401
    response._content = b"Invalid token"

    def boom(progress_cb=None):
        raise requests.HTTPError("401", response=response)
    monkeypatch.setattr(stancer_sync, "sync_payouts", boom)
    stancer_async.start_sync_payouts(app)
    assert _rows(other_instance, "SELECT status, message FROM sync_jobs") == [
        ("failed", "Erreur API Stancer : 401 Invalid token")
    ]
