"""Exercices comptables : création, clôture, assujettissement à la TVA."""
from datetime import date

from flask import jsonify

from app.extensions import db
from app.models import FiscalYear
from app.models.fiscal_year import FY_PROVISIONAL

from . import ApiError, bp, get_or_404, invalid, json_body, notice


def fiscal_year_payload(fy: FiscalYear) -> dict:
    return {"id": fy.id, "label": fy.label, "start_date": fy.start_date.isoformat(),
            "end_date": fy.end_date.isoformat(), "closed": fy.closed, "status": fy.status,
            "status_label": fy.status_label, "vat_liable": fy.vat_liable}


def _date(data, key, label):
    try:
        return date.fromisoformat(str(data.get(key) or ""))
    except ValueError:
        raise invalid(f"{label} : date invalide.", key) from None


@bp.route("/fiscal-years")
def fiscal_years_list():
    years = FiscalYear.query.order_by(FiscalYear.start_date.desc()).all()
    return jsonify(items=[fiscal_year_payload(fy) for fy in years])


@bp.route("/fiscal-years", methods=["POST"])
def fiscal_years_create():
    data = json_body()
    label = str(data.get("label") or "").strip()
    if not label:
        raise invalid("Le libellé est obligatoire.", "label")
    start, end = _date(data, "start_date", "Début"), _date(data, "end_date", "Fin")
    if end < start:
        raise invalid("La fin de l'exercice doit suivre son début.", "end_date")
    fy = FiscalYear(label=label[:50], start_date=start, end_date=end,
                    vat_liable=bool(data.get("vat_liable")))
    db.session.add(fy)
    db.session.commit()
    return jsonify(item=fiscal_year_payload(fy), notices=[notice(f"Exercice « {fy.label} » créé.")]), 201


@bp.route("/fiscal-years/<int:fy_id>/close", methods=["POST"])
def fiscal_years_close(fy_id):
    fy = get_or_404(FiscalYear, fy_id, "Exercice introuvable.")
    if fy.closed:
        raise ApiError("conflict", "Cet exercice est déjà clôturé.", status=409)
    # Clôture provisoire (verrou réversible) ; l'assistant de clôture complète viendra la remplacer.
    fy.status = FY_PROVISIONAL
    db.session.commit()
    return jsonify(item=fiscal_year_payload(fy), notices=[notice(
        f"Exercice « {fy.label} » en clôture provisoire : les écritures sont verrouillées.")])


@bp.route("/fiscal-years/<int:fy_id>", methods=["PATCH"])
def fiscal_years_update(fy_id):
    """Seul l'assujettissement à la TVA se modifie, sur un exercice ouvert."""
    fy = get_or_404(FiscalYear, fy_id, "Exercice introuvable.")
    data = json_body()
    if "vat_liable" not in data:
        raise invalid("Rien à modifier.")
    if fy.closed:
        raise ApiError("conflict", "Cet exercice est clôturé.", status=409)
    fy.vat_liable = bool(data["vat_liable"])
    db.session.commit()
    state = "soumis" if fy.vat_liable else "non soumis"
    return jsonify(item=fiscal_year_payload(fy), notices=[notice(
        f"Exercice « {fy.label} » {state} à la TVA. "
        "S'applique aux factures comptabilisées à partir de maintenant.")])
