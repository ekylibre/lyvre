"""Notes de frais des associés (module « Associés », lot A3) : dépense avancée sans facture,
écriture charge / 455 de l'associé au journal AS. Lecture pour tous les membres ; saisie et
suppression par le trésorier ou l'administrateur. Multipart (`payload` + `attachment`) pour
joindre le justificatif.
"""
import json

from flask import abort, jsonify, request, send_file

from app.models import Account, Associate, Entity
from app.models.associate import AssociateExpense
from app.services import associate_operations, attachments
from app.services.associate_operations import OperationError
from app.services.attachments import AttachmentError

from . import ApiError, bp, get_or_404, invalid, json_body, notice
from .associates import _require_enabled


@bp.route("/associate-expenses")
def associate_expenses_list():
    _require_enabled()
    query = AssociateExpense.query
    associate_id = request.args.get("associate_id", type=int)
    if associate_id:
        query = query.filter_by(associate_id=associate_id)
    items = query.order_by(AssociateExpense.expense_date.desc(), AssociateExpense.id.desc()).all()
    return jsonify(items=[associate_operations.expense_payload(e) for e in items], meta={
        "associates": [{"value": str(a.id), "label": a.name} for a in Associate.query.join(Entity).order_by(Entity.name)],
        "charge_accounts": [{"value": a.code, "label": f"{a.code} — {a.label}"} for a in
                            Account.query.filter(Account.code.like("6%"), Account.is_header.is_(False)).order_by(Account.code)],
    })


@bp.route("/associate-expenses", methods=["POST"])
def associate_expenses_create():
    _require_enabled()
    token = None
    if request.files or request.form:
        try:
            data = json.loads(request.form.get("payload") or "{}")
        except ValueError:
            raise invalid("Formulaire illisible.") from None
        upload = request.files.get("attachment")
        if upload is not None and upload.filename:
            try:
                token = attachments.stage(upload)
            except AttachmentError as exc:
                raise invalid(str(exc), "attachment") from None
    else:
        data = json_body()
    try:
        expense = associate_operations.create_expense(data, token)
    except OperationError as exc:
        raise invalid(str(exc), exc.field) from None
    return jsonify(item=associate_operations.expense_payload(expense), notices=[notice(
        f"Note de frais de {expense.associate.name} enregistrée (écriture {expense.journal_entry.reference}).")]), 201


@bp.route("/associate-expenses/<int:expense_id>", methods=["DELETE"])
def associate_expenses_delete(expense_id):
    _require_enabled()
    expense = get_or_404(AssociateExpense, expense_id, "Note de frais introuvable.")
    try:
        associate_operations.delete_expense(expense)
    except OperationError as exc:
        raise ApiError("conflict", str(exc), status=409) from None
    return jsonify(notices=[notice("Note de frais supprimée avec son écriture.")])


@bp.route("/associate-expenses/<int:expense_id>/attachment")
def associate_expenses_attachment(expense_id):
    _require_enabled()
    expense = get_or_404(AssociateExpense, expense_id, "Note de frais introuvable.")
    path = attachments.path_of(expense)
    if path is None:
        abort(404)
    return send_file(path, mimetype=expense.attachment_mime, download_name=expense.attachment_name or path.name,
                     as_attachment=bool(request.args.get("download")))
