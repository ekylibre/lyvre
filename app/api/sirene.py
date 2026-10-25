"""Sirene (lot G3) : recherche et proposition de champs pour la Structure et les tiers. Lecture
seule, ouverte à tous les rôles (l'expert-comptable n'en voit pas les boutons) ; la clé de l'INSEE
reste sur le serveur."""
import json
import re
from datetime import datetime

from flask import current_app, jsonify, request

from app.extensions import db
from app.models import Entity, SyncJob
from app.models.sync_job import SYNC_KIND_SIRENE_REFRESH, SYNC_STATUS_DONE
from app.services import sirene, sirene_refresh, sync_jobs
from app.services.organization import luhn_valid
from app.tenant import is_association

from . import ApiError, bp, get_or_404, json_body, notice
from .session import job_payload

_ERRORS = {"not_configured": ("sirene_unavailable", 503), "unavailable": ("sirene_unavailable", 503),
           "busy": ("sirene_busy", 429), "not_found": ("not_found", 404), "invalid": ("validation_error", 422)}


def _raise(exc: sirene.SireneError):
    code, status = _ERRORS.get(exc.code, ("sirene_unavailable", 503))
    raise ApiError(code, exc.message, status, extra={"retry_after": exc.retry_after} if exc.retry_after else None) \
        from None


def _number(name: str, size: int) -> str | None:
    value = re.sub(r"[\s.]", "", request.args.get(name) or "")
    if not value:
        return None
    if not re.fullmatch(rf"\d{{{size}}}", value) or not luhn_valid(value[:9]):
        raise ApiError("validation_error", f"{name.upper()} invalide.", 422, fields={name: f"{name.upper()} invalide."})
    return value


@bp.route("/sirene/search")
def sirene_search():
    try:
        items = sirene.search(request.args.get("q") or "", request.args.get("postal_code"))
    except sirene.SireneError as exc:
        _raise(exc)
    return jsonify(items=items)


@bp.route("/sirene/proposal")
def sirene_proposal():
    """`?siren=` (siège) ou `?siret=` ; `for=entity` pour un tiers (nature, activité de l'établissement),
    sinon la Structure (forme juridique, RNA d'une association)."""
    siret, siren = _number("siret", 14), _number("siren", 9)
    if not siret and not siren:
        raise ApiError("validation_error", "SIREN ou SIRET attendu.", 422)
    for_entity = request.args.get("for") == "entity"
    try:
        result = sirene.proposal(siren=siren, siret=siret, for_entity=for_entity, association=is_association())
    except sirene.SireneError as exc:
        _raise(exc)
    found = result.values.get("siren")
    existing = Entity.query.filter_by(siren=found).order_by(Entity.id).first() if found and for_entity else None
    return jsonify(**result.payload(),
                   existing_entity={"id": existing.id, "name": existing.name} if existing else None)


# ------------------------------------------------------------------ mise à jour groupée des tiers (lot G5)


def _refresh_job(job_id: int) -> SyncJob:
    job = get_or_404(SyncJob, job_id, "Comparaison introuvable.")
    if job.kind != SYNC_KIND_SIRENE_REFRESH:
        raise ApiError("not_found", "Comparaison introuvable.", 404)
    return job


@bp.route("/entities/sirene-refresh", methods=["POST"])
def sirene_refresh_start():
    """`{entity_ids?}` : compare à Sirene les tiers choisis (tous ceux qui ont un SIREN sinon), en
    arrière-plan ; rien n'est modifié avant la revue."""
    if not sirene.available():
        raise ApiError("sirene_unavailable", "Sirene n'est pas configuré sur ce serveur.", 503)
    if sync_jobs.running_job(SYNC_KIND_SIRENE_REFRESH):
        raise ApiError("conflict", "Une comparaison avec Sirene est déjà en cours.", 409)
    ids = json_body().get("entity_ids") or None
    if ids is not None and not (isinstance(ids, list) and all(isinstance(i, int) for i in ids)):
        raise ApiError("validation_error", "Liste de tiers invalide.", 422)
    count = len(sirene_refresh.candidates(ids))
    if not count:
        raise ApiError("validation_error", "Aucun tiers avec un SIREN ou un SIRET.", 422)

    def work(job_id):
        return sirene_refresh.run(ids, job_id, sync_jobs.progress_callback(job_id, throttle=1))
    job = sync_jobs.start(current_app._get_current_object(), SYNC_KIND_SIRENE_REFRESH, work,
                          message=f"Comparaison de {count} tiers avec Sirene…")
    return jsonify(job=job_payload(job), count=count), 202


@bp.route("/entities/sirene-refresh/<int:job_id>")
def sirene_refresh_get(job_id):
    job = _refresh_job(job_id)
    result = json.loads(job.result_json) if job.result_json else None
    return jsonify(job=job_payload(job), result=result,
                   applied=bool(result and result.get("applied_at")))


@bp.route("/entities/sirene-refresh/<int:job_id>/apply", methods=["POST"])
def sirene_refresh_apply(job_id):
    """`{changes: {entity_id: [champs]}}` : champs retenus à la revue, appliqués en une transaction."""
    job = _refresh_job(job_id)
    if job.status != SYNC_STATUS_DONE or not job.result_json:
        raise ApiError("conflict", "La comparaison n'est pas terminée.", 409)
    selection = json_body().get("changes")
    if not isinstance(selection, dict):
        raise ApiError("validation_error", "Champs à appliquer attendus.", 422)
    result = json.loads(job.result_json)
    outcome = sirene_refresh.apply(result, selection)
    result["applied_at"] = datetime.utcnow().isoformat(timespec="seconds")  # revue close : retour possible, en lecture
    job.result_json = json.dumps(result, ensure_ascii=False)
    db.session.commit()
    notices = [notice(f"{outcome['applied']} champ(s) mis à jour depuis Sirene.")]
    if outcome["skipped"]:
        notices.append(notice(f"{len(outcome['skipped'])} champ(s) laissé(s) tels quels : voir le détail.", "warning"))
    return jsonify(**outcome, notices=notices)


@bp.route("/entities/sirene-refresh/<int:job_id>/cancel", methods=["POST"])
def sirene_refresh_cancel(job_id):
    job = _refresh_job(job_id)
    if job.is_running:
        sirene_refresh.cancel(job.id)
    return jsonify(notices=[notice("Arrêt demandé : les tiers déjà comparés restent consultables.")])
