"""Exercices comptables : création, clôture, assujettissement à la TVA."""
from datetime import date

from flask import jsonify, url_for

from app.extensions import db
from app.models import FiscalYear
from app.models.fiscal_year import FY_PROVISIONAL
from app.services import fec

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
    # Clôture provisoire (verrou réversible) : les écritures sont numérotées pour le FEC.
    fy.status = FY_PROVISIONAL
    db.session.flush()
    fec.validate(fy)
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


@bp.route("/fiscal-years/<int:fy_id>/fec/check")
def fiscal_years_fec_check(fy_id):
    """Contrôles avant export du FEC, puis relecture du fichier produit (format, équilibre,
    numérotation) ; lien de téléchargement si tout est bon."""
    fy = get_or_404(FiscalYear, fy_id, "Exercice introuvable.")
    errors, warnings = fec.check(fy)
    body = {"errors": errors, "warnings": warnings, "problems": [], "filename": None, "stats": None,
            "frozen": bool(fy.fec_sha256), "sha256": fy.fec_sha256, "download_url": None}
    if not errors:
        fec_file = fec.build(fy)
        body.update(problems=fec.verify(fec_file.content), filename=fec_file.filename,
                    sha256=fy.fec_sha256 or fec_file.sha256,
                    stats={"lines": fec_file.lines, "entries": fec_file.entries,
                           "total_debit_cents": fec_file.total_debit_cents,
                           "total_credit_cents": fec_file.total_credit_cents},
                    download_url=url_for("fec.download", fy_id=fy.id))
    return jsonify(body)
