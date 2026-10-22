"""Exercices comptables : création, assistant de clôture (étapes 1 à 8), assujettissement à la TVA."""
from contextlib import contextmanager
from datetime import date, timedelta

from flask import jsonify, request, url_for
from flask_login import current_user

from app.access import current_role, instance_admin_required
from app.extensions import db
from app.models import FiscalYear
from app.models.instance_membership import ROLE_ADMIN
from app.services import closing, dedicated_funds, fec, projects
from app.services.ledger import LedgerError

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
    """`{final: false}` : clôture provisoire (étapes 1 à 5 décidées) ; `{final: true}` : clôture
    définitive (administrateur de l'instance), FEC figé, irréversible."""
    fy = get_or_404(FiscalYear, fy_id, "Exercice introuvable.")
    data = request.get_json(silent=True) or {}
    final = bool(data.get("final"))
    if final and current_role() != ROLE_ADMIN:
        raise ApiError("forbidden", "Clôture définitive réservée à l'administrateur de l'instance.", status=403)
    with _closing_errors():
        if final:
            closing.close_final(fy, current_user.id)
            message = f"Exercice « {fy.label} » clôturé définitivement : FEC figé."
        else:
            closing.close_provisional(fy, current_user.id)
            message = f"Exercice « {fy.label} » en clôture provisoire : écritures verrouillées et numérotées."
    return jsonify(item=fiscal_year_payload(fy), notices=[notice(message)])


@bp.route("/fiscal-years/<int:fy_id>/reopen", methods=["POST"])
@instance_admin_required
def fiscal_years_reopen(fy_id):
    fy = get_or_404(FiscalYear, fy_id, "Exercice introuvable.")
    with _closing_errors():
        closing.reopen(fy, current_user.id, json_body().get("reason"))
    return jsonify(item=fiscal_year_payload(fy), notices=[notice(f"Exercice « {fy.label} » rouvert.")])


@contextmanager
def _closing_errors():
    try:
        yield
    except closing.ClosingError as exc:
        db.session.rollback()
        code = {404: "not_found", 422: "validation_error"}.get(exc.status, "conflict")
        raise ApiError(code, exc.message, status=exc.status) from None
    except LedgerError as exc:
        db.session.rollback()
        raise ApiError("conflict", str(exc), status=409) from None


@bp.route("/fiscal-years/<int:fy_id>/closing")
def fiscal_years_closing(fy_id):
    """État de l'assistant : étapes, contrôles recalculés, écritures d'inventaire, résultat."""
    fy = get_or_404(FiscalYear, fy_id, "Exercice introuvable.")
    following = closing.next_fiscal_year(fy)
    return jsonify(
        fiscal_year=fiscal_year_payload(fy),
        steps=closing.steps(fy),
        checks=[c.__dict__ for c in closing.checks(fy)],
        inventory=[{"id": e.id, "reference": e.reference, "kind": e.inventory_kind,
                    "kind_label": closing.INVENTORY_KINDS.get(e.inventory_kind, {}).get("label", ""),
                    "description": e.description, "amount_cents": sum(l.debit_cents for l in e.lines),
                    "lines": [{"account": l.account.code, "debit_cents": l.debit_cents, "credit_cents": l.credit_cents}
                              for l in e.lines]} for e in closing.inventory_entries(fy)],
        inventory_options=closing.inventory_options(),
        result=closing.result(fy),
        next_fiscal_year=fiscal_year_payload(following) if following else None,
        dedicated_funds={"funds": [dedicated_funds.payload(f, fy) for f in dedicated_funds.funds_for(fy)],
                         "kinds": dedicated_funds.options(), "projects": projects.options()},
        opening=_opening_payload(fy, following),
        allocation=_allocation_payload(fy),
        events=closing.events(fy),
    )


def _entry_link(entry):
    return {"id": entry.id, "reference": entry.reference, "url": f"/entries/{entry.id}"} if entry else None


