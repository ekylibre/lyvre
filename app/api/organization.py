"""Identité de la structure (instance courante) : lecture pour tous, modification par
l'administrateur de l'instance."""
from flask import g, jsonify

from app.access import instance_admin_required
from app.extensions import db
from app.services import associates, organization
from app.services.catalog import format_rate

from . import ApiError, bp, json_body, notice


def organization_payload(org) -> dict:
    return {**{key: getattr(org, key) for key in organization.FIELDS}, "fec_ready": bool(org.siren),
            "has_associates": associates.enabled(),
            "associate_interest_rate": format_rate(org.associate_interest_rate_bp).replace(" %", "")}


@bp.route("/organization")
def organization_get():
    return jsonify(item=organization_payload(organization.get()))


@bp.route("/organization", methods=["PUT"])
@instance_admin_required
def organization_update():
    data = json_body()
    instance = g.current_instance
    was_enabled = bool(instance.has_associates)
    org, errors = organization.update(data)
    if errors:
        raise ApiError("validation_error", "Champs invalides.", status=422, fields=errors)
    if "has_associates" in data:
        instance.has_associates = bool(data["has_associates"])  # base méta, même session
        db.session.commit()
    notices = [notice("Identité de la structure enregistrée.")]
    if was_enabled and not instance.has_associates:
        # Désactivation avec des comptes courants non soldés : avertissement, sans refus (F1.3).
        open_accounts = [a for a in associates.listing()["items"] if a["balance_cents"]]
        if open_accounts:
            names = ", ".join(a["name"] for a in open_accounts)
            notices.append(notice(f"Module Associés désactivé alors que des comptes courants ne sont pas soldés : "
                                  f"{names}. Les données sont conservées.", "warning"))
    return jsonify(item=organization_payload(org), notices=notices)
