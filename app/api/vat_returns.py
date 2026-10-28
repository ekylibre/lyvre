"""Déclarations de TVA (lot T3) : mois des exercices déclarants, CA3 calculée à la volée, validation
(cases figées, liquidation), annulation de la dernière, dépôt (« déclarée », mois verrouillé).
Le rôle `accountant` lit et exporte (refus centralisé des écritures)."""
from contextlib import contextmanager
from datetime import date

from flask import jsonify, request
from flask_login import current_user

from app.extensions import db
from app.models import FiscalYear, VatReturn
from app.models.vat_return import VAT_RETURN_STATUSES
from app.services import vat_return
from app.services.ledger_errors import LedgerError
from app.services.vat_return import VatReturnError

from . import ApiError, bp, get_or_404, json_body, notice

STATUS_LABELS = {**VAT_RETURN_STATUSES, "to_prepare": "À préparer", "in_progress": "Mois en cours"}


@contextmanager
def _errors():
    try:
        yield
    except VatReturnError as exc:
        db.session.rollback()
        fields = {exc.field: str(exc)} if exc.field else None
        raise ApiError("conflict" if exc.status == 409 else "validation_error", str(exc), exc.status, fields,
                       extra={"problems": exc.problems} if exc.problems else None) from None
    except LedgerError as exc:
        db.session.rollback()
        raise ApiError(getattr(exc, "code", "conflict"), str(exc), 409) from None


def _iso(value):
    return value.isoformat() if value else None


def _return_payload(ret: VatReturn | None) -> dict | None:
    if ret is None:
        return None
    entry = ret.liquidation_entry
    return {"id": ret.id, "status": ret.status, "status_label": STATUS_LABELS[ret.status],
            "due_cents": ret.due_cents, "credit_cents": ret.credit_cents,
            "credit_carried_cents": ret.credit_carried_cents, "declared_on": _iso(ret.declared_on),
            "declared_reference": ret.declared_reference, "validated_at": _iso(ret.validated_at),
            "liquidation_entry": {"id": entry.id, "reference": entry.reference} if entry is not None else None}


def _period(text):
    with _errors():
        return vat_return.parse_period(text)


def _line_payload(line) -> dict:
    entry = line.entry
    return {"id": line.id, "entry_id": entry.id, "reference": entry.reference, "date": entry.entry_date.isoformat(),
            "description": entry.description or "", "account": line.account.code, "label": line.label or "",
            "debit_cents": line.debit_cents, "credit_cents": line.credit_cents, "vat_code": line.vat_code,
            "vat_base_cents": line.vat_base_cents}


@bp.route("/vat-returns")
def vat_returns_list():
    """Mois de l'exercice `?fiscal_year_id=` (défaut : exercice déclarant le plus récent)."""
    years = vat_return.declaring_years()
    fy_id = request.args.get("fiscal_year_id", type=int)
    fy = db.session.get(FiscalYear, fy_id) if fy_id else None
    if fy is None or not fy.vat_period:
        today = date.today()
        fy = next((y for y in years if y.start_date <= today <= y.end_date), years[0] if years else None)
    rows = []
    if fy is not None:
        for row in vat_return.periods(fy):
            ret = row["return"]
            rows.append({"period": row["period"], "start": _iso(row["start"]), "end": _iso(row["end"]),
                         "deadline": _iso(row["deadline"]), "late": row["late"], "status": row["status"],
                         "status_label": STATUS_LABELS[row["status"]], "return": _return_payload(ret)})
    return jsonify(items=rows, fiscal_year={"id": fy.id, "label": fy.label} if fy else None,
                   fiscal_years=[{"value": str(y.id), "label": y.label} for y in years])


@bp.route("/vat-returns/preview")
def vat_returns_preview():
    """CA3 du mois `?period=AAAA-MM` : figée si validée, sinon calculée (rien n'est écrit) avec ses contrôles."""
    start, end = _period(request.args.get("period"))
    ret = vat_return.return_for(start)
    if ret is not None:
        detail = ret.detail
        return jsonify(period=vat_return.period_key(start), rows=detail["rows"], codes=detail["codes"],
                       checks=[], deadline=_iso(ret.deadline), form_year=detail["form_year"],
                       credit_carried_cents=ret.credit_carried_cents, due_cents=ret.due_cents,
                       credit_cents=ret.credit_cents, vat_return=_return_payload(ret))
    with _errors():
        result = vat_return.preview(start, end)
    return jsonify(period=result["period"], rows=result["rows"], codes=result["codes"], checks=result["checks"],
                   deadline=_iso(result["deadline"]), form_year=result["form_year"],
                   credit_carried_cents=result["credit_carried_cents"], due_cents=result["due_cents"],
                   credit_cents=result["credit_cents"], lines_count=result["lines_count"], vat_return=None)


@bp.route("/vat-returns/lines")
def vat_returns_lines():
    """Lignes d'écriture qui composent la case `?box=` du mois `?period=`."""
    start, end = _period(request.args.get("period"))
    box = request.args.get("box") or ""
    with _errors():
        lines = vat_return.lines_for(start, end, box, vat_return.return_for(start))
    return jsonify(items=[_line_payload(line) for line in lines])


@bp.route("/vat-returns", methods=["POST"])
def vat_returns_validate():
    start, end = _period(json_body().get("period"))
    with _errors():
        ret = vat_return.validate(start, end, current_user.id)
        db.session.commit()
    message = (f"Déclaration de {start:%m/%Y} validée : TVA à payer {ret.due_cents // 100} €." if ret.due_cents
               else f"Déclaration de {start:%m/%Y} validée : crédit de TVA {ret.credit_cents // 100} € reporté."
               if ret.credit_cents else f"Déclaration de {start:%m/%Y} validée (néant).")
    return jsonify(item=_return_payload(ret), notices=[notice(message)]), 201


@bp.route("/vat-returns/<int:return_id>/unvalidate", methods=["POST"])
def vat_returns_unvalidate(return_id):
    ret = get_or_404(VatReturn, return_id, "Déclaration introuvable.")
    label = f"{ret.period_start:%m/%Y}"
    with _errors():
        vat_return.unvalidate(ret)
        db.session.commit()
    return jsonify(notices=[notice(f"Validation de la déclaration de {label} annulée.")])


@bp.route("/vat-returns/<int:return_id>/declare", methods=["POST"])
def vat_returns_declare(return_id):
    ret = get_or_404(VatReturn, return_id, "Déclaration introuvable.")
    data = json_body()
    try:
        declared_on = date.fromisoformat(str(data.get("declared_on") or ""))
    except ValueError:
        raise ApiError("validation_error", "Date de dépôt obligatoire.", 422,
                       {"declared_on": "Date attendue (AAAA-MM-JJ)."}) from None
    with _errors():
        vat_return.declare(ret, declared_on, data.get("reference"), current_user.id)
        db.session.commit()
    return jsonify(item=_return_payload(ret),
                   notices=[notice(f"Déclaration de {ret.period_start:%m/%Y} déposée : mois verrouillé.")])