def _opening_payload(fy, following):
    """Étape 7 : à-nouveaux prévus (exercice au moins en clôture provisoire) et déjà portés."""
    carried = closing.opening_entries(fy)
    preview, error = [], None
    if fy.status != "open":
        try:
            preview = closing.opening_lines(fy)
        except closing.ClosingError as exc:
            error = exc.message
    return {
        "lines": [{k: line[k] for k in ("account_code", "label", "debit_cents", "credit_cents")} for line in preview],
        "error": error,
        "reversals_planned": len(closing.inventory_entries(fy)),
        "entries": [dict(_entry_link(e), source=e.source, description=e.description) for e in carried],
        "next_start_date": (fy.end_date + timedelta(days=1)).isoformat(),
    }


def _allocation_payload(fy):
    return {
        "result_cents": closing.result_to_allocate(fy),
        "decided_on": fy.allocation_decided_on.isoformat() if fy.allocation_decided_on else None,
        "body": fy.allocation_body,
        "entry": _entry_link(closing.allocation_entry(fy)),
        "options": closing.allocation_options(),
    }


@bp.route("/fiscal-years/<int:fy_id>/dedicated-funds", methods=["POST"])
def fiscal_years_dedicated_fund_add(fy_id):
    """Étape 3 : `{label, kind, amount_cents, resource_account_code?}` (ressource affectée reçue en N)."""
    fy = get_or_404(FiscalYear, fy_id, "Exercice introuvable.")
    data = json_body()
    with _closing_errors():
        fund = dedicated_funds.create_fund(fy, data.get("label"), data.get("kind"), data.get("amount_cents"),
                                           data.get("resource_account_code"), current_user.id, data.get("project_id"))
    return jsonify(notices=[notice(f"Fonds dédié « {fund.label} » créé.")]), 201


@bp.route("/fiscal-years/<int:fy_id>/dedicated-funds/<int:fund_id>", methods=["PUT"])
def fiscal_years_dedicated_fund_project(fy_id, fund_id):
    """`{project_id}` (null : aucun) : projet financé par la ressource (lot C.5)."""
    fy = get_or_404(FiscalYear, fy_id, "Exercice introuvable.")
    with _closing_errors():
        fund = dedicated_funds.set_project(fy, fund_id, json_body().get("project_id"), current_user.id)
    return jsonify(notices=[notice(f"Fonds « {fund.label} » : projet enregistré.")])


@bp.route("/fiscal-years/<int:fy_id>/dedicated-funds/<int:fund_id>", methods=["DELETE"])
def fiscal_years_dedicated_fund_delete(fy_id, fund_id):
    fy = get_or_404(FiscalYear, fy_id, "Exercice introuvable.")
    with _closing_errors():
        dedicated_funds.delete_fund(fy, fund_id, current_user.id)
    return jsonify(notices=[notice("Fonds dédié supprimé.")])


@bp.route("/fiscal-years/<int:fy_id>/dedicated-funds/<int:fund_id>/movements", methods=["POST"])
def fiscal_years_dedicated_fund_movement(fy_id, fund_id):
    """`{kind: allocation|use, amount_cents}` : écriture 689x/19x ou 19x/789x au dernier jour."""
    fy = get_or_404(FiscalYear, fy_id, "Exercice introuvable.")
    data = json_body()
    with _closing_errors():
        movement = dedicated_funds.add_movement(fy, fund_id, data.get("kind"), data.get("amount_cents"),
                                                current_user.id)
    label = dedicated_funds.MOVEMENT_LABELS[movement.kind]
    return jsonify(notices=[notice(f"{label} enregistrée : écriture {movement.entry.reference}.")]), 201


@bp.route("/fiscal-years/<int:fy_id>/dedicated-fund-movements/<int:movement_id>", methods=["DELETE"])
def fiscal_years_dedicated_fund_movement_delete(fy_id, movement_id):
    fy = get_or_404(FiscalYear, fy_id, "Exercice introuvable.")
    with _closing_errors():
        dedicated_funds.delete_movement(fy, movement_id, current_user.id)
    return jsonify(notices=[notice("Mouvement de fonds dédié supprimé.")])


