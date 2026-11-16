"""Profil fiscal de la structure (lot AG1.a) : forme juridique codée, régimes datés, options datées.
Lecture pour tous, modification par l'administrateur de l'instance."""
from flask import jsonify

from app.access import instance_admin_required
from app.models import TaxOption, TaxProfile
from app.services import organization, tax_profile
from app.services.tax_profile import TaxProfileError

from . import ApiError, bp, get_or_404, json_body, notice


def _error(exc: TaxProfileError) -> ApiError:
    return ApiError("validation_error", exc.message, status=exc.status,
                    fields={exc.field: exc.message} if exc.field else None)


def _profile(*notices):
    return jsonify(item=tax_profile.payload(), meta=tax_profile.meta(), notices=list(notices))


@bp.route("/tax-profile")
def tax_profile_get():
    return _profile()


@bp.route("/tax-profile", methods=["PUT"])
@instance_admin_required
def tax_profile_update():
    """Forme juridique codée et date de création (champs de `organization`)."""
    data = json_body()
    _org, errors = organization.update({k: data[k] for k in ("legal_form_code", "created_on") if k in data})
    if errors:
        raise ApiError("validation_error", "Champs invalides.", status=422, fields=errors)
    return _profile(notice("Forme juridique enregistrée."))


@bp.route("/tax-profiles", methods=["POST"])
@instance_admin_required
def tax_profiles_create():
    try:
        tax_profile.add_period(json_body())
    except TaxProfileError as exc:
        raise _error(exc) from None
    return _profile(notice("Période de régime ajoutée.")), 201


@bp.route("/tax-profiles/<int:period_id>", methods=["PATCH"])
@instance_admin_required
def tax_profiles_update(period_id):
    period = get_or_404(TaxProfile, period_id, "Période introuvable.")
    try:
        tax_profile.update_period(period, json_body())
    except TaxProfileError as exc:
        raise _error(exc) from None
    return _profile(notice("Période de régime enregistrée."))


@bp.route("/tax-profiles/<int:period_id>", methods=["DELETE"])
@instance_admin_required
def tax_profiles_delete(period_id):
    tax_profile.delete_period(get_or_404(TaxProfile, period_id, "Période introuvable."))
    return _profile(notice("Période supprimée."))


@bp.route("/tax-options", methods=["POST"])
@instance_admin_required
def tax_options_create():
    try:
        tax_profile.add_option(json_body())
    except TaxProfileError as exc:
        raise _error(exc) from None
    return _profile(notice("Option ajoutée.")), 201


@bp.route("/tax-options/<int:option_id>", methods=["PATCH"])
@instance_admin_required
def tax_options_update(option_id):
    option = get_or_404(TaxOption, option_id, "Option introuvable.")
    try:
        tax_profile.update_option(option, json_body())
    except TaxProfileError as exc:
        raise _error(exc) from None
    return _profile(notice("Option enregistrée."))


@bp.route("/tax-options/<int:option_id>", methods=["DELETE"])
@instance_admin_required
def tax_options_delete(option_id):
    tax_profile.delete_option(get_or_404(TaxOption, option_id, "Option introuvable."))
    return _profile(notice("Option supprimée."))
