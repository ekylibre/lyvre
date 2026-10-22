"""Exports tableur du lot C.3 (tous les rôles) : suivi budgétaire et compte de résultat d'un
projet. Écrans : SPA (Compta › Budget › Suivi, fiche projet) ; données : app/api/budgets.py,
app/api/projects.py."""
from datetime import date
from io import BytesIO

from flask import Blueprint, Response, abort, request
from flask_login import login_required
from openpyxl import Workbook
from openpyxl.styles import Font

from app.extensions import db
from app.models import FiscalYear, Project
from app.services import budget, projects

bp = Blueprint("exports", __name__)

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
EURO = '#,##0.00 "€";-#,##0.00 "€"'


def _date(value):
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        abort(400)


def _sheet(wb, title, header, rows, money_cols):
    ws = wb.create_sheet(title[:31])
    ws.append(header)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append(row)
    for col in money_cols:
        for cell in ws.iter_cols(min_col=col, max_col=col, min_row=2):
            for c in cell:
                c.number_format = EURO
    for column in ws.columns:
        ws.column_dimensions[column[0].column_letter].width = max(12, min(48, max(len(str(c.value or "")) for c in column) + 2))
    return ws


def _response(wb, filename):
    buf = BytesIO()
    wb.save(buf)
    response = Response(buf.getvalue(), mimetype=XLSX)
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@bp.route("/budget/tracking.xlsx")
@login_required
def budget_tracking_xlsx():
    fy = db.session.get(FiscalYear, request.args.get("fiscal_year_id", type=int) or 0) or abort(404)
    try:
        project = budget.project_or_error(request.args.get("project_id"))
    except budget.BudgetError:
        abort(404)
    data = budget.tracking(fy, project, _date(request.args.get("as_of")))
    wb = Workbook()
    wb.remove(wb.active)
    rows = [[{"expense": "Charges", "income": "Produits"}[r["kind"]], r["code"], r["label"] + (" (hors budget)" if r["unbudgeted"] else ""),
             r["planned_cents"] / 100, r["planned_to_date_cents"] / 100, r["actual_cents"] / 100, r["gap_cents"] / 100,
             r["rate"] / 100 if r["rate"] is not None else None] for r in data["rows"]]
    s = data["summary"]
    rows += [[], ["Total", "", "Charges", *(s["expense"][k] / 100 for k in ("planned_cents", "planned_to_date_cents", "actual_cents", "gap_cents"))],
             ["Total", "", "Produits", *(s["income"][k] / 100 for k in ("planned_cents", "planned_to_date_cents", "actual_cents", "gap_cents"))],
             ["Résultat", "", "", *(s["result"][k] / 100 for k in ("planned_cents", "planned_to_date_cents", "actual_cents"))]]
    ws = _sheet(wb, f"Suivi {fy.label}", ["Nature", "Compte", "Poste", "Prévu (année)", f"Prévu au {data['as_of']}",
                                          "Réalisé", "Écart", "Réalisé / prévu"], rows, (4, 5, 6, 7))
    for cell in ws.iter_cols(min_col=8, max_col=8, min_row=2):
        for c in cell:
            c.number_format = "0.0%"
    scope = f"-{project.name}" if project else ""
    return _response(wb, f"suivi-budget-{fy.label}{scope}.xlsx".replace(" ", "-"))


@bp.route("/projects/<int:project_id>/statement.xlsx")
@login_required
def project_statement_xlsx(project_id):
    project = db.session.get(Project, project_id) or abort(404)
    start, end = projects.default_period(project)
    data = projects.statement(project, _date(request.args.get("start")) or start, _date(request.args.get("end")) or end)
    wb = Workbook()
    wb.remove(wb.active)
    kinds = {"expense": "Charges", "income": "Produits"}
    t = data["totals"]
    _sheet(wb, "Compte de résultat", ["Nature", "Compte", "Libellé", "Montant"],
           [[kinds[a["kind"]], a["code"], a["label"], a["amount_cents"] / 100] for a in data["accounts"]]
           + [[], ["Total charges", "", "", t["expense_cents"] / 100], ["Total produits", "", "", t["income_cents"] / 100],
              ["Résultat", "", "", t["result_cents"] / 100]], (4,))
    _sheet(wb, "Détail", ["Date", "Pièce", "Libellé", "Compte", "Nature", "Montant", "Justificatif"],
           [[l["date"], l["reference"], l["label"], l["account"], kinds[l["kind"]], l["amount_cents"] / 100,
             request.host_url.rstrip("/") + l["document_url"] if l["document_url"] else ""] for l in data["lines"]], (6,))
    return _response(wb, f"projet-{project.name}-{data['start']}-{data['end']}.xlsx".replace(" ", "-"))


@bp.route("/receipts/signature")
@login_required
def receipts_signature():
    """Image de la signature des reçus (aperçu dans les paramètres)."""
    from flask import send_file

    from app.services import receipts
    path = receipts.signature_file()
    if path is None:
        abort(404)
    return send_file(path, max_age=0)