@bp.route("/fiscal-years/<int:fy_id>/opening", methods=["POST"])
def fiscal_years_opening(fy_id):
    """Étape 7 : `{create_next}` ; à-nouveaux et extournes (re)générés dans l'exercice suivant."""
    fy = get_or_404(FiscalYear, fy_id, "Exercice introuvable.")
    with _closing_errors():
        following, opening, reversals = closing.generate_opening(
            fy, current_user.id, create_next=bool(json_body().get("create_next")))
    parts = [f"à-nouveaux {opening.reference}" if opening else "aucun solde à reporter"]
    if reversals:
        parts.append(f"{len(reversals)} extourne(s)")
    return jsonify(notices=[notice(f"Exercice {following.label} : " + ", ".join(parts) + ".")])


@bp.route("/fiscal-years/<int:fy_id>/allocation", methods=["POST"])
def fiscal_years_allocation(fy_id):
    """Étape 8 : `{decided_on, body, lines: [{account_code, amount_cents}]}`."""
    fy = get_or_404(FiscalYear, fy_id, "Exercice introuvable.")
    data = json_body()
    with _closing_errors():
        entry = closing.allocate(fy, data.get("decided_on"), data.get("body"), data.get("lines"), current_user.id)
    detail = f" : écriture {entry.reference}" if entry else ""
    return jsonify(notices=[notice(f"Affectation du résultat {fy.label} enregistrée{detail}.")])


@bp.route("/fiscal-years/<int:fy_id>/allocation", methods=["DELETE"])
def fiscal_years_allocation_cancel(fy_id):
    fy = get_or_404(FiscalYear, fy_id, "Exercice introuvable.")
    with _closing_errors():
        closing.cancel_allocation(fy, current_user.id)
    return jsonify(notices=[notice(f"Affectation du résultat {fy.label} annulée.")])


@bp.route("/fiscal-years/<int:fy_id>/closing/<step>", methods=["POST"])
def fiscal_years_closing_step(fy_id, step):
    """`{state: done|skipped|todo, note}` (motif obligatoire pour `skipped`)."""
    fy = get_or_404(FiscalYear, fy_id, "Exercice introuvable.")
    data = json_body()
    with _closing_errors():
        closing.set_step(fy, step, data.get("state"), data.get("note"), current_user.id)
    return jsonify(steps=closing.steps(fy))


@bp.route("/fiscal-years/<int:fy_id>/inventory", methods=["POST"])
def fiscal_years_inventory_add(fy_id):
    """`{kind, account_code, amount_cents, label, counterpart_code?}`."""
    fy = get_or_404(FiscalYear, fy_id, "Exercice introuvable.")
    data = json_body()
    with _closing_errors():
        entry = closing.add_inventory(fy, data.get("kind"), data.get("account_code"), data.get("amount_cents"),
                                      data.get("label"), data.get("counterpart_code"), current_user.id)
    return jsonify(notices=[notice(f"Écriture d'inventaire {entry.reference} enregistrée.")]), 201


@bp.route("/fiscal-years/<int:fy_id>/inventory/<int:entry_id>", methods=["DELETE"])
def fiscal_years_inventory_delete(fy_id, entry_id):
    fy = get_or_404(FiscalYear, fy_id, "Exercice introuvable.")
    with _closing_errors():
        closing.delete_inventory(fy, entry_id, current_user.id)
    return jsonify(notices=[notice("Écriture d'inventaire supprimée.")])


@bp.route("/fiscal-years/<int:fy_id>/fec/preview")
def fiscal_years_fec_preview(fy_id):
    """Essai à blanc du FEC (exercice encore ouvert) : contrôles, relecture, totaux."""
    fy = get_or_404(FiscalYear, fy_id, "Exercice introuvable.")
    fec_file, errors, warnings, problems = fec.preview(fy)
    return jsonify(errors=errors, warnings=warnings, problems=problems,
                   filename=fec_file.filename if fec_file else None, frozen=False, sha256=None, download_url=None,
                   stats={"lines": fec_file.lines, "entries": fec_file.entries,
                          "total_debit_cents": fec_file.total_debit_cents,
                          "total_credit_cents": fec_file.total_credit_cents} if fec_file else None)


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
