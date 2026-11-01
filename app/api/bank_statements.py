"""Relevés de compte (lot RQ1, claudedocs/design_releves_qonto.md § 4) : liste des mois de l'exercice
en cours et relevés stockés, récupération Qonto au clic. Le PDF est servi par
`exports.bank_statement_pdf` ; aucune suppression (R6). Écriture refusée au comptable par la garde
générale de l'API."""
from flask import jsonify, request, url_for
from flask_login import current_user

from app.extensions import db
from app.models import BankAccount
from app.services import bank_statements, external_config

from . import ApiError, bp, get_or_404, notice, require_integration


def _iso(value):
    return value.isoformat() if value else None


def statement_payload(statement) -> dict:
    return {"id": statement.id, "source": statement.source, "file_name": statement.file_name,
            "file_size": statement.file_size, "fetched_at": _iso(statement.fetched_at),
            "replaced_at": _iso(statement.replaced_at),
            "url": url_for("exports.bank_statement_pdf", statement_id=statement.id)}


@bp.route("/bank-accounts/<int:ba_id>/statements")
def bank_statements_list(ba_id):
    ba = get_or_404(BankAccount, ba_id, "Compte bancaire introuvable.")
    qonto = external_config.state("qonto", "transactions") if ba.qonto_account_id else None
    fy = bank_statements.current_fiscal_year()
    return jsonify(
        items=[{"period": f"{row['period']:%Y-%m}",
                "statement": statement_payload(row["statement"]) if row["statement"] else None}
               for row in bank_statements.overview(ba)],
        fiscal_year={"id": fy.id, "label": fy.label} if fy else None,
        qonto=({"enabled": qonto["enabled"], "available": qonto["enabled"] and qonto["available"],
                "message": qonto["message"]} if qonto else None),
        # Dépôt (lot RQ3) : comptes bancaires hors Qonto, mois des exercices ouverts.
        upload_months=([f"{m:%Y-%m}" for m in bank_statements.upload_months()]
                       if not ba.qonto_account_id and ba.kind == "bank" else []),
    )


@bp.route("/bank-accounts/<int:ba_id>/statements", methods=["POST"])
def bank_statements_upload(ba_id):
    """Dépôt d'un relevé PDF (multipart : `period` AAAA-MM, `file`) ; remplace celui du mois."""
    ba = get_or_404(BankAccount, ba_id, "Compte bancaire introuvable.")
    try:
        statement, outcome = bank_statements.store_upload(ba, request.form.get("period"), request.files.get("file"),
                                                          user_id=getattr(current_user, "id", None))
    except bank_statements.StatementError as exc:
        db.session.rollback()
        raise ApiError("validation_error", str(exc), status=422) from None
    month = f"{statement.period:%m/%Y}"
    text = {"new": f"Relevé de {month} déposé.", "replaced": f"Relevé de {month} remplacé.",
            "unchanged": f"Relevé de {month} identique à celui déjà déposé."}[outcome]
    return jsonify(item=statement_payload(statement), notices=[notice(text, "success")]), 201


@bp.route("/bank-accounts/<int:ba_id>/statements/fetch", methods=["POST"])
def bank_statements_fetch(ba_id):
    """Relevés Qonto des mois de l'exercice en cours, téléchargés tout de suite (≤ 12 PDF)."""
    from app.services import integrations
    from app.services.qonto_client import QontoError

    ba = get_or_404(BankAccount, ba_id, "Compte bancaire introuvable.")
    if not ba.qonto_account_id:
        raise ApiError("conflict", "Ce compte bancaire n'est pas rattaché à Qonto.", status=409)
    require_integration("qonto", "transactions")
    try:
        result = bank_statements.fetch_qonto(ba, user_id=getattr(current_user, "id", None))
    except bank_statements.StatementError as exc:
        db.session.rollback()
        raise ApiError("conflict", str(exc), status=409) from None
    except QontoError as exc:
        db.session.rollback()
        raise ApiError("qonto_error", integrations.mask_secrets("qonto", integrations.describe_error("qonto", exc)),
                       status=502) from None
    fetched = result["new"] + result["replaced"]
    text = (f"{result['new']} relevé(s) récupéré(s), {result['replaced']} remplacé(s), "
            f"{result['unchanged']} déjà à jour.") if fetched or result["unchanged"] else \
        "Aucun relevé disponible chez Qonto pour l'exercice en cours."
    notices = [notice(text, "success" if fetched else "info")]
    notices += [notice(e, "warning") for e in result["errors"][:10]]
    return jsonify(result=result, notices=notices)
