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


# ------------------------------------------------------------------ activités et surfaces (lot AG11.b)

@bp.route("/ekylibre/activities")
@instance_admin_required
def ekylibre_activities_list():
    _agri_only()
    from app.services import ekylibre_activities
    return jsonify(ekylibre_activities.rows())


@bp.route("/ekylibre/activities", methods=["POST"])
@instance_admin_required
def ekylibre_activities_apply():
    """`{items: [{ekylibre_id, activity_id? | create?, name?}]}` : rattachement ou création, puis surfaces."""
    _agri_only()
    from app.extensions import db
    from app.services import ekylibre_activities
    from app.services.analytic import AnalyticError
    try:
        stats = ekylibre_activities.apply(json_body().get("items"))
    except (ekylibre_activities.EkylibreActivityError, AnalyticError) as exc:
        db.session.rollback()
        if exc.status == 422:
            raise invalid(exc.message, exc.field) from None
        raise ApiError("conflict" if exc.status == 409 else "not_found", exc.message, status=exc.status) from None
    text = (f"{stats['linked']} activité(s) rattachée(s), dont {stats['created']} créée(s) ; "
            f"{stats['measures']} surface(s) reportée(s).")
    notices = [notice(text)]
    if stats["conflicts"]:
        notices.append(notice(f"{stats['conflicts']} surface(s) saisie(s) dans Lyvre différente(s) d'Ekylibre : "
                              "conservée(s), à vérifier.", "warning"))
    return jsonify(stats=stats, notices=notices, **ekylibre_activities.rows())


# ------------------------------------------------------------------ clés depuis les interventions (lot AG11.c)

def _fiscal_year(raw):
    from app.extensions import db
    from app.models import FiscalYear
    from app.services.ledger import open_fiscal_year_for
    from datetime import date
    if raw not in (None, ""):
        fy = db.session.get(FiscalYear, int(raw)) if str(raw).isdigit() else None
        if fy is None:
            raise invalid("Exercice introuvable.", "fiscal_year_id")
        return fy
    fy = open_fiscal_year_for(date.today()) or FiscalYear.query.order_by(FiscalYear.end_date.desc()).first()
    if fy is None:
        raise ApiError("conflict", "Aucun exercice.", status=409)
    return fy


def _key_errors(call):
    from app.extensions import db
    from app.services import ekylibre_keys
    from app.services.analytic import AnalyticError
    try:
        return call()
    except (ekylibre_keys.EkylibreKeyError, AnalyticError) as exc:
        db.session.rollback()
        if exc.status == 422:
            raise invalid(exc.message, exc.field) from None
        raise ApiError("conflict" if exc.status == 409 else "not_found", exc.message, status=exc.status) from None


@bp.route("/ekylibre/keys")
@instance_admin_required
def ekylibre_keys_view():
    _agri_only()
    from flask import request
    from app.models import FiscalYear
    from app.services import ekylibre_keys
    fy = _fiscal_year(request.args.get("fiscal_year_id"))
    data = ekylibre_keys.compute(fy)
    data["fiscal_years"] = [{"value": str(f.id), "label": f.label}
                            for f in FiscalYear.query.order_by(FiscalYear.start_date.desc())]
    return jsonify(data)


@bp.route("/ekylibre/keys", methods=["POST"])
@instance_admin_required
def ekylibre_keys_apply():
    """`{fiscal_year_id}` : crée ou refait les clés « (Ekylibre) » de l'exercice."""
    _agri_only()
    from app.services import ekylibre_keys
    fy = _fiscal_year(json_body().get("fiscal_year_id"))
    data = _key_errors(lambda: ekylibre_keys.apply(fy))
    return jsonify(**data, notices=[notice(f"{len(data['applied'])} clé(s) calculée(s) depuis Ekylibre sur l'exercice {fy.label}.")])


@bp.route("/ekylibre/rules", methods=["POST"])
@instance_admin_required
def ekylibre_rules_apply():
    """`{prefixes: [...]}` : règles « compte → clé Ekylibre » proposées, créées."""
    _agri_only()
    from app.services import ekylibre_keys
    count = _key_errors(lambda: ekylibre_keys.apply_rules(json_body().get("prefixes")))
    return jsonify(rules=ekylibre_keys.proposed_rules(), notices=[notice(
        f"{count} règle(s) créée(s) : les lignes de ces comptes non encore ventilées suivent la clé.")])


# ------------------------------------------------------------------ quantités d'inventaire (lot AG11.d)

def _stock_errors(call):
    from app.extensions import db
    from app.services.stock_inventory import StockError
    try:
        return call()
    except StockError as exc:
        db.session.rollback()
        if exc.status == 422:
            raise invalid(exc.message, exc.field) from None
        raise ApiError("conflict" if exc.status == 409 else "not_found", exc.message, status=exc.status) from None


@bp.route("/ekylibre/inventory")
@instance_admin_required
def ekylibre_inventory_view():
    _agri_only()
    from flask import request
    from app.models import FiscalYear
    from app.services import ekylibre_inventory
    fy = _fiscal_year(request.args.get("fiscal_year_id"))
    data = ekylibre_inventory.rows(fy)
    data["fiscal_years"] = [{"value": str(f.id), "label": f.label}
                            for f in FiscalYear.query.order_by(FiscalYear.start_date.desc())]
    return jsonify(data)


@bp.route("/ekylibre/inventory", methods=["POST"])
@instance_admin_required
def ekylibre_inventory_apply():
    """`{fiscal_year_id, items: [{variant_id, line_id? | create?: {account_code, label?}}]}`."""
    _agri_only()
    from app.services import ekylibre_inventory
    data = json_body()
    fy = _fiscal_year(data.get("fiscal_year_id"))
    stats = _stock_errors(lambda: ekylibre_inventory.apply(fy, data.get("items")))
    notices = [notice(f"{stats['filled']} quantité(s) reportée(s) depuis Ekylibre"
                      + (f", {stats['created']} ligne(s) créée(s)." if stats["created"] else "."))]
    if stats["skipped"]:
        notices.append(notice("Unités incompatibles, non reportées : " + ", ".join(stats["skipped"]) + ".", "warning"))
    return jsonify(stats=stats, notices=notices, **ekylibre_inventory.rows(fy))
