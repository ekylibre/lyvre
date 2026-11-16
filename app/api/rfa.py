"""Remboursement forfaitaire agricole, 3520 (lot AG2.e) : demande de l'année calculée à la volée, classes de taux
des comptes de vente, type des clients, attestations d'achats (pièce jointe), dépôt, annulation, remboursement.
Réservé aux exploitations agricoles (plan `agri`)."""
import json
from contextlib import contextmanager
from datetime import date

from flask import abort, jsonify, request, send_file
from flask_login import current_user

from app.extensions import db
from app.models import Entity, RfaAttestation, RfaClaim
from app.models.rfa import RFA_CLAIM_STATUSES
from app.services import attachments, rfa
from app.services.attachments import AttachmentError
from app.services.rfa import RfaError

from . import ApiError, bp, get_or_404, invalid, json_body, notice


def _agri():
    from app.tenant import current_chart

    if current_chart() != "agri":
        raise ApiError("not_found", "Remboursement forfaitaire réservé aux exploitations agricoles.", 404)


@contextmanager
def _errors():
    try:
        yield
    except RfaError as exc:
        db.session.rollback()
        raise ApiError("conflict" if exc.status == 409 else "validation_error" if exc.status == 422 else "not_found",
                       exc.message, exc.status, {exc.field: exc.message} if exc.field else None,
                       extra={"problems": exc.problems} if exc.problems else None) from None


def _iso(value):
    return value.isoformat() if value else None


def _date(value, field, label):
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        raise invalid(f"{label} : date attendue (AAAA-MM-JJ).", field) from None


def claim_payload(claim: RfaClaim | None) -> dict | None:
    if claim is None:
        return None
    entry = claim.entry
    return {"id": claim.id, "year": claim.year, "status": claim.status, "status_label": RFA_CLAIM_STATUSES[claim.status],
            "high_base_cents": claim.high_base_cents, "low_base_cents": claim.low_base_cents,
            "amount_cents": claim.amount_cents, "declared_on": _iso(claim.declared_on), "refunded_on": _iso(claim.refunded_on),
            "entry": {"id": entry.id, "reference": entry.reference} if entry is not None else None}


def _payload(data: dict) -> dict:
    return {**data, "deadline": _iso(data["deadline"]), "claim": claim_payload(data["claim"]),
            "rates": [{"value": k, "label": v} for k, v in rfa.RATES.items()],
            "buyers": [{"value": k, "label": v} for k, v in rfa.BUYERS.items()],
            "years_available": rfa.years()}


@bp.route("/rfa/<int:year>")
def rfa_year(year):
    _agri()
    return jsonify(_payload(rfa.compute(year)))


@bp.route("/rfa/accounts/<int:account_id>/rate", methods=["PUT"])
def rfa_account_rate(account_id):
    _agri()
    with _errors():
        rfa.set_account_rate(account_id, json_body().get("rfa_rate"))
        db.session.commit()
    return jsonify(notices=[notice("Classe de taux enregistrée.")])


@bp.route("/rfa/buyers/<int:entity_id>", methods=["PUT"])
def rfa_buyer(entity_id):
    _agri()
    entity = get_or_404(Entity, entity_id, "Tiers introuvable.")
    with _errors():
        rfa.set_buyer(entity, json_body().get("rfa_buyer"))
        db.session.commit()
    return jsonify(notices=[notice(f"Type de client de {entity.name} enregistré.")])


@bp.route("/rfa/<int:year>/attestations/<int:entity_id>", methods=["POST"])
def rfa_attestation_save(year, entity_id):
    """Attestation d'achats : JSON, ou multipart (`payload` JSON et fichier `attachment`)."""
    _agri()
    entity = get_or_404(Entity, entity_id, "Tiers introuvable.")
    token = None
    if request.files or request.form:
        try:
            data = json.loads(request.form.get("payload") or "{}")
        except ValueError:
            raise invalid("Formulaire illisible.") from None
        upload = request.files.get("attachment")
        if upload is not None and upload.filename:
            try:
                token = attachments.stage(upload)
            except AttachmentError as exc:
                raise invalid(str(exc), "attachment") from None
    else:
        data = json_body()
    received = _date(data["received_on"], "received_on", "Reçue le") if data.get("received_on") else None
    with _errors():
        row = rfa.save_attestation(entity, year, data.get("amount_cents"), received, data.get("note"), token)
        db.session.commit()
    return jsonify(item=rfa.attestation_payload(row),
                   notices=[notice(f"Attestation de {entity.name} pour {year} enregistrée.")]), 201


@bp.route("/rfa/attestations/<int:attestation_id>", methods=["DELETE"])
def rfa_attestation_delete(attestation_id):
    _agri()
    row = get_or_404(RfaAttestation, attestation_id, "Attestation introuvable.")
    with _errors():
        rfa.delete_attestation(row)
        db.session.commit()
    return jsonify(notices=[notice("Attestation supprimée.")])


@bp.route("/rfa/attestations/<int:attestation_id>/file")
def rfa_attestation_file(attestation_id):
    _agri()
    row = get_or_404(RfaAttestation, attestation_id, "Attestation introuvable.")
    path = attachments.path_of(row)
    if path is None or not path.is_file():
        abort(404)
    return send_file(path, mimetype=row.attachment_mime, download_name=row.attachment_name or path.name,
                     as_attachment=bool(request.args.get("download")))


@bp.route("/rfa/<int:year>/declare", methods=["POST"])
def rfa_declare(year):
    _agri()
    declared_on = _date(json_body().get("declared_on"), "declared_on", "Déposée le")
    with _errors():
        claim = rfa.declare(year, declared_on, current_user.id)
        db.session.commit()
    entry = f" ; créance passée en 44583 (écriture {claim.entry.reference})" if claim.entry is not None else ""
    return jsonify(item=claim_payload(claim), notices=[notice(
        f"Demande {year} déposée : {claim.amount_cents // 100} € de remboursement forfaitaire{entry}.")]), 201


@bp.route("/rfa/<int:year>/declare", methods=["DELETE"])
def rfa_cancel(year):
    _agri()
    claim = RfaClaim.query.filter_by(year=year).first()
    if claim is None:
        raise ApiError("not_found", "Aucune demande déposée pour cette année.", 404)
    with _errors():
        rfa.cancel(claim)
        db.session.commit()
    return jsonify(notices=[notice(f"Dépôt de la demande {year} annulé.")])


@bp.route("/rfa/<int:year>/refunded", methods=["POST"])
def rfa_refunded(year):
    _agri()
    claim = RfaClaim.query.filter_by(year=year).first()
    if claim is None:
        raise ApiError("not_found", "Aucune demande déposée pour cette année.", 404)
    refunded_on = _date(json_body().get("refunded_on"), "refunded_on", "Remboursée le")
    with _errors():
        rfa.mark_refunded(claim, refunded_on)
        db.session.commit()
    return jsonify(item=claim_payload(claim), notices=[notice(
        f"Remboursement {year} reçu : rapprochez le virement de la DGFiP du compte 44583.")])
