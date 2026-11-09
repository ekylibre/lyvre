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
from app.services import vat_installments, vat_return
from app.services.ledger_errors import LedgerError
from app.services.vat_return import VatReturnError

from . import ApiError, bp, get_or_404, json_body, notice

STATUS_LABELS = {**VAT_RETURN_STATUSES, "to_prepare": "À préparer", "in_progress": "Mois en cours",
                 "dispensed": "Dispensé"}
INSTALLMENT_LABELS = {"validated": "Enregistré", "declared": "Payé"}


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
    labels = INSTALLMENT_LABELS if ret.form == vat_return.INSTALLMENT else STATUS_LABELS
    return {"id": ret.id, "form": ret.form, "status": ret.status, "status_label": labels[ret.status],
            "due_cents": ret.due_cents, "credit_cents": ret.credit_cents, "refund_cents": ret.refund_cents,
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
    """Périodes (mois ou trimestres) de l'exercice `?fiscal_year_id=` (défaut : exercice déclarant le plus récent)."""
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
            rows.append({"period": row["period"], "label": row["label"], "start": _iso(row["start"]), "end": _iso(row["end"]),
                         "deadline": _iso(row["deadline"]), "late": row["late"], "status": row["status"],
                         "status_label": STATUS_LABELS[row["status"]], "return": _return_payload(ret)})
    return jsonify(items=rows, fiscal_year={"id": fy.id, "label": fy.label, "vat_period": fy.vat_period} if fy else None,
                   fiscal_years=[{"value": str(y.id), "label": y.label} for y in years],
                   setup=None if fy is not None else vat_return.setup_hint())


@bp.route("/vat-returns/preview")
def vat_returns_preview():
    """CA3 de la période `?period=AAAA-MM` ou `AAAA-T1` : figée si validée, sinon calculée (rien n'est écrit) avec ses
    contrôles et le remboursement possible."""
    start, end = _period(request.args.get("period"))
    ret = vat_return.return_for(start)
    if ret is not None:
        detail = ret.detail
        return jsonify(period=vat_return.period_key(start, end), label=vat_return.period_label(start, end),
                       form=detail.get("form", "3310-CA3-SD"), form_code=ret.form,
                       rows=detail["rows"], codes=detail["codes"], refund=None,
                       checks=[], deadline=_iso(ret.deadline), form_year=detail["form_year"],
                       credit_carried_cents=ret.credit_carried_cents, due_cents=ret.due_cents,
                       credit_cents=ret.credit_cents, vat_return=_return_payload(ret))
    with _errors():
        result = vat_return.preview(start, end)
    refund = None
    if result["form_code"] == vat_return.CA12A:  # cadre VII : maximum de la ligne 44, sans minimum à respecter
        maximum = result["refund_max_cents"]
        refund = {"minimum_cents": 100 if maximum else 0, "maximum_cents": maximum, "possible": maximum > 0}
    elif result["gross_credit_cents"]:
        annual = end.month == 12
        from app.services import reg_params
        minimum = reg_params.value("vat.rsa.refund_min_annual_cents" if annual else "vat.rsa.refund_min_period_cents",
                                   end, default=15000 if annual else 76000)
        refund = {"minimum_cents": minimum, "maximum_cents": result["gross_credit_cents"],
                  "possible": result["gross_credit_cents"] >= minimum}
    return jsonify(period=result["period"], label=result["label"], refund=refund, form=result["form"],
                   form_code=result["form_code"], installments_cents=result.get("installments_cents"), rows=result["rows"],
                   codes=result["codes"], checks=result["checks"],
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
    data = json_body()
    start, end = _period(data.get("period"))
    refund = data.get("refund_cents") or 0
    if not isinstance(refund, int) or isinstance(refund, bool):
        raise ApiError("validation_error", "Remboursement en centimes.", 422, {"refund": "Montant invalide."})
    extra = {}
    if data.get("tca_euros") not in (None, ""):  # CA12A ligne 31 : saisie libre, en euros (Q-V3)
        if not isinstance(data["tca_euros"], int) or isinstance(data["tca_euros"], bool) or data["tca_euros"] < 0:
            raise ApiError("validation_error", "Ligne 31 : montant en euros entiers.", 422, {"tca_euros": "Montant invalide."})
        extra["31"] = data["tca_euros"]
    with _errors():
        ret = vat_return.validate(start, end, current_user.id, refund_cents=refund, extra=extra)
        db.session.commit()
    label = vat_return.period_label(start, end)
    refund_text = f" ; remboursement de {ret.refund_cents // 100} € demandé (formulaire 3519)" if ret.refund_cents else ""
    message = (f"Déclaration de {label} validée : TVA à payer {ret.due_cents // 100} €." if ret.due_cents
               else f"Déclaration de {label} validée : crédit de TVA {ret.credit_cents // 100} € reporté{refund_text}."
               if ret.credit_cents or ret.refund_cents else f"Déclaration de {label} validée (néant).")
    return jsonify(item=_return_payload(ret), notices=[notice(message)]), 201


@bp.route("/vat-returns/<int:return_id>/unvalidate", methods=["POST"])
def vat_returns_unvalidate(return_id):
    ret = get_or_404(VatReturn, return_id, "Déclaration introuvable.")
    label = vat_return.period_label(ret.period_start, ret.period_end)
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
    if ret.form == vat_return.INSTALLMENT:
        message = (f"Acompte n° {ret.detail.get('number')} payé ({ret.due_cents // 100} €) : rapprochez le prélèvement "
                   "du compte 44551.")
    else:
        message = f"Déclaration de {vat_return.period_label(ret.period_start, ret.period_end)} déposée : période verrouillée."
    return jsonify(item=_return_payload(ret), notices=[notice(message)])


# ------------------------------------------------------------------ acomptes du RSA (lot AG2.c, 3525 bis)

def _schedule_payload(data: dict) -> dict:
    ref = data["reference"]
    return {"period": data["period"], "label": data["label"], "start": _iso(data["start"]), "end": _iso(data["end"]),
            "reference": ref, "dispensed": data["dispensed"], "proposed_cents": data["proposed_cents"],
            "planned_cents": data["planned_cents"], "exemption_cents": data["exemption_cents"], "share_bp": data["share_bp"],
            "estimate": {**data["estimate"], "until": _iso(data["estimate"]["until"])} if data["estimate"] else None,
            "annual_return": _return_payload(data["annual_return"]), "warnings": data["warnings"],
            "items": [{"number": i["number"], "label": i["label"], "start": _iso(i["start"]), "end": _iso(i["end"]),
                       "deadline": _iso(i["deadline"]), "status": i["status"],
                       "status_label": INSTALLMENT_LABELS.get(i["status"]) or STATUS_LABELS[i["status"]],
                       "late": i["late"], "amount_cents": i["amount_cents"], "motive": i["motive"],
                       "can_validate": i["can_validate"], "return": _return_payload(i["return"])}
                      for i in data["items"]]}


@bp.route("/vat-returns/installments")
def vat_returns_installments():
    """Acomptes de la période annuelle `?period=AAAA-A` (ou `AAAA-MM-A`) : référence, dispense, échéancier."""
    period = _period(request.args.get("period"))
    with _errors():
        data = vat_installments.schedule(period)
    return jsonify(_schedule_payload(data))


@bp.route("/vat-returns/installments/reference", methods=["PUT"])
def vat_returns_installments_reference():
    """TVA due l'année précédente (et TVA sur immobilisations déduite), sans CA12A précédente dans Lyvre."""
    data = json_body()
    period = _period(data.get("period"))
    with _errors():
        vat_installments.save_reference(period, data.get("reference_cents"), data.get("assets_cents"))
        db.session.commit()
        payload = _schedule_payload(vat_installments.schedule(period))
    return jsonify(item=payload, notices=[notice("Référence des acomptes enregistrée.")])


@bp.route("/vat-returns/installments", methods=["POST"])
def vat_returns_installments_validate():
    data = json_body()
    period = _period(data.get("period"))
    with _errors():
        ret, warnings = vat_installments.validate(period, data.get("number"), data.get("amount_cents"),
                                                  data.get("motive"), current_user.id)
        db.session.commit()
    number = ret.detail["number"]
    text = (f"Acompte n° {number} enregistré : {ret.due_cents // 100} € à payer avant le {ret.deadline:%d/%m/%Y} "
            f"(bulletin 3525 bis)." if ret.due_cents else f"Acompte n° {number} enregistré à 0 € (bulletin 3525 bis à déposer).")
    return jsonify(item=_return_payload(ret),
                   notices=[notice(text)] + [notice(w, level="warning") for w in warnings]), 201
