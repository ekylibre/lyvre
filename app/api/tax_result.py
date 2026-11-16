"""Résultat fiscal BA et tableau de passage (lot AG6.a, claudedocs/design_fiscalite_ba.md § 3). Plan agricole en partie
double ; l'expert-comptable lit et exporte."""
from contextlib import contextmanager

from flask import jsonify

from app.extensions import db
from app.models import FiscalYear
from app.services import tax_result
from app.services.tax_result import TaxResultError

from . import ApiError, bp, get_or_404, json_body, notice


def _fy(fy_id):
    if not tax_result.enabled():
        raise ApiError("not_found", "Résultat fiscal réservé aux exploitations au réel (partie double).", 404)
    return get_or_404(FiscalYear, fy_id, "Exercice introuvable.")


@contextmanager
def _errors():
    try:
        yield
    except TaxResultError as exc:
        db.session.rollback()
        code = {409: "conflict", 404: "not_found"}.get(exc.status, "validation_error")
        raise ApiError(code, exc.message, exc.status, {exc.field: exc.message} if exc.field else None) from None


@bp.route("/fiscal-years/<int:fy_id>/tax-result")
def tax_result_view(fy_id):
    return jsonify(item=tax_result.view(_fy(fy_id)), meta=tax_result.meta())


@bp.route("/fiscal-years/<int:fy_id>/tax-result/lines", methods=["POST"])
def tax_result_line_add(fy_id):
    fy = _fy(fy_id)
    with _errors():
        tax_result.add_line(fy, json_body())
        db.session.commit()
    return jsonify(item=tax_result.view(fy), meta=tax_result.meta(), notices=[notice("Ligne ajoutée.")]), 201


@bp.route("/fiscal-years/<int:fy_id>/tax-result/lines/<int:line_id>", methods=["DELETE"])
def tax_result_line_delete(fy_id, line_id):
    fy = _fy(fy_id)
    with _errors():
        tax_result.delete_line(fy, line_id)
        db.session.commit()
    return jsonify(item=tax_result.view(fy), meta=tax_result.meta(), notices=[notice("Ligne supprimée.")])


# ------------------------------------------------------------------ DEP (lot AG6.c)

def _dep_view(fy):
    from app.models.tax_result import DEP_HAZARDS, DEP_KINDS, DEP_MOVEMENTS
    from app.services import dep

    data = tax_result.view(fy)
    base, basis = dep.base_for(data)
    from app.models import DepEntry
    entry = DepEntry.query.filter_by(fiscal_year_id=fy.id).first()
    return {"base_cents": base, "base_basis": basis, "base_notes": dep.base_notes(fy),
            "ceiling": dep.ceiling(base, fy), "deduction_cents": entry.amount_cents if entry else 0,
            "register": dep.register(fy), "savings": dep.savings(fy), "hazard": dep.economic_hazard(fy),
            "kinds": [{"value": k, "label": v} for k, v in DEP_KINDS.items()],
            "movements": [{"value": k, "label": v} for k, v in DEP_MOVEMENTS.items()],
            "hazards": [{"value": k, "label": v} for k, v in DEP_HAZARDS.items()]}


@bp.route("/fiscal-years/<int:fy_id>/dep")
def dep_view(fy_id):
    return jsonify(item=_dep_view(_fy(fy_id)))


@bp.route("/fiscal-years/<int:fy_id>/dep", methods=["PUT"])
def dep_set(fy_id):
    from app.services import dep

    fy = _fy(fy_id)
    with _errors():
        base = _dep_view(fy)["base_cents"]
        dep.set_deduction(fy, json_body().get("amount_cents"), base)
        db.session.commit()
    return jsonify(item=_dep_view(fy), notices=[notice("DEP de l'exercice enregistrée.")])


@bp.route("/fiscal-years/<int:fy_id>/dep/movements", methods=["POST"])
def dep_movement_add(fy_id):
    from app.services import dep

    fy = _fy(fy_id)
    with _errors():
        dep.add_movement(fy, json_body())
        db.session.commit()
    return jsonify(item=_dep_view(fy), notices=[notice("Mouvement de DEP enregistré.")]), 201


@bp.route("/fiscal-years/<int:fy_id>/dep/movements/<int:movement_id>", methods=["DELETE"])
def dep_movement_delete(fy_id, movement_id):
    from app.services import dep

    fy = _fy(fy_id)
    with _errors():
        dep.delete_movement(fy, movement_id)
        db.session.commit()
    return jsonify(item=_dep_view(fy), notices=[notice("Mouvement supprimé.")])


@bp.route("/fiscal-years/<int:fy_id>/dep/substitutes", methods=["POST"])
def dep_substitute_add(fy_id):
    from app.services import dep

    fy = _fy(fy_id)
    with _errors():
        dep.add_substitute(fy, json_body())
        db.session.commit()
    return jsonify(item=_dep_view(fy), notices=[notice("Substitut d'épargne enregistré.")]), 201


