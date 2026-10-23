"""Notifications des utilisateurs, créées à la fin des tâches en arrière-plan (`SyncJob`).

`notify_job(job)` est appelé par `sync_jobs.run` une fois le job terminé (succès ou échec) :
titre et message selon le type de job, niveau (`success`, `warning` s'il y a des erreurs dans le
résultat, `danger` en cas d'échec), lien vers l'écran concerné. Le destinataire est l'utilisateur
qui a lancé le job (`started_by_user_id`) ; sans auteur connu, la notification vaut pour tous les
utilisateurs de l'instance (`user_id` NULL).

Les notifications lues de plus de `RETENTION_DAYS` jours sont purgées à chaque création.
"""
import json
from datetime import datetime, timedelta

from app.extensions import db
from app.models import Notification, SyncJob
from app.models.sync_job import (
    SYNC_KIND_METRICS, SYNC_KIND_PAYOUT_PAYMENTS, SYNC_KIND_PAYOUTS, SYNC_KIND_QONTO, SYNC_KIND_QONTO_INVOICES,
    SYNC_KIND_RECEIPTS_ISSUE, SYNC_KIND_RECEIPTS_SEND, SYNC_STATUS_FAILED,
)

RETENTION_DAYS = 90
KIND_JOB_DONE = "job_done"
KIND_JOB_FAILED = "job_failed"

# Type de job → libellé de la tâche (« Synchronisation Qonto »).
JOB_LABELS = {
    SYNC_KIND_PAYOUTS: "Synchronisation des versements Stancer",
    SYNC_KIND_PAYOUT_PAYMENTS: "Synchronisation des paiements d'un versement Stancer",
    SYNC_KIND_QONTO: "Synchronisation des transactions Qonto",
    SYNC_KIND_QONTO_INVOICES: "Synchronisation des factures d'achat Qonto",
    SYNC_KIND_METRICS: "Synchronisation des indicateurs",
    SYNC_KIND_RECEIPTS_ISSUE: "Émission des reçus fiscaux",
    SYNC_KIND_RECEIPTS_SEND: "Expédition des reçus fiscaux par email",
}


def _url(job: SyncJob) -> str | None:
    """Écran de la SPA où voir le résultat."""
    if job.kind == SYNC_KIND_QONTO:
        return f"/bank-accounts/{job.bank_account_id}/transactions" if job.bank_account_id else "/bank-accounts/"
    if job.kind == SYNC_KIND_PAYOUT_PAYMENTS and job.payout_id:
        return f"/payouts/{job.payout_id}"
    return {SYNC_KIND_PAYOUTS: "/payouts/", SYNC_KIND_QONTO_INVOICES: "/purchases/",
            SYNC_KIND_METRICS: "/impact/", SYNC_KIND_RECEIPTS_ISSUE: "/receipts/?tab=issued",
            SYNC_KIND_RECEIPTS_SEND: "/receipts/?tab=issued"}.get(job.kind)


def _result(job: SyncJob) -> dict:
    try:
        value = json.loads(job.result_json) if job.result_json else {}
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def summary(kind: str, result: dict) -> str:
    """Résumé du résultat d'un job terminé (« 3 nouvelle(s), 1 mise(s) à jour… »)."""
    n = lambda key: int(result.get(key) or 0)  # noqa: E731
    if kind == SYNC_KIND_QONTO:
        parts = [f"{n('created')} transaction(s) importée(s), {n('updated')} mise(s) à jour"]
        if n("rules_posted"):
            parts.append(f"{n('rules_posted')} écriture(s) de règle")
        if n("settled"):
            parts.append(f"{n('settled')} facture(s) réglée(s)")
        if n("proposed_counterparties"):
            parts.append(f"{n('proposed_counterparties')} contrepartie(s) à valider")
        return ", ".join(parts) + "."
    if kind == SYNC_KIND_QONTO_INVOICES:
        parts = [f"{n('created')} nouvelle(s), {n('updated')} mise(s) à jour sur {n('read')} lue(s)"]
        if n("posted"):
            parts.append(f"{n('posted')} comptabilisée(s)")
        if n("without_supplier"):
            parts.append(f"{n('without_supplier')} sans fournisseur")
        if n("to_review"):
            parts.append(f"{n('to_review')} à revoir")
        return ", ".join(parts) + "."
    if kind in (SYNC_KIND_PAYOUTS, SYNC_KIND_PAYOUT_PAYMENTS):
        text = f"{n('imported')} importé(s), {n('updated')} mis à jour sur {n('total')}."
        if "payments_total" in result:
            text += (f" Paiements : {n('payments_imported')} importé(s), {n('payments_updated')} mis à jour"
                     f" sur {n('payments_total')}.")
        return text
    if kind == SYNC_KIND_RECEIPTS_ISSUE:
        return f"{n('issued')} reçu(s) émis, {n('refused')} donateur(s) à compléter."
    if kind == SYNC_KIND_RECEIPTS_SEND:
        return f"{n('sent')} reçu(s) envoyé(s), {n('skipped')} sans adresse email."
    return "Terminée."


def _errors(result: dict) -> list[str]:
    errors = result.get("errors")
    return [str(e) for e in errors] if isinstance(errors, list) else []


def notify_job(job: SyncJob) -> Notification | None:
    """Crée la notification de fin d'un job terminé (aucune si le job tourne encore)."""
    if not job.is_terminal:
        return None
    label = JOB_LABELS.get(job.kind, "Tâche en arrière-plan")
    if job.status == SYNC_STATUS_FAILED:
        kind, level, title = KIND_JOB_FAILED, "danger", f"{label} : échec"
        message = job.message or "La tâche a échoué."
    else:
        result = _result(job)
        errors = _errors(result)
        kind, level = KIND_JOB_DONE, "warning" if errors else "success"
        title = f"{label} terminée" + (" avec des erreurs" if errors else "")
        message = summary(job.kind, result)
        if errors:
            message += f" {len(errors)} erreur(s), dont : {errors[0]}"
    note = Notification(user_id=job.started_by_user_id, kind=kind, level=level, title=title[:200],
                        message=message, url=_url(job), job_id=job.id)
    db.session.add(note)
    purge()
    db.session.commit()
    return note


def purge(now: datetime | None = None) -> None:
    """Supprime les notifications lues depuis plus de RETENTION_DAYS jours (sans commit)."""
    limit = (now or datetime.utcnow()) - timedelta(days=RETENTION_DAYS)
    Notification.query.filter(Notification.read_at.isnot(None), Notification.read_at < limit).delete(
        synchronize_session=False)


def visible_to(user_id: int):
    """Requête des notifications d'un utilisateur : les siennes et celles de toute l'instance."""
    return Notification.query.filter(db.or_(Notification.user_id == user_id, Notification.user_id.is_(None)))


def unread_count(user_id: int) -> int:
    return visible_to(user_id).filter(Notification.read_at.is_(None)).count()


def mark_read(user_id: int, ids=None) -> int:
    """Marque comme lues les notifications visibles (toutes si `ids` est None) ; renvoie le nombre."""
    query = visible_to(user_id).filter(Notification.read_at.is_(None))
    if ids is not None:
        query = query.filter(Notification.id.in_(list(ids)))
    count = query.update({Notification.read_at: datetime.utcnow()}, synchronize_session=False)
    db.session.commit()
    return count
