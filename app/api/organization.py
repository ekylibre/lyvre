"""Identité de la structure (instance courante) : lecture pour tous, modification par
l'administrateur de l'instance."""
from flask import jsonify

from app.access import instance_admin_required
from app.services import organization

from . import ApiError, bp, json_body, notice


def organization_payload(org) -> dict:
    return {**{key: getattr(org, key) for key in organization.FIELDS}, "fec_ready": bool(org.siren)}


@bp.route("/organization")
def organization_get():
    return jsonify(item=organization_payload(organization.get()))


@bp.route("/organization", methods=["PUT"])
@instance_admin_required
def organization_update():
    org, errors = organization.update(json_body())
    if errors:
        raise ApiError("validation_error", "Champs invalides.", status=422, fields=errors)
    return jsonify(item=organization_payload(org), notices=[notice("Identité de la structure enregistrée.")])
