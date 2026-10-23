"""Reçus fiscaux (lot B) : paramètres de l'instance (B.1, modification par l'administrateur de
l'instance), dons à reprendre, émission, dons en nature (B.2). Réservé au plan des associations."""
from contextlib import contextmanager
from datetime import date

from flask import jsonify, request
from flask_login import current_user

from app.access import instance_admin_required
from app.extensions import db
from app.models import DonationReceipt, Entity, InKindDonation
from app.services import receipts
from app.tenant import current_chart

from . import ApiError, bp, json_body, notice


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
    """`{year, entity_ids?, mode?}` : un reçu par donateur (annuel) ou par don (`single`)."""
    _asso_only()
    data = json_body()
    with _errors():
        year = data.get("year")
        if not isinstance(year, int):
            raise receipts.ReceiptError("Année obligatoire.", "year")
        issued, refused = receipts.issue(year, data.get("entity_ids"), data.get("mode"), current_user.id)
    messages = [notice(f"{len(issued)} reçu(s) émis.")] if issued else []
    messages += [notice(f"{r['name']} : {r['reason']}", "warning") for r in refused]
    return jsonify(items=[receipts.receipt_payload(r) for r in issued], refused=refused,
                   notices=messages or [notice("Aucun reçu à émettre.", "info")])


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
