"""Lancement asynchrone des synchronisations Stancer.

Chaque appel à `start_sync_payouts(app)` ou `start_sync_payments_for_payout(app, payout_id)`
crée un `SyncJob` en base, démarre un thread qui exécute la sync correspondante en
poussant un `app_context()`, et met à jour la progression du job au fil du traitement.

Le frontend consulte `/payouts/sync/status/<job_id>` (HTMX polling) pour suivre l'avancée.
"""
import json
import threading
from datetime import datetime

import requests
from sqlalchemy import or_

from app.extensions import db
from app.models import Payout, SyncJob
from app.models.sync_job import (
    SYNC_KIND_PAYOUTS,
    SYNC_KIND_PAYOUT_PAYMENTS,
    SYNC_STATUS_RUNNING,
    SYNC_STATUS_DONE,
    SYNC_STATUS_FAILED,
)
from app.services import stancer_sync


# Throttle des écritures DB de progression : on ne pousse qu'à chaque 5e tick
# pour éviter de saturer SQLite quand le sync défile vite.
_PROGRESS_THROTTLE = 5


def _running_job(kind, payout_id=None):
    return SyncJob.query.filter_by(
        kind=kind,
        payout_id=payout_id,
        status=SYNC_STATUS_RUNNING,
    ).first()


def _create_job(kind, payout_id=None, message="Démarrage…"):
    job = SyncJob(
        kind=kind,
        payout_id=payout_id,
        status=SYNC_STATUS_RUNNING,
        message=message,
    )
    db.session.add(job)
    db.session.commit()
    return job


def _make_progress_cb(job_id):
    """Retourne un callback (done, total, message) qui met à jour le job en DB.

    Le callback est appelé depuis le thread de travail ; il utilise sa propre
    session SQLAlchemy via `db.session.get(...)` et commit immédiatement.
    """
    state = {"calls": 0}

    def _cb(done, total, message):
        state["calls"] += 1
        if state["calls"] % _PROGRESS_THROTTLE != 0:
            return
        job = db.session.get(SyncJob, job_id)
        if job is None:
            return
        job.progress_done = done or 0
        if total is not None:
            job.progress_total = total
        if message:
            job.message = message
        db.session.commit()

    return _cb


def _finalize(job_id, status, message=None, result=None):
    job = db.session.get(SyncJob, job_id)
    if job is None:
        return
    job.status = status
    job.finished_at = datetime.utcnow()
    if message is not None:
        job.message = message
    if result is not None:
        job.result_json = json.dumps(result, ensure_ascii=False, default=str)
    db.session.commit()


def _run_in_thread(app, job_id, work):
    """Pousse un app_context, exécute `work()` et finalise le job."""
    with app.app_context():
        try:
            result = work(job_id)
            _finalize(
                job_id,
                SYNC_STATUS_DONE,
                message="Synchronisation terminée.",
                result=result,
            )
        except RuntimeError as e:
            db.session.rollback()
            _finalize(job_id, SYNC_STATUS_FAILED, message=str(e))
        except requests.HTTPError as e:
            db.session.rollback()
            status = e.response.status_code if e.response is not None else "?"
            body = e.response.text[:200] if e.response is not None else ""
            _finalize(
                job_id, SYNC_STATUS_FAILED,
                message=f"Erreur API Stancer : {status} {body}",
            )
        except Exception as e:  # noqa: BLE001
            db.session.rollback()
            _finalize(job_id, SYNC_STATUS_FAILED, message=f"Erreur : {e}")


def start_sync_payouts(app):
    """Démarre (ou retourne) un job de sync globale des payouts.

    Idempotent : si un job de même nature est déjà en cours, on le retourne tel quel.
    """
    existing = _running_job(SYNC_KIND_PAYOUTS)
    if existing:
        return existing
    job = _create_job(SYNC_KIND_PAYOUTS, message="Démarrage de la synchronisation…")

    def work(job_id):
        cb = _make_progress_cb(job_id)
        return stancer_sync.sync_payouts(progress_cb=cb)

    threading.Thread(
        target=_run_in_thread, args=(app, job.id, work), daemon=True,
    ).start()
    return job


def start_sync_payments_for_payout(app, payout_id):
    """Démarre (ou retourne) un job de sync ciblé sur les payments d'un payout."""
    existing = _running_job(SYNC_KIND_PAYOUT_PAYMENTS, payout_id=payout_id)
    if existing:
        return existing
    job = _create_job(
        SYNC_KIND_PAYOUT_PAYMENTS,
        payout_id=payout_id,
        message="Démarrage de la synchronisation des paiements…",
    )

    def work(job_id):
        cb = _make_progress_cb(job_id)
        payout = db.session.get(Payout, payout_id)
        if payout is None:
            raise RuntimeError("Payout introuvable")
        imported, updated, total = stancer_sync.sync_payments_for_payout(
            payout, progress_cb=cb,
        )
        db.session.commit()
        return {"imported": imported, "updated": updated, "total": total}

    threading.Thread(
        target=_run_in_thread, args=(app, job.id, work), daemon=True,
    ).start()
    return job


def latest_payouts_job():
    """Renvoie le job de sync globale le plus récent (running ou non)."""
    return (
        SyncJob.query.filter_by(kind=SYNC_KIND_PAYOUTS)
        .order_by(SyncJob.started_at.desc())
        .first()
    )


def latest_job_for_payout(payout_id):
    return (
        SyncJob.query.filter(
            or_(
                SyncJob.payout_id == payout_id,
                SyncJob.kind == SYNC_KIND_PAYOUTS,
            )
        )
        .order_by(SyncJob.started_at.desc())
        .first()
    )
