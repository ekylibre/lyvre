"""États de la comptabilité simplifiée et verrouillage d'exercice (lot D.4)."""
from datetime import date

from flask import jsonify, request
from flask_login import current_user

from app.access import current_role
from app.extensions import db
from app.models import FiscalYear
from app.models.instance_membership import ROLE_ADMIN
from app.services import simple_reports
from app.tenant import current_instance

from . import ApiError, bp, get_or_404, json_body, notice
from .fiscal_years import fiscal_year_payload


def _fiscal_year():
    fy_id = request.args.get("fiscal_year_id", type=int)
    if fy_id:
        return get_or_404(FiscalYear, fy_id, "Exercice introuvable.")
    today = date.today()
    fy = (FiscalYear.query.filter(FiscalYear.start_date <= today, FiscalYear.end_date >= today).first()
          or FiscalYear.query.order_by(FiscalYear.end_date.desc()).first())
    if fy is None:
        raise ApiError("not_found", "Aucun exercice : créez-en un dans Compta › Exercices.", 404)
    return fy


def _years():
    return [{"value": str(y.id), "label": y.label} for y in FiscalYear.query.order_by(FiscalYear.start_date.desc())]


@bp.route("/simple/reports/income-statement")
def simple_income_statement():
    """Compte de résultat simplifié `?fiscal_year_id=` : par catégorie, N et N-1."""
    fy = _fiscal_year()
    return jsonify(fiscal_year_id=fy.id, fiscal_years=_years(), **simple_reports.income_statement(fy))


@bp.route("/simple/reports/treasury")
def simple_treasury():
    """Situation de trésorerie `?fiscal_year_id=` : soldes cumulés début / fin d'exercice."""
    fy = _fiscal_year()
    return jsonify(fiscal_year_id=fy.id, fiscal_years=_years(), **simple_reports.treasury_situation(fy))


@bp.route("/fiscal-years/<int:fy_id>/lock", methods=["POST"])
def fiscal_years_lock(fy_id):
    """`{locked}` : verrouillage simple (comptabilité simplifiée) ; déverrouiller : administrateur."""
    instance = current_instance()
    if instance is None or instance.bookkeeping != "simple":
        raise ApiError("conflict", "En partie double, l'exercice se clôture avec l'assistant de clôture.", 409)
    fy = get_or_404(FiscalYear, fy_id, "Exercice introuvable.")
    locked = bool(json_body().get("locked", True))
    if not locked and current_role() != ROLE_ADMIN:
        raise ApiError("forbidden", "Déverrouillage réservé à l'administrateur de l'instance.", 403)
    try:
        simple_reports.lock(fy, locked, current_user.id)
    except simple_reports.SimpleReportError as exc:
        db.session.rollback()
        raise ApiError("conflict", exc.message, exc.status) from None
    message = f"Exercice « {fy.label} » {'verrouillé' if locked else 'déverrouillé'}."
    return jsonify(item=fiscal_year_payload(fy), notices=[notice(message)])
