"""Analytique agricole par activité (lot AG8, claudedocs/design_analytique_agricole.md) : ateliers, activités,
campagnes et mesures (AG8.a)."""
from contextlib import contextmanager

from flask import jsonify, request

from app.extensions import db
from app.models import Activity, Workshop
from app.services import analytic
from app.services.analytic import AnalyticError

from . import ApiError, bp, get_or_404, json_body, notice


def _require():
    if not analytic.enabled():
        raise ApiError("not_found", "Analytique par activité réservée aux exploitations agricoles.", 404)


@contextmanager
def _errors():
    try:
        yield
    except AnalyticError as exc:
        db.session.rollback()
        code = {409: "conflict", 404: "not_found"}.get(exc.status, "validation_error")
        raise ApiError(code, exc.message, exc.status, {exc.field: exc.message} if exc.field else None) from None


def _campaign():
    raw = request.args.get("campaign")
    try:
        return int(raw) if raw else None
    except ValueError:
        raise ApiError("validation_error", "Campagne attendue (année).", 422) from None


def _listing(year=None):
    return analytic.listing(year, include_archived=request.args.get("archived") == "1")


@bp.route("/workshops")
def workshops_list():
    _require()
    return jsonify(item=_listing(_campaign()), meta=analytic.meta())


@bp.route("/workshops", methods=["POST"])
def workshop_create():
    _require()
    with _errors():
        workshop = analytic.save_workshop(None, json_body())
        db.session.commit()
    return jsonify(item=analytic.workshop_payload(workshop), notices=[notice("Atelier créé.")]), 201


@bp.route("/workshops/<int:workshop_id>", methods=["PATCH"])
def workshop_update(workshop_id):
    _require()
    workshop = get_or_404(Workshop, workshop_id, "Atelier introuvable.")
    with _errors():
        analytic.save_workshop(workshop, json_body())
        db.session.commit()
    return jsonify(item=analytic.workshop_payload(workshop), notices=[notice("Atelier enregistré.")])


@bp.route("/workshops/<int:workshop_id>", methods=["DELETE"])
def workshop_delete(workshop_id):
    _require()
    workshop = get_or_404(Workshop, workshop_id, "Atelier introuvable.")
    with _errors():
        analytic.delete_workshop(workshop)
        db.session.commit()
    return jsonify(notices=[notice("Atelier supprimé.")])


@bp.route("/activities", methods=["POST"])
def activity_create():
    _require()
    with _errors():
        activity = analytic.save_activity(None, json_body())
        db.session.commit()
    return jsonify(item=analytic.activity_payload(activity), notices=[notice("Activité créée.")]), 201


@bp.route("/activities/<int:activity_id>", methods=["PATCH"])
def activity_update(activity_id):
    _require()
    activity = get_or_404(Activity, activity_id, "Activité introuvable.")
    with _errors():
        analytic.save_activity(activity, json_body())
        db.session.commit()
    return jsonify(item=analytic.activity_payload(activity), notices=[notice("Activité enregistrée.")])


@bp.route("/activities/<int:activity_id>", methods=["DELETE"])
def activity_delete(activity_id):
    _require()
    activity = get_or_404(Activity, activity_id, "Activité introuvable.")
    with _errors():
        analytic.delete_activity(activity)
        db.session.commit()
    return jsonify(notices=[notice("Activité supprimée.")])


@bp.route("/activities/<int:activity_id>/campaigns/<int:year>", methods=["PUT"])
def activity_measure(activity_id, year):
    _require()
    with _errors():
        analytic.set_measure(activity_id, year, json_body())
        db.session.commit()
    return jsonify(item=_listing(year), notices=[notice("Mesure enregistrée.")])


@bp.route("/campaigns/<int:year>/copy-measures", methods=["POST"])
def campaign_copy_measures(year):
    _require()
    with _errors():
        count = analytic.copy_measures(year - 1, year)
        db.session.commit()
    return jsonify(item=_listing(year), notices=[notice(f"{count} mesure(s) reprise(s) de la campagne {year - 1}.")])


@bp.route("/lexicon/productions")
def lexicon_productions():
    _require()
    items = analytic.lexicon_search(request.args.get("q", ""), request.args.get("family") or None, limit=500)
    return jsonify(items=items, meta={"source": analytic.lexicon_source()})


# ------------------------------------------------------------------ clés, règles, ventilation (lot AG8.b)

