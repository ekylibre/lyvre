"""Budget (lot C.2) : grille comptes × mois d'un exercice, globale ou par projet ; copie de
l'exercice précédent (budget ou réalisé)."""
from contextlib import contextmanager
from datetime import date

from flask import jsonify, request

from app.extensions import db
from app.models import FiscalYear
from app.services import budget, projects

from . import ApiError, bp, get_or_404, json_body, notice


@contextmanager
def _errors():
    try:
        yield
    except budget.BudgetError as exc:
        db.session.rollback()
        raise ApiError("validation_error", exc.message, 422, {exc.field: exc.message} if exc.field else None) from None


def _payload(fy, project, rows, **extra):
    previous = budget.previous_fiscal_year(fy)
    return {"fiscal_year": {"id": fy.id, "label": fy.label, "closed": fy.closed},
            "project_id": project.id if project else None, "months": budget.months(fy), "rows": rows,
            "totals": budget.totals(rows), "previous_fiscal_year": previous.label if previous else None, **extra}


@bp.route("/budgets/<int:fy_id>")
def budgets_get(fy_id):
    """`?project_id=` (vide : budget sans projet) ; options de comptes et de projets."""
    fy = get_or_404(FiscalYear, fy_id, "Exercice introuvable.")
    with _errors():
        project = budget.project_or_error(request.args.get("project_id"))
    selected = [project.id] if project else []
    return jsonify(_payload(fy, project, budget.grid(fy, project), accounts=budget.account_options(),
                            projects=projects.options(selected)))


@bp.route("/budgets/<int:fy_id>", methods=["PUT"])
def budgets_save(fy_id):
    """`{project_id, rows: [{account_id, annual_cents} | {account_id, months: [...]}]}` : remplace la grille."""
    fy = get_or_404(FiscalYear, fy_id, "Exercice introuvable.")
    data = json_body()
    with _errors():
        project = budget.project_or_error(data.get("project_id"))
        rows = budget.save(fy, project, data.get("rows"))
    scope = f"projet « {project.name} »" if project else "budget général"
    return jsonify({**_payload(fy, project, rows), "notices": [notice(f"Budget {fy.label} enregistré ({scope}).")]})


@bp.route("/budgets/<int:fy_id>/copy")
def budgets_copy(fy_id):
    """`?source=budget|actual&project_id=` : grille proposée d'après l'exercice précédent (non enregistrée)."""
    fy = get_or_404(FiscalYear, fy_id, "Exercice introuvable.")
    with _errors():
        project = budget.project_or_error(request.args.get("project_id"))
        rows = budget.copy_rows(fy, project, request.args.get("source"))
    return jsonify(_payload(fy, project, rows))


@bp.route("/budgets/<int:fy_id>/tracking")
def budgets_tracking(fy_id):
    """Suivi `?project_id=&as_of=` : prévu (année, à date), réalisé à date, écart par poste ; hors budget."""
    fy = get_or_404(FiscalYear, fy_id, "Exercice introuvable.")
    with _errors():
        project = budget.project_or_error(request.args.get("project_id"))
        as_of = _as_of(request.args.get("as_of"))
    data = budget.tracking(fy, project, as_of)
    query = f"fiscal_year_id={fy.id}&as_of={data['as_of']}" + (f"&project_id={project.id}" if project else "")
    return jsonify(fiscal_year={"id": fy.id, "label": fy.label}, project_id=project.id if project else None,
                   projects=projects.options([project.id] if project else []),
                   export_url=f"/budget/tracking.xlsx?{query}", **data)


def _as_of(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise budget.BudgetError("Date invalide.", "as_of") from None
