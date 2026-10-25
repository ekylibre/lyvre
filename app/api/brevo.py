"""Brevo : listes de contacts et attributs du compte (fiche de l'intégration, lot B1), aperçu et
synchronisation des adhérents (lot B3). Réservé aux associations (`app/association_only.py`) ; la clé reste sur le serveur."""
import json

from flask import current_app, jsonify

from app.access import instance_admin_required
from app.extensions import db
from app.models import SyncJob
from app.models.brevo_link import BREVO_CONFLICT, BREVO_LINKED, BrevoLink
from app.models.sync_job import SYNC_KIND_BREVO
from app.services import brevo_attributes, brevo_client, brevo_sync, external_config, sync_jobs

from . import ApiError, bp, get_or_404, json_body, notice, require_integration
from .session import job_payload

_STATUS = {"not_configured": 409, "invalid_key": 409, "ip_not_allowed": 409, "not_found": 404, "busy": 429}


def _client() -> brevo_client.Client:
    try:
        return brevo_client.Client.from_config()
    except brevo_client.BrevoError as exc:
        _raise(exc)


def _raise(exc: brevo_client.BrevoError):
    raise ApiError(f"brevo_{exc.code}", exc.message, _STATUS.get(exc.code, 502)) from None


@bp.route("/brevo/lists")
def brevo_lists():
    """Listes du compte (choix de la liste des adhérents)."""
    try:
        lists = _client().lists()
    except brevo_client.BrevoError as exc:
        _raise(exc)
    selected = external_config.get("brevo", "list_id")
    return jsonify(items=[{"value": str(l["id"]), "label": l.get("name") or f"Liste {l['id']}",
                           "contacts": l.get("uniqueSubscribers") or 0} for l in lists],
                   selected=selected)


@bp.route("/brevo/attributes")
def brevo_attributes_get():
    try:
        attributes = _client().attributes()
    except brevo_client.BrevoError as exc:
        _raise(exc)
    return jsonify(items=brevo_attributes.status(attributes))


@bp.route("/brevo/attributes", methods=["POST"])
@instance_admin_required
def brevo_attributes_create():
    """Crée dans Brevo les attributs attendus qui manquent (action explicite)."""
    client = _client()
    try:
        created = brevo_attributes.create_missing(client)
        items = brevo_attributes.status(client.attributes())
    except brevo_client.BrevoError as exc:
        _raise(exc)
    message = (f"Attribut(s) créé(s) dans Brevo : {', '.join(created)}." if created
               else "Tous les attributs existent déjà dans Brevo.")
    return jsonify(items=items, notices=[notice(message)])


# ------------------------------------------------------------------ synchronisation des adhérents (lot B3)


def _brevo_job(job_id: int) -> SyncJob:
    job = get_or_404(SyncJob, job_id, "Synchronisation introuvable.")
    if job.kind != SYNC_KIND_BREVO:
        raise ApiError("not_found", "Synchronisation introuvable.", 404)
    return job


@bp.route("/brevo/status")
def brevo_status():
    """Dernier passage, liens, conflits en cours ; la première synchronisation doit être un aperçu."""
    last = SyncJob.query.filter_by(kind=SYNC_KIND_BREVO).order_by(SyncJob.id.desc()).first()
    counts = dict(db.session.query(BrevoLink.state, db.func.count()).group_by(BrevoLink.state).all())
    return jsonify(enabled=external_config.is_enabled("brevo"), configured=external_config.is_configured("brevo"),
                   first_sync_pending=brevo_sync.first_sync_pending(),
                   links=counts.get(BREVO_LINKED, 0), conflicts=counts.get(BREVO_CONFLICT, 0),
                   last_job=job_payload(last) if last else None)


@bp.route("/brevo/sync", methods=["POST"])
def brevo_sync_start():
    """`{dry_run, entity_ids?}` : aperçu ou synchronisation, en arrière-plan."""
    require_integration("brevo")
    data = json_body()
    dry_run = bool(data.get("dry_run"))
    ids = data.get("entity_ids") or None
    if ids is not None and not (isinstance(ids, list) and all(isinstance(i, int) for i in ids)):
        raise ApiError("validation_error", "Liste d'adhérents invalide.", 422)
    if not dry_run and brevo_sync.first_sync_pending():
        raise ApiError("validation_error", "Première synchronisation : lancez d'abord l'aperçu, puis validez-le.", 422)
    if sync_jobs.running_job(SYNC_KIND_BREVO):
        raise ApiError("conflict", "Une synchronisation Brevo est déjà en cours.", 409)
    job = brevo_sync.start(current_app._get_current_object(), dry_run=dry_run, entity_ids=ids)
    return jsonify(job=job_payload(job)), 202


@bp.route("/brevo/sync/<int:job_id>")
def brevo_sync_get(job_id):
    job = _brevo_job(job_id)
    result = json.loads(job.result_json) if job.result_json else None
    return jsonify(job=job_payload(job), result=result, first_sync_pending=brevo_sync.first_sync_pending())
