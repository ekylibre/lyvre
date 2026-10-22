"""Indicateurs « Visibilité & Impact » : tableau de bord par période, synchronisation des
sources externes (GA4, Facebook), saisie mensuelle sans API, facteurs d'impact (admin).
L'export XLSX reste servi par Flask (`impact.export_xlsx`)."""
from datetime import date

from flask import jsonify, request, url_for
from flask_login import current_user

from app.decorators import admin_required
from app.extensions import db
from app.models import ImpactFactor, MetricSnapshot
from app.services import dashboard_service, external_config, impact_engine, metric_catalog, metrics_sync
from app.utils.list_filters import month_options_all_fy, month_options_for_fy, parse_month, year_options_all_fy

from . import ApiError, bp, invalid, json_body, notice

PERIOD_ARGS = ("gran", "month", "quarter", "year", "start", "end")


def _iso(value):
    return value.isoformat() if value else None


def _kpi(k) -> dict:
    return {"key": k.key, "label": k.label, "unit": k.unit, "value": k.value, "formatted": k.formatted,
            "delta_pct": k.delta_pct, "trend": list(k.trend), "source": k.source, "source_label": k.source_label,
            "origin": k.origin, "higher_is_better": k.higher_is_better, "available": k.available}


def _integration(name):
    return {"available": external_config.is_available(name), "message": external_config.unavailable_message(name)}


@bp.route("/impact")
def impact_dashboard():
    period = dashboard_service.period_from_args(request.args)
    view = dashboard_service.build_dashboard(period)
    args = {key: request.args.get(key, "") for key in PERIOD_ARGS}
    # Valeurs effectives du filtre : la période courante préremplit mois et année.
    current = {**args, "gran": period.gran, "month": args["month"] or period.start.strftime("%Y-%m"),
               "year": args["year"] or str(period.start.year)}
    return jsonify(
        period={"label": view.period.label, "start": _iso(period.start), "end": _iso(period.end), "gran": period.gran},
        current=current,
        highlights=[{k: h.get(k) for k in ("key", "label", "formatted", "available", "icon")} for h in view.highlights],
        sections=[{"key": dim, "label": label, "kpis": [_kpi(k) for k in view.sections.get(dim, [])]}
                  for dim, label in metric_catalog.DIMENSIONS],
        sources=[{"source": s.get("source"), "label": s.get("label"), "status": s.get("status"),
                  "fresh_at": _iso(s.get("fresh_at"))} for s in view.sources_status],
        meta={"months": month_options_all_fy(), "years": [str(y) for y in year_options_all_fy()],
              "ga4": _integration("ga4"), "facebook": _integration("facebook"),
              "export_url": url_for("impact.export_xlsx", **{k: v for k, v in current.items() if v})},
    )


@bp.route("/impact/sync", methods=["POST"])
def impact_sync():
    data = json_body()
    today = date.today()
    if data.get("scope") == "year":
        try:
            year = int(data.get("year") or today.year)
        except (TypeError, ValueError):
            raise invalid("Année invalide.", "year") from None
        result = metrics_sync.sync_metrics_year(year)
        label = f"année {year}"
    else:
        year, month = parse_month(str(data.get("month") or "")) or (today.year, today.month)
        result = metrics_sync.sync_metrics(year, month)
        label = f"{year}-{month:02d}"
    imported = sum(v.get("imported", 0) for v in result.values())
    errors = [e for v in result.values() for e in v.get("errors", [])]
    notices = [notice(f"Synchronisation ({label}) : {imported} métrique(s) importée(s).",
                      "warning" if errors else "success")]
    notices += [notice(e, "warning") for e in errors[:4]]
    return jsonify(notices=notices)


# ------------------------------------------------------------------ saisie manuelle


def _month_start(arg):
    parsed = parse_month(arg or "")
    year, month = parsed if parsed else (date.today().year, date.today().month)
    return date(year, month, 1)


@bp.route("/impact/manual")
def impact_manual():
    start = _month_start(request.args.get("month"))
    existing = {r.metric_key: float(r.value) for r in
                MetricSnapshot.query.filter_by(period_start=start, granularity="month").all()}
    fields = []
    for m in metric_catalog.manual_metrics():
        value = existing.get(m.key)
        if value is not None and m.unit == "cents":
            value = round(value / 100, 2)
        fields.append({"key": m.key, "label": m.label, "unit": "€" if m.unit == "cents" else m.unit,
                       "in_euros": m.unit == "cents", "value": value})
    month = start.strftime("%Y-%m")
    options = month_options_for_fy()
    if month not in {o["value"] for o in options}:
        options = [*options, {"value": month, "label": month}]
    return jsonify(month=month, fields=fields, meta={"months": options})


@bp.route("/impact/manual", methods=["PUT"])
def impact_manual_save():
    data = json_body()
    start = _month_start(str(data.get("month") or ""))
    values = data.get("values") or {}
    errors, parsed = {}, []
    for m in metric_catalog.manual_metrics():
        raw = values.get(m.key)
        if raw is None or str(raw).strip() == "":
            continue  # champ vide : valeur existante conservée
        try:
            num = float(str(raw).replace(",", "."))
        except ValueError:
            errors[m.key] = "Nombre attendu."
            continue
        if num < 0:
            errors[m.key] = "Valeur positive attendue."
        else:
            parsed.append((m, num))
    if errors:
        raise ApiError("validation_error", "Valeurs invalides.", status=422, fields=errors)
    for m, num in parsed:
        metrics_sync.upsert_snapshot(source=m.source, metric_key=m.key, period_start=start,
                                     value=int(round(num * 100)) if m.unit == "cents" else num, unit=m.unit,
                                     is_manual=True, user_id=getattr(current_user, "id", None))
    db.session.commit()
    return jsonify(notices=[notice(f"Saisie enregistrée pour {start:%Y-%m}.")])


# ------------------------------------------------------------------ facteurs d'impact


def _factor(f: ImpactFactor) -> dict:
    return {"id": f.id, "key": f.key, "value": float(f.value), "unit": f.unit, "source_label": f.source_label or "",
            "source_url": f.source_url or "", "updated_at": _iso(f.updated_at)}


@bp.route("/impact/factors")
@admin_required
def impact_factors():
    impact_engine.ensure_seeded()
    return jsonify(items=[_factor(f) for f in ImpactFactor.query.order_by(ImpactFactor.key)])


@bp.route("/impact/factors", methods=["PUT"])
@admin_required
def impact_factors_save():
    rows = {f.id: f for f in ImpactFactor.query.all()}
    items = json_body().get("items")
    if not isinstance(items, list):
        raise invalid("Facteurs attendus.")
    errors = {}
    for item in items:
        f = rows.get(item.get("id")) if isinstance(item, dict) else None
        if f is None:
            continue
        try:
            f.value = float(str(item.get("value")).replace(",", "."))
        except (TypeError, ValueError):
            errors[f"value_{f.id}"] = "Nombre attendu."
            continue
        url = str(item.get("source_url") or "").strip()
        if url and not url.startswith(("https://", "http://")):
            errors[f"source_url_{f.id}"] = "Adresse http(s) attendue."
            continue
        f.source_label = str(item.get("source_label") or "").strip()[:200] or None
        f.source_url = url[:500] or None
        f.updated_by_user_id = getattr(current_user, "id", None)
    if errors:
        db.session.rollback()
        raise ApiError("validation_error", "Valeurs invalides.", status=422, fields=errors)
    db.session.commit()
    return jsonify(items=[_factor(f) for f in ImpactFactor.query.order_by(ImpactFactor.key)],
                   notices=[notice("Facteurs d'impact mis à jour.")])
