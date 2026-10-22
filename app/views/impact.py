"""Visibilité & Impact : export XLSX servi par Flask (écrans : SPA, API : app/api/impact.py)."""
from io import BytesIO

from flask import Blueprint, Response, request
from flask_login import login_required

from app.services import dashboard_service, metric_catalog

bp = Blueprint("impact", __name__, url_prefix="/impact")


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
