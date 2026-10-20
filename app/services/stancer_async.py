"""Lancement asynchrone des synchronisations Stancer.

`start_sync_payouts(app)` et `start_sync_payments_for_payout(app, payout_id)` délèguent à
`sync_jobs` : un `SyncJob` est créé, la sync tourne dans un fil d'exécution sur la base
de l'instance courante, et la progression du job est mise à jour au fil du traitement.

Le frontend consulte `/payouts/sync/status/<job_id>` (HTMX polling) pour suivre l'avancée.
"""
import requests
from sqlalchemy import or_

from app.extensions import db
from app.models import Payout, SyncJob
from app.models.sync_job import SYNC_KIND_PAYOUTS, SYNC_KIND_PAYOUT_PAYMENTS
from app.services import stancer_sync, sync_jobs


def _error_message(exc):
    if isinstance(exc, requests.HTTPError):
        status = exc.response.status_code if exc.response is not None else "?"
        body = exc.response.text[:200] if exc.response is not None else ""
        return f"Erreur API Stancer : {status} {body}"
    if isinstance(exc, RuntimeError):
        return str(exc)
    return f"Erreur : {exc}"


def start_sync_payouts(app):
    """Démarre (ou retourne) un job de sync globale des payouts.

    Idempotent : si un job de même nature est déjà en cours, on le retourne tel quel.
    """
    def work(job_id):
        return stancer_sync.sync_payouts(progress_cb=sync_jobs.progress_callback(job_id))

    return sync_jobs.start(
        app, SYNC_KIND_PAYOUTS, work, payout_id=None,
        message="Démarrage de la synchronisation…", error_message=_error_message,
    )


def start_sync_payments_for_payout(app, payout_id):
    """Démarre (ou retourne) un job de sync ciblé sur les payments d'un payout."""
    def work(job_id):
        payout = db.session.get(Payout, payout_id)
        if payout is None:
            raise RuntimeError("Payout introuvable")
        imported, updated, total = stancer_sync.sync_payments_for_payout(
            payout, progress_cb=sync_jobs.progress_callback(job_id),
        )
        db.session.commit()
        return {"imported": imported, "updated": updated, "total": total}

    return sync_jobs.start(
        app, SYNC_KIND_PAYOUT_PAYMENTS, work, payout_id=payout_id,
        message="Démarrage de la synchronisation des paiements…", error_message=_error_message,
    )


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
