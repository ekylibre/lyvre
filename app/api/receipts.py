"""Reçus fiscaux (lot B) : paramètres de l'instance (B.1, modification par l'administrateur de
l'instance), dons à reprendre, émission, dons en nature (B.2). Réservé au plan des associations."""
import json
from contextlib import contextmanager
from datetime import date

from flask import current_app, jsonify, request
from flask_login import current_user

from app.access import instance_admin_required
from app.extensions import db
from app.models import DonationReceipt, Entity, InKindDonation
from app.models.sync_job import SYNC_KIND_RECEIPTS_ISSUE, SYNC_KIND_RECEIPTS_SEND
from app.services import receipts, sync_jobs
from app.tenant import current_chart

from . import ApiError, bp, json_body, notice, require_integration
from .session import job_payload


@contextmanager
def _errors():
    try:
        yield
    except receipts.ReceiptError as exc:
        db.session.rollback()
        code = "validation_error" if exc.status == 422 else "conflict"
        raise ApiError(code, exc.message, exc.status, {exc.field: exc.message} if exc.field else None) from None


def _asso_only():
    if current_chart() != "asso":
        raise ApiError("not_found", "Les reçus fiscaux concernent les associations.", 404)


@bp.route("/receipts/settings")
def receipts_settings_get():
    _asso_only()
    return jsonify(item=receipts.payload())


@bp.route("/receipts/settings", methods=["PUT"])
@instance_admin_required
def receipts_settings_save():
    """`{enabled, eligibility, eligibility_detail, rescrit_ref, cgi_articles, donation_prefixes,
    default_mode, acknowledged}`."""
    _asso_only()
    with _errors():
        settings = receipts.save(json_body(), current_user.id)
    message = "Reçus fiscaux activés." if settings.enabled else "Paramètres des reçus fiscaux enregistrés."
    return jsonify(item=receipts.payload(settings), notices=[notice(message)])


@bp.route("/receipts/settings/signature", methods=["POST"])
@instance_admin_required
def receipts_signature_upload():
    _asso_only()
    with _errors():
        receipts.save_signature(request.files.get("signature"))
    return jsonify(item=receipts.payload(), notices=[notice("Signature enregistrée.")])


@bp.route("/receipts/settings/signature", methods=["DELETE"])
@instance_admin_required
def receipts_signature_delete():
    _asso_only()
    receipts.delete_signature()
    return jsonify(item=receipts.payload(), notices=[notice("Signature retirée ; reçus désactivés.")])


# ------------------------------------------------------------------ B.2 : candidats, émission


def _year():
    try:
        return int(request.args.get("year") or date.today().year)
    except ValueError:
        raise ApiError("validation_error", "Année invalide.", 422) from None


@bp.route("/receipts")
def receipts_list():
    """Reçus émis de l'année `?year=` (défaut : année en cours)."""
    _asso_only()
    year = _year()
    rows = DonationReceipt.query.filter_by(year=year).order_by(DonationReceipt.number).all()
    return jsonify(items=[receipts.receipt_payload(r) for r in rows], meta={"year": year, "enabled": receipts.get().enabled})


@bp.route("/receipts/candidates")
def receipts_candidates():
    """Dons de l'année non encore repris sur un reçu, par donateur ; lignes sans donateur."""
    _asso_only()
    data = receipts.candidates(_year())
    entities = [{"value": str(e.id), "label": e.name} for e in Entity.query.order_by(Entity.name)]
    return jsonify(entities=entities, **data)


@bp.route("/receipts/issue", methods=["POST"])
def receipts_issue():
    """`{year, entity_ids?, mode?}` : émission en arrière-plan (job `donation_receipts`, notification
    de fin) ; contrôles préalables immédiats (activation, mentions, année, mode)."""
    _asso_only()
    data = json_body()
    year = data.get("year")
    with _errors():
        if not isinstance(year, int):
            raise receipts.ReceiptError("Année obligatoire.", "year")
        mode = receipts.check_issue(year, data.get("mode"))
    entity_ids, user_id = data.get("entity_ids"), current_user.id

    def work(job_id):
        issued, refused = receipts.issue(year, entity_ids, mode, user_id, sync_jobs.progress_callback(job_id, throttle=1))
        return {"issued": len(issued), "refused": len(refused), "numbers": [r.number for r in issued],
                "errors": [f"{r['name']} : {r['reason']}" for r in refused]}
    job = sync_jobs.start(current_app._get_current_object(), SYNC_KIND_RECEIPTS_ISSUE, work,
                          message="Émission des reçus…")
    return jsonify(job=job_payload(job)), 202


