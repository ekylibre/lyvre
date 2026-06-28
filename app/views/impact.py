from io import BytesIO

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, Response,
)
from flask_login import login_required, current_user

from app.decorators import admin_required
from app.extensions import db
from app.models import ImpactFactor
from app.models import MetricSnapshot
from app.services import dashboard_service
from app.services import metric_catalog
from app.services import impact_engine
from app.services import metrics_sync
from app.utils.list_filters import (
    month_options_for_fy, month_options_all_fy, year_options_all_fy, parse_month,
)

bp = Blueprint("impact", __name__, url_prefix="/impact")


def _period_context():
    """Contexte commun du filtre de période (dashboard + rapport)."""
    period = dashboard_service.period_from_args(request.args)
    return period, {
        "period": period,
        "gran": period.gran,
        "month_options": month_options_all_fy(),
        "year_options": year_options_all_fy(),
        # Présélectionne le mois/l'année effectifs de la période courante.
        "current_month": request.args.get("month") or period.start.strftime("%Y-%m"),
        "current_quarter": request.args.get("quarter", ""),
        "current_year": request.args.get("year") or str(period.start.year),
        "current_start": request.args.get("start", ""),
        "current_end": request.args.get("end", ""),
    }


@bp.route("/")
@login_required
def index():
    period, ctx = _period_context()
    view = dashboard_service.build_dashboard(period)
    return render_template(
        "impact/dashboard.html",
        view=view,
        dimensions=metric_catalog.DIMENSIONS,
        **ctx,
    )


@bp.route("/report")
@login_required
def report():
    period, ctx = _period_context()
    view = dashboard_service.build_dashboard(period)
    return render_template(
        "impact/report.html",
        view=view,
        dimensions=metric_catalog.DIMENSIONS,
        **ctx,
    )


@bp.route("/export.xlsx")
@login_required
def export_xlsx():
    import pandas as pd

    period = dashboard_service.period_from_args(request.args)
    view = dashboard_service.build_dashboard(period)

    records = []
    for dim, label in metric_catalog.DIMENSIONS:
        for kpi in view.sections.get(dim, []):
            records.append({
                "Dimension": label,
                "Indicateur": kpi.label,
                "Valeur": kpi.formatted,
                "Variation %": (round(kpi.delta_pct, 1)
                                if kpi.delta_pct is not None else ""),
                "Source": kpi.source_label or kpi.source,
            })
    df = pd.DataFrame(records, columns=[
        "Dimension", "Indicateur", "Valeur", "Variation %", "Source",
    ])
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Visibilité & Impact")
    response = Response(
        buf.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response.headers["Content-Disposition"] = (
        'attachment; filename="visibilite-impact.xlsx"'
    )
    return response


@bp.route("/factors", methods=["GET", "POST"])
@login_required
@admin_required
def factors():
    impact_engine.ensure_seeded()
    rows = ImpactFactor.query.order_by(ImpactFactor.key).all()

    if request.method == "POST":
        for f in rows:
            raw = (request.form.get(f"value_{f.id}") or "").strip().replace(",", ".")
            try:
                f.value = float(raw)
            except ValueError:
                flash(f"Valeur invalide pour « {f.key} » — ignorée.", "warning")
                continue
            f.source_label = (request.form.get(f"source_label_{f.id}") or "").strip() or None
            f.source_url = (request.form.get(f"source_url_{f.id}") or "").strip() or None
            f.updated_by_user_id = getattr(current_user, "id", None)
        db.session.commit()
        flash("Facteurs d'impact mis à jour.", "success")
        return redirect(url_for("impact.factors"))

    return render_template("impact/factors.html", factors=rows)


@bp.route("/manual", methods=["GET", "POST"])
@login_required
def manual():
    """Saisie mensuelle des métriques sans API (Vinted, groupe FB, collectés/dons)."""
    from datetime import date, datetime

    metrics = metric_catalog.manual_metrics()
    today = date.today()

    # Mois sélectionné (défaut : mois courant).
    month_arg = (request.values.get("month") or "").strip()
    parsed = parse_month(month_arg)
    if parsed:
        year, month = parsed
    else:
        year, month = today.year, today.month
        month_arg = f"{year:04d}-{month:02d}"
    period_start = date(year, month, 1)

    if request.method == "POST":
        for m in metrics:
            raw = (request.form.get(m.key) or "").strip().replace(",", ".")
            if raw == "":
                continue
            try:
                num = float(raw)
            except ValueError:
                flash(f"Valeur invalide pour « {m.label} » — ignorée.", "warning")
                continue
            value = int(round(num * 100)) if m.unit == "cents" else num
            metrics_sync.upsert_snapshot(
                source=m.source, metric_key=m.key, period_start=period_start,
                value=value, unit=m.unit, is_manual=True,
                user_id=getattr(current_user, "id", None),
            )
        db.session.commit()
        flash(f"Saisie enregistrée pour {month_arg}.", "success")
        return redirect(url_for("impact.manual", month=month_arg))

    # Valeurs existantes pour pré-remplir le formulaire.
    existing = {
        r.metric_key: float(r.value)
        for r in MetricSnapshot.query.filter_by(
            period_start=period_start, granularity="month"
        ).all()
    }
    fields = []
    for m in metrics:
        val = existing.get(m.key)
        if val is not None and m.unit == "cents":
            display = f"{val / 100:.2f}"
        elif val is not None:
            display = f"{val:g}"
        else:
            display = ""
        fields.append({"metric": m, "value": display,
                       "in_euros": m.unit == "cents"})

    return render_template(
        "impact/manual_form.html",
        fields=fields,
        month=month_arg,
        month_options=month_options_for_fy(),
    )


@bp.route("/sync", methods=["POST"])
@login_required
def sync():
    from datetime import date
    today = date.today()
    scope = (request.form.get("scope") or "month").strip()

    if scope == "year":
        try:
            year = int(request.form.get("year") or today.year)
        except ValueError:
            year = today.year
        result = metrics_sync.sync_metrics_year(year)
        label = f"année {year}"
    else:
        parsed = parse_month((request.form.get("month") or "").strip())
        year, month = parsed if parsed else (today.year, today.month)
        result = metrics_sync.sync_metrics(year, month)
        label = f"{year}-{month:02d}"

    imported = sum(v.get("imported", 0) for v in result.values())
    errors = [e for v in result.values() for e in v.get("errors", [])]
    msg = f"Synchronisation ({label}) : {imported} métrique(s) importée(s)."
    flash(msg + (" " + " | ".join(errors[:4]) if errors else ""),
          "warning" if errors else "success")
    return redirect(request.referrer or url_for("impact.index"))
