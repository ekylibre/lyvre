"""Synchronisations en arrière-plan suivies par un `SyncJob`.

`start(app, kind, work, …)` crée le job dans la base de l'instance courante, puis
exécute `work(job_id)` dans un fil d'exécution. Le fil pousse un `app_context` et
**sélectionne la même instance** (`g.current_instance`, `g.tenant_engine`) : sans
cela, `db.session` retomberait sur la base par défaut et non sur celle de l'instance.

Le frontend suit l'avancement en interrogeant le job (`GET /api/v1/jobs/<id>`). Le job terminé
(succès ou échec), une notification est créée pour l'utilisateur qui l'a lancé
(`services/notifications.py`), même s'il a quitté l'écran entre-temps.
"""
import json
import threading
from datetime import datetime

from flask import g, has_request_context
from flask_login import current_user

from app.extensions import db
from app.models import Instance, SyncJob
from app.models.sync_job import SYNC_STATUS_DONE, SYNC_STATUS_FAILED, SYNC_STATUS_RUNNING
from app.tenant import current_instance, get_tenant_engine

# Écritures de progression limitées à 1 appel sur 5 pour ne pas saturer SQLite.
PROGRESS_THROTTLE = 5


def running_job(kind, **filters):
    """Job de ce type encore en cours (filtres sur les colonnes du job), ou None."""
    return SyncJob.query.filter_by(kind=kind, status=SYNC_STATUS_RUNNING, **filters).first()


def progress_callback(job_id, throttle=PROGRESS_THROTTLE):
    """Callback (done, total, message) qui met à jour le job, appelé depuis le fil."""
    state = {"calls": 0}

    def _cb(done, total, message):
        state["calls"] += 1
        if state["calls"] % throttle != 0:
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


def _default_error_message(exc):
    if isinstance(exc, RuntimeError):
        return str(exc)
    return f"Erreur : {exc}"


def _select_instance(instance_id):
    """Reproduit dans le fil la sélection d'instance faite par `tenant._select_tenant`."""
    g.tenant_engine = None
    g.current_instance = None
    if instance_id is None:
        return
    instance = db.session.get(Instance, instance_id)
    if instance is not None:
        g.current_instance = instance
        g.tenant_engine = get_tenant_engine(instance)


def _notify(app, job_id):
    """Notification de fin : son échec ne change rien au job (déjà terminé et enregistré)."""
    from app.services import notifications

    try:
        job = db.session.get(SyncJob, job_id)
        if job is not None:
            notifications.notify_job(job)
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        app.logger.warning("Notification of sync job %s failed: %r", job_id, exc)


def run(app, instance_id, job_id, work, error_message=_default_error_message):
    """Corps du fil d'exécution (appelable directement en test)."""
    with app.app_context():
        _select_instance(instance_id)
        try:
            result = work(job_id)
            _finalize(job_id, SYNC_STATUS_DONE, message="Synchronisation terminée.", result=result)
        except Exception as exc:  # noqa: BLE001 — tout échec termine le job
            db.session.rollback()
            app.logger.warning("Sync job %s failed: %r", job_id, exc)
            _finalize(job_id, SYNC_STATUS_FAILED, message=error_message(exc))
        _notify(app, job_id)


def _current_user_id():
    """Utilisateur de la requête qui lance le job (aucun hors requête : CLI, tâche planifiée)."""
    if not has_request_context() or not current_user.is_authenticated:
        return None
    return current_user.id


def start(app, kind, work, *, message="Démarrage…", error_message=_default_error_message,
          **job_fields):
    """Crée le job (ou renvoie celui déjà en cours avec les mêmes champs) et lance `work`."""
    existing = running_job(kind, **job_fields)
    if existing:
        return existing
    job = SyncJob(kind=kind, status=SYNC_STATUS_RUNNING, message=message,
                  started_by_user_id=_current_user_id(), **job_fields)
    db.session.add(job)
    db.session.commit()

    instance = current_instance()
    threading.Thread(
        target=run,
        args=(app, instance.id if instance is not None else None, job.id, work, error_message),
        daemon=True,
    ).start()
    return job