@bp.route("/analytic-keys")
def analytic_keys_list():
    from app.models import AnalyticKey
    from app.models.analytic import KEY_BASES
    from app.services import analytic_allocation as alloc
    _require()
    keys = AnalyticKey.query.order_by(AnalyticKey.archived, AnalyticKey.name)
    return jsonify(items=[alloc.key_payload(k) for k in keys],
                   meta={"bases": [{"value": k, "label": v} for k, v in KEY_BASES.items()], "targets": alloc.targets_options()})


@bp.route("/analytic-keys", methods=["POST"])
def analytic_key_create():
    from app.services import analytic_allocation as alloc
    _require()
    with _errors():
        key = alloc.save_key(None, json_body())
        db.session.commit()
    return jsonify(item=alloc.key_payload(key), notices=[notice("Clé créée.")]), 201


@bp.route("/analytic-keys/<int:key_id>", methods=["PATCH"])
def analytic_key_update(key_id):
    from app.models import AnalyticKey
    from app.services import analytic_allocation as alloc
    _require()
    key = get_or_404(AnalyticKey, key_id, "Clé introuvable.")
    with _errors():
        alloc.save_key(key, json_body())
        db.session.commit()
    return jsonify(item=alloc.key_payload(key), notices=[notice("Clé enregistrée.")])


@bp.route("/analytic-keys/<int:key_id>", methods=["DELETE"])
def analytic_key_delete(key_id):
    from app.models import AnalyticKey
    _require()
    key = get_or_404(AnalyticKey, key_id, "Clé introuvable.")
    db.session.delete(key)
    db.session.commit()
    return jsonify(notices=[notice("Clé supprimée (ventilations et règles qui l'utilisaient comprises).")])


@bp.route("/analytic-rules")
def analytic_rules_list():
    from app.models import AnalyticRule
    from app.services import analytic_allocation as alloc
    _require()
    return jsonify(items=[alloc.rule_payload(r) for r in AnalyticRule.query.order_by(AnalyticRule.account_prefix)])


@bp.route("/analytic-rules", methods=["POST"])
def analytic_rule_save():
    from app.services import analytic_allocation as alloc
    _require()
    with _errors():
        rule = alloc.save_rule(json_body())
        db.session.commit()
    return jsonify(item=alloc.rule_payload(rule), notices=[notice("Règle enregistrée.")]), 201


@bp.route("/analytic-rules/<int:rule_id>", methods=["DELETE"])
def analytic_rule_delete(rule_id):
    from app.services import analytic_allocation as alloc
    _require()
    with _errors():
        alloc.delete_rule(rule_id)
        db.session.commit()
    return jsonify(notices=[notice("Règle supprimée.")])


def _fy(fy_id):
    from app.models import FiscalYear
    _require()
    return get_or_404(FiscalYear, fy_id, "Exercice introuvable.")


@bp.route("/fiscal-years/<int:fy_id>/analytic/unallocated")
def analytic_unallocated(fy_id):
    from app.services import analytic_allocation as alloc
    fy = _fy(fy_id)
    data = alloc.unallocated(fy, request.args.get("account") or None, request.args.get("all") == "1")
    return jsonify(item=data, meta={"targets": alloc.targets_options()})


@bp.route("/fiscal-years/<int:fy_id>/analytic/allocations", methods=["POST"])
def analytic_allocate(fy_id):
    from app.services import analytic_allocation as alloc
    fy = _fy(fy_id)
    body = json_body()
    with _errors():
        count = alloc.allocate(fy, body.get("line_ids"), body.get("targets"), body.get("campaign_year"))
        db.session.commit()
    return jsonify(notices=[notice(f"{count} ligne(s) ventilée(s).")])


@bp.route("/fiscal-years/<int:fy_id>/analytic/allocations/clear", methods=["POST"])
def analytic_clear(fy_id):
    from app.services import analytic_allocation as alloc
    fy = _fy(fy_id)
    with _errors():
        count = alloc.clear(fy, json_body().get("line_ids"))
        db.session.commit()
    return jsonify(notices=[notice(f"Ventilation retirée ({count}).")])


@bp.route("/analytic-targets")
def analytic_targets():
    """Activités et clés pour le champ « Affectation analytique » des éditeurs (lot AG8.c) ; vide hors agricole."""
    from app.services.analytic_allocation import targets_options
    return jsonify(items=targets_options() if analytic.enabled() else [])


@bp.route("/fiscal-years/<int:fy_id>/activity-margins")
def activity_margins(fy_id):
    """Marge par activité et par atelier de l'exercice (lot AG8.d)."""
    from app.services import analytic_margins
    fy = _fy(fy_id)
    return jsonify(item=analytic_margins.view(fy, _campaign()))
