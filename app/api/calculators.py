"""Calculettes (lot AG12, claudedocs/design_calculettes_agricoles.md) : liste filtrée par type de structure,
spécification avec préremplissage, calcul sans écriture. Utilisateurs connectés (AGD14)."""
from datetime import date

from flask import jsonify, request

from app.services import calculators
from app.services.calculators import CHART_LABELS, CalculatorError, Context
from app.tenant import current_instance

from . import ApiError, bp, invalid, json_body


def _chart() -> str | None:
    inst = current_instance()
    return inst.chart if inst is not None else None


def _module(code: str):
    try:
        return calculators.get(code)
    except CalculatorError as exc:
        raise ApiError("not_found", exc.message, status=404) from None


@bp.route("/calculators")
def calculators_list():
    chart = request.args.get("chart") or _chart()
    items = [calculators.spec_payload(m, _chart()) for m in calculators.registry().values()]
    if chart and chart != "all":
        items = [i for i in items if chart in i["charts"]]
    items.sort(key=lambda i: (list(calculators.CATEGORIES).index(i["category"]), i["number"]))
    return jsonify(items=items, meta={"chart": chart, "instance_chart": _chart(),
                                      "charts": [{"value": k, "label": v} for k, v in CHART_LABELS.items()],
                                      "categories": [{"value": k, "label": v} for k, v in calculators.CATEGORIES.items()]})


@bp.route("/calculators/<code>")
def calculators_detail(code):
    module = _module(code)
    spec = module.SPEC
    data = calculators.spec_payload(module, _chart())
    if data["prefillable"]:
        ctx = Context(chart=_chart(), choice=request.args.get("choice") or None)
        data["prefill_options"] = module.prefill_options(ctx) if hasattr(module, "prefill_options") else None
        data["prefill"] = module.prefill(ctx)
    else:
        data["prefill_options"], data["prefill"] = None, {}
    data["params"] = calculators.params(spec, date.today())
    return jsonify(item=data)


@bp.route("/calculators/<code>", methods=["POST"])
def calculators_compute(code):
    """`{values: {clé: valeur}, origins?: {clé: origine}}` : résultat, détail, paramètres et texte à copier."""
    module = _module(code)
    body = json_body()
    origins = body.get("origins") if isinstance(body.get("origins"), dict) else {}
    try:
        return jsonify(result=calculators.run(module, body.get("values") or {},
                                              {k: str(v)[:200] for k, v in origins.items()}))
    except CalculatorError as exc:
        if exc.status == 422:
            raise invalid(exc.message, exc.field) from None
        code = {409: "conflict", 503: "unavailable"}.get(exc.status, "not_found")
        raise ApiError(code, exc.message, status=exc.status) from None