@bp.route("/fiscal-years/<int:fy_id>/dep/substitutes/<int:substitute_id>", methods=["DELETE"])
def dep_substitute_delete(fy_id, substitute_id):
    from app.services import dep

    fy = _fy(fy_id)
    with _errors():
        dep.delete_substitute(fy, substitute_id)
        db.session.commit()
    return jsonify(item=_dep_view(fy), notices=[notice("Substitut supprimé.")])


@bp.route("/dep/history", methods=["POST"])
def dep_history_add():
    """Reprise d'une DEP, DPI ou DPA non encore rapportée d'un exercice antérieur à Lyvre."""
    from app.services import dep

    if not tax_result.enabled():
        raise ApiError("not_found", "Réservé aux exploitations au réel (partie double).", 404)
    with _errors():
        dep.add_history(json_body())
        db.session.commit()
    return jsonify(notices=[notice("Déduction antérieure reprise.")]), 201


@bp.route("/bank-accounts/<int:ba_id>/dep-savings", methods=["PUT"])
def bank_account_dep_savings(ba_id):
    """Compte bancaire repéré comme épargne DEP (compte courant dédié, art. 73)."""
    from app.models import BankAccount

    if not tax_result.enabled():
        raise ApiError("not_found", "Réservé aux exploitations au réel (partie double).", 404)
    ba = get_or_404(BankAccount, ba_id, "Compte bancaire introuvable.")
    value = json_body().get("dep_savings")
    if not isinstance(value, bool):
        raise ApiError("validation_error", "dep_savings : vrai ou faux attendu.", 422)
    ba.dep_savings = value
    db.session.commit()
    return jsonify(notices=[notice("Compte d'épargne DEP " + ("repéré." if value else "retiré."))])


# ------------------------------------------------------------------ provision 73 A (lot AG6.d)

@bp.route("/fiscal-years/<int:fy_id>/cow-provision")
def cow_provision_view(fy_id):
    from app.services import cow_provision
    return jsonify(item=cow_provision.view(_fy(fy_id)))


@bp.route("/fiscal-years/<int:fy_id>/cow-provision", methods=["POST"])
def cow_provision_post(fy_id):
    """`{constitute: bool}` : dotation de l'exercice (option) et reprises calculées, écriture gérée."""
    from app.services import cow_provision
    fy = _fy(fy_id)
    constitute = json_body().get("constitute", False)
    if not isinstance(constitute, bool):
        raise ApiError("validation_error", "constitute : vrai ou faux attendu.", 422)
    with _errors():
        entry = cow_provision.post(fy, constitute)
        db.session.commit()
    message = f"Provision 73 A passée ({entry.reference})." if entry else "Rien à passer."
    return jsonify(item=cow_provision.view(fy), notices=[notice(message)])


@bp.route("/fiscal-years/<int:fy_id>/cow-provision", methods=["DELETE"])
def cow_provision_cancel(fy_id):
    from app.services import cow_provision
    fy = _fy(fy_id)
    with _errors():
        cow_provision.cancel(fy)
        db.session.commit()
    return jsonify(item=cow_provision.view(fy), notices=[notice("Provision 73 A de l'exercice annulée.")])


@bp.route("/fiscal-years/<int:fy_id>/cow-provision/waivers", methods=["POST"])
def cow_provision_waive(fy_id):
    from app.services import cow_provision
    fy = _fy(fy_id)
    data = json_body()
    with _errors():
        cow_provision.waive(fy, data.get("provision_id"), data.get("reason"))
        db.session.commit()
    return jsonify(item=cow_provision.view(fy), notices=[notice("Sortie sans reprise enregistrée.")]), 201


@bp.route("/fiscal-years/<int:fy_id>/egalim", methods=["PUT"])
def fiscal_year_egalim(fy_id):
    """Contrat pluriannuel (EGALIM) en cours à la clôture : pas de minoration de la provision 73 A."""
    fy = _fy(fy_id)
    value = json_body().get("egalim_contract")
    if value is not None and not isinstance(value, bool):
        raise ApiError("validation_error", "egalim_contract : vrai, faux ou nul attendu.", 422)
    if fy.status == "closed":
        raise ApiError("conflict", "Exercice clôturé.", 409)
    fy.egalim_contract = value
    db.session.commit()
    return jsonify(notices=[notice("Contrat pluriannuel enregistré.")])


# ------------------------------------------------------------------ régimes BA et étalement 75-0 A (lot AG6.e)

def _agri_fy(fy_id):
    from app.tenant import is_agri
    if not is_agri():
        raise ApiError("not_found", "Réservé aux exploitations agricoles.", 404)
    return get_or_404(FiscalYear, fy_id, "Exercice introuvable.")


