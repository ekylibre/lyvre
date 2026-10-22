"""Reçus fiscaux (lot B) : paramètres de l'instance (B.1). Lecture pour tous les rôles,
modification par l'administrateur de l'instance ; réservé au plan comptable des associations."""
from contextlib import contextmanager

from flask import jsonify, request
from flask_login import current_user

from app.access import instance_admin_required
from app.extensions import db
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
