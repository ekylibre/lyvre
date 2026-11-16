"""États de la comptabilité simplifiée et verrouillage d'exercice (lot D.4)."""
from datetime import date

from flask import jsonify, request
from flask_login import current_user

from app.access import current_role
from app.extensions import db
from app.models import FiscalYear
from app.models.instance_membership import ROLE_ADMIN
from app.services import micro_ba, simple_reports
from app.tenant import current_chart, current_instance

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


def _micro_year() -> int:
    """Exploitation agricole en comptabilité simplifiée (micro-BA) ; année civile `?year=` (défaut : en cours)."""
    instance = current_instance()
    if current_chart() != "agri" or instance is None or instance.bookkeeping != "simple":
        raise ApiError("not_found", "État réservé aux exploitations agricoles au micro-BA.", 404)
    year = request.args.get("year", type=int) or date.today().year
    if not 1990 <= year <= 2100:
        raise ApiError("validation_error", "Année invalide.", 422, fields={"year": "Année invalide."})
    return year


@bp.route("/simple/reports/receipts-book")
def simple_receipts_book():
    """Livre des recettes du micro-BA `?year=&group_small=1` (lot AG1.d)."""
    year = _micro_year()
    book = micro_ba.receipts_book(year, group_small=request.args.get("group_small", "1") != "0")
    from flask import url_for
    return jsonify(**book, export_url=url_for("exports.receipts_book_xlsx", year=year,
                                              group_small=request.args.get("group_small", "1")))


@bp.route("/simple/reports/micro-ba")
def simple_micro_ba():
    """Récapitulatif du micro-BA : recettes de N, N-1, N-2, moyenne, bénéfice forfaitaire (lot AG1.d)."""
    return jsonify(micro_ba.summary(_micro_year()))


@bp.route("/simple/reports/micro-ba/carryover", methods=["PUT"])
def simple_micro_ba_carryover():
    """`{year, receipts_cents, note}` : recettes retenues d'une année antérieure à Lyvre (vide : retirées)."""
    year = _micro_year()
    from app.access import permissions
    if not permissions(current_role())["write"]:
        raise ApiError("forbidden", "Lecture seule : modification réservée au trésorier ou à l'administrateur.", 403)
    data = json_body()
    try:
        micro_ba.save_carryover(data.get("year"), data.get("receipts_cents"), data.get("note"))
    except micro_ba.MicroError as exc:
        raise ApiError("validation_error", exc.message, exc.status, fields={exc.field: exc.message}) from None
    return jsonify(item=micro_ba.summary(year), notices=[notice("Recettes de l'année antérieure enregistrées.")])


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