@bp.route("/receipts/send", methods=["POST"])
def receipts_send():
    """`{ids?, year?}` : envoi par email (PDF joint) des reçus choisis, ou des reçus émis, non encore
    envoyés et dont le donateur a une adresse email, de l'année ; en arrière-plan (job
    `donation_receipts_send`)."""
    _asso_only()
    data = json_body()
    ids = data.get("ids")
    if not ids:
        year = data.get("year")
        if not isinstance(year, int):
            raise ApiError("validation_error", "Reçus ou année à envoyer.", 422)
        ids = [r.id for r in DonationReceipt.query.filter_by(year=year, status="issued", sent_at=None)
               if r.entity.email or json.loads(r.donor_json).get("email")]
    if not ids:
        return jsonify(notices=[notice("Aucun reçu à envoyer.", "info")])
    require_integration("smtp")

    def work(job_id):
        return receipts.send(ids, sync_jobs.progress_callback(job_id, throttle=1))
    job = sync_jobs.start(current_app._get_current_object(), SYNC_KIND_RECEIPTS_SEND, work,
                          message="Envoi des reçus…")
    return jsonify(job=job_payload(job)), 202


@bp.route("/receipts/<int:receipt_id>/cancel", methods=["POST"])
def receipts_cancel(receipt_id):
    """`{reason, reissue}` : annulation tracée (jamais de suppression ni de renumérotation) et
    réémission éventuelle des mêmes dons sous un nouveau numéro."""
    _asso_only()
    data = json_body()
    with _errors():
        receipt, replacement = receipts.cancel(receipt_id, data.get("reason"), bool(data.get("reissue")), current_user.id)
    message = f"Reçu {receipt.number} annulé" + (f", remplacé par le reçu {replacement.number}." if replacement else ".")
    return jsonify(item=receipts.receipt_payload(receipt), notices=[notice(message)])


@bp.route("/receipts/summary")
def receipts_summary():
    """État annuel `?year=` : reçus émis / annulés, par type de donateur et nature, envoi, et
    rapprochement avec les dons comptabilisés."""
    _asso_only()
    year = _year()
    return jsonify(export_url=f"/receipts/summary.xlsx?year={year}", **receipts.annual_summary(year))


@bp.route("/receipts/lines/<int:line_id>/donor", methods=["PUT"])
def receipts_line_donor(line_id):
    """`{entity_id}` (null : retirer) : donateur d'une ligne de don."""
    _asso_only()
    with _errors():
        receipts.assign_donor(line_id, json_body().get("entity_id"))
    return jsonify(notices=[notice("Donateur enregistré.")])


@bp.route("/receipts/in-kind", methods=["POST"])
def receipts_in_kind_create():
    """`{entity_id, date, description, valuation_cents, valuation_method}`."""
    _asso_only()
    with _errors():
        gift = receipts.save_in_kind(json_body())
    return jsonify(notices=[notice(f"Don en nature « {gift.description} » enregistré.")]), 201


@bp.route("/receipts/in-kind/<int:gift_id>", methods=["DELETE"])
def receipts_in_kind_delete(gift_id):
    _asso_only()
    with _errors():
        receipts.delete_in_kind(gift_id)
    return jsonify(notices=[notice("Don en nature supprimé.")])


@bp.route("/receipts/in-kind")
def receipts_in_kind_list():
    """Dons en nature de l'année `?year=`, avec le reçu qui les reprend."""
    _asso_only()
    year = _year()
    done = receipts.issued_in_kind_ids()
    rows = (InKindDonation.query.filter(InKindDonation.date.between(date(year, 1, 1), date(year, 12, 31)))
            .order_by(InKindDonation.date).all())
    return jsonify(items=[{"id": g.id, "entity_id": g.entity_id, "donor": g.entity.name, "date": g.date.isoformat(),
                           "description": g.description, "valuation_cents": g.valuation_cents,
                           "valuation_method": g.valuation_method, "receipted": g.id in done} for g in rows])