@bp.route("/fiscal-years/<int:fy_id>/ba-regime")
def ba_regime_view(fy_id):
    """Moyennes et régime de plein droit, simulation micro ou réel, revenus accessoires, années antérieures saisies."""
    from app.services import ba_regimes
    return jsonify(item=ba_regimes.view(_agri_fy(fy_id)))


@bp.route("/ba-history/<int:year>", methods=["PUT"])
def ba_history_save(year):
    from app.services import ba_regimes
    from app.tenant import is_agri
    if not is_agri():
        raise ApiError("not_found", "Réservé aux exploitations agricoles.", 404)
    with _errors():
        ba_regimes.save_history(year, json_body())
        db.session.commit()
    return jsonify(items=ba_regimes.history_rows(), notices=[notice(f"Année {year} enregistrée.")])


@bp.route("/accounts/<int:account_id>/ba-income-class", methods=["PUT"])
def account_ba_income_class(account_id):
    from app.models import Account
    from app.services import ba_regimes
    from app.tenant import is_agri
    if not is_agri():
        raise ApiError("not_found", "Réservé aux exploitations agricoles.", 404)
    account = get_or_404(Account, account_id, "Compte introuvable.")
    with _errors():
        ba_regimes.set_income_class(account, json_body().get("ba_income_class"))
        db.session.commit()
    return jsonify(item={"id": account.id, "code": account.code, "class": account.ba_income_class},
                   notices=[notice(f"Compte {account.code} repéré.")])


@bp.route("/fiscal-years/<int:fy_id>/income-spreads")
def income_spreads_view(fy_id):
    from app.services import ba_regimes
    return jsonify(item=ba_regimes.spreads_view(_fy(fy_id)))


@bp.route("/fiscal-years/<int:fy_id>/income-spreads", methods=["POST"])
def income_spreads_add(fy_id):
    from app.services import ba_regimes
    fy = _fy(fy_id)
    with _errors():
        ba_regimes.add_spread(fy, json_body())
        db.session.commit()
    return jsonify(item=ba_regimes.spreads_view(fy), notices=[notice("Étalement 75-0 A enregistré.")]), 201


@bp.route("/fiscal-years/<int:fy_id>/income-spreads/<int:spread_id>", methods=["DELETE"])
def income_spreads_delete(fy_id, spread_id):
    from app.services import ba_regimes
    fy = _fy(fy_id)
    with _errors():
        ba_regimes.delete_spread(fy, spread_id)
        db.session.commit()
    return jsonify(item=ba_regimes.spreads_view(fy), notices=[notice("Étalement supprimé.")])


# ------------------------------------------------------------------ aide à la liasse 2139 / 2143 (lot AG6.f)

@bp.route("/fiscal-years/<int:fy_id>/liasse")
def liasse_view(fy_id):
    from app.services import liasse
    fy = _fy(fy_id)
    try:
        return jsonify(item=liasse.compute(fy))
    except liasse.LiasseError as exc:
        raise ApiError("not_found" if exc.status == 404 else "validation_error", exc.message, exc.status) from None


# ------------------------------------------------------------------ plus-values et crédits d'impôt (lot AG6.g)

@bp.route("/fiscal-years/<int:fy_id>/capital-gains")
def capital_gains_view(fy_id):
    from app.services import capital_gains
    return jsonify(item=capital_gains.view(_fy(fy_id)))


@bp.route("/fiscal-years/<int:fy_id>/capital-gains", methods=["PUT"])
def capital_gains_choice(fy_id):
    """`{apply_151_septies, activity_since, young_farmer_buyer}` : choix de l'exercice."""
    from app.services import capital_gains
    fy = _fy(fy_id)
    with _errors():
        capital_gains.save_choice(fy, json_body())
        db.session.commit()
    return jsonify(item=capital_gains.view(fy), notices=[notice("Choix des plus-values enregistré.")])


@bp.route("/fiscal-years/<int:fy_id>/tax-credits")
def tax_credits_view(fy_id):
    from app.services import capital_gains
    return jsonify(item=capital_gains.credits(_fy(fy_id)))


@bp.route("/fiscal-years/<int:fy_id>/tax-credits/<kind>", methods=["PUT"])
def tax_credits_save(fy_id, kind):
    from app.services import capital_gains
    fy = _fy(fy_id)
    with _errors():
        capital_gains.save_credit(fy, kind, json_body())
        db.session.commit()
    return jsonify(item=capital_gains.credits(fy), notices=[notice("Crédit d'impôt enregistré.")])


@bp.route("/fiscal-years/<int:fy_id>/tax-credits/<kind>", methods=["DELETE"])
def tax_credits_delete(fy_id, kind):
    from app.services import capital_gains
    fy = _fy(fy_id)
    with _errors():
        capital_gains.delete_credit(fy, kind)
        db.session.commit()
    return jsonify(item=capital_gains.credits(fy), notices=[notice("Crédit d'impôt retiré.")])
