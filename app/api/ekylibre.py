"""Connecteur Ekylibre (lot AG11.a, claudedocs/design_connecteur_ekylibre.md) : connexion par mot de passe à usage
unique (jeton conservé, mot de passe jamais), révocation, synchronisation de l'instantané local, état. Instance
agricole, administrateur de l'instance."""
from flask import current_app, jsonify

from app.access import instance_admin_required
from app.services import ekylibre_sync, external_config, integrations, sync_jobs
from app.services.ekylibre_client import EkylibreError

from . import ApiError, bp, invalid, json_body, notice, require_integration


def _agri_only():
    if not external_config.applies("ekylibre"):
        raise ApiError("not_found", "Ekylibre : instance agricole seulement.", status=404)


def _state() -> dict:
    from .session import job_payload
    job = ekylibre_sync.latest_job()
    return {"enabled": external_config.is_enabled("ekylibre"), "configured": external_config.is_configured("ekylibre"),
            "url": external_config.get("ekylibre", "url") or "", "email": external_config.get("ekylibre", "email") or "",
            "snapshots": ekylibre_sync.status(), "job": job_payload(job) if job else None}


@bp.route("/ekylibre")
@instance_admin_required
def ekylibre_state():
    _agri_only()
    return jsonify(_state())


@bp.route("/ekylibre/connect", methods=["POST"])
@instance_admin_required
def ekylibre_connect():
    """`{url, email, password}` : jeton obtenu auprès d'Ekylibre ; le mot de passe n'est ni conservé ni journalisé."""
    _agri_only()
    data = json_body()
    url, email, password = (str(data.get(k) or "") for k in ("url", "email", "password"))
    if not url.strip():
        raise invalid("Adresse de l'instance Ekylibre obligatoire.", "url")
    if not email.strip() or not password:
        raise invalid("Email et mot de passe Ekylibre obligatoires.", "password")
    try:
        ekylibre_sync.connect(url, email, password)
    except EkylibreError as exc:
        raise ApiError("ekylibre_error", exc.message, status=422 if exc.status in (None, 401, 403) else 502) from None
    notices = [notice("Jeton Ekylibre enregistré (mot de passe non conservé).")]
    if external_config.is_enabled("ekylibre"):
        result = integrations.run_check("ekylibre")
        notices.append(notice(result.message, "success" if result.ok else "danger"))
    return jsonify(**_state(), notices=notices)


@bp.route("/ekylibre/revoke", methods=["POST"])
@instance_admin_required
def ekylibre_revoke():
    _agri_only()
    try:
        ekylibre_sync.revoke()
    except EkylibreError as exc:
        return jsonify(**_state(), notices=[notice(exc.message, "warning")])
    return jsonify(**_state(), notices=[notice("Jeton Ekylibre révoqué et effacé de Lyvre.")])


@bp.route("/ekylibre/sync", methods=["POST"])
@instance_admin_required
def ekylibre_sync_start():
    _agri_only()
    require_integration("ekylibre")
    from app.models.sync_job import SYNC_KIND_EKYLIBRE
    from .session import job_payload
    if sync_jobs.running_job(SYNC_KIND_EKYLIBRE):
        raise ApiError("conflict", "Une lecture d'Ekylibre est déjà en cours.", 409)
    job = ekylibre_sync.start_sync(current_app._get_current_object())
    return jsonify(job=job_payload(job)), 202
