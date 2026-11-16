"""Paramètres réglementaires datés (lot AG1.a, claudedocs/design_compta_agricole.md § 4.4) : lecture pour
tout utilisateur connecté ; surcharges réservées à l'administrateur de la plateforme (communes à toutes
les instances)."""
from datetime import date

from flask import jsonify, request
from flask_login import current_user

from app.decorators import admin_required
from app.services import reg_params
from app.services.reg_params import ParamError

from . import ApiError, bp, json_body, notice


def _error(exc: ParamError) -> ApiError:
    return ApiError("validation_error", exc.message, status=422,
                    fields={exc.field: exc.message} if exc.field else None)


@bp.route("/regulatory-values")
def regulatory_values_list():
    text = request.args.get("on") or ""
    try:
        on = date.fromisoformat(text) if text else None
    except ValueError:
        raise ApiError("validation_error", "Date attendue (AAAA-MM-JJ).", status=422, fields={"on": "Date invalide."}) from None
    items = reg_params.listing(request.args.get("prefix") or "", on)
    return jsonify(items=items, meta={"reliabilities": [{"value": k, "label": v}
                                                         for k, v in reg_params.RELIABILITIES.items()],
                                      "on": (on or date.today()).isoformat()})


@bp.route("/regulatory-values/<path:key>", methods=["POST"])
@admin_required
def regulatory_values_override(key):
    try:
        row = reg_params.add_override(key, json_body(), user_id=current_user.id)
    except ParamError as exc:
        raise _error(exc) from None
    return jsonify(item={"id": row.id, "key": row.key},
                   notices=[notice("Valeur enregistrée : elle s'applique à toutes les instances.")]), 201


@bp.route("/regulatory-values/overrides/<int:override_id>", methods=["DELETE"])
@admin_required
def regulatory_values_delete(override_id):
    try:
        reg_params.delete_override(override_id)
    except ParamError as exc:
        raise ApiError("not_found", exc.message, status=404) from None
    return jsonify(notices=[notice("Surcharge supprimée : la valeur de référence s'applique de nouveau.")])
