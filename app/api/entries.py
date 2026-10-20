"""Journal entries for the EntryForm island."""
from flask import jsonify, url_for
from flask_login import login_required

from app.extensions import db
from app.models import BankTransaction, JournalEntry
from app.services.ledger import (
    LedgerError, entry_is_reconciled, post_validated_entry, update_entry,
    validate_entry_payload,
)

from . import ApiError, bp, json_body


def serialize_entry(entry):
    return {
        "id": entry.id,
        "reference": entry.reference,
        "fiscal_year_id": entry.fiscal_year_id,
        "journal_id": entry.journal_id,
        "entry_date": entry.entry_date.isoformat(),
        "description": entry.description or "",
        "reconciled": entry_is_reconciled(entry),
        "editable": not entry.fiscal_year.closed,
        "url": url_for("entries.detail", entry_id=entry.id),
        "lines": [
            {"id": l.id, "account_id": l.account_id, "account_code": l.account.code,
             "account_label": l.account.label, "label": l.label or "",
             "debit_cents": l.debit_cents, "credit_cents": l.credit_cents}
            for l in entry.lines
        ],
    }


def _validated(data):
    clean, errors = validate_entry_payload(data)
    if errors:
        raise ApiError("validation_error", "L'écriture contient des erreurs.", 422, errors)
    return clean


def _get_entry(entry_id):
    entry = db.session.get(JournalEntry, entry_id)
    if entry is None:
        raise ApiError("not_found", "Écriture introuvable.", 404)
    return entry


@bp.route("/entries/validate", methods=["POST"])
@login_required
def entries_validate():
    """Dry run: errors by field, nothing is saved."""
    _clean, errors = validate_entry_payload(json_body())
    return jsonify(errors=errors)


@bp.route("/entries", methods=["POST"])
@login_required
def entries_create():
    data = json_body()
    clean = _validated(data)

    bank_transaction = None
    bt_id = data.get("bank_transaction_id")
    if bt_id is not None:
        bank_transaction = db.session.get(BankTransaction, bt_id) if isinstance(bt_id, int) else None
        if bank_transaction is None:
            raise ApiError("not_found", "Transaction bancaire introuvable.", 404)

    try:
        entry = post_validated_entry(clean, bank_transaction=bank_transaction)
    except LedgerError as e:
        raise ApiError("conflict", str(e), 409)

    body = serialize_entry(entry)
    return jsonify(body), 201, {"Location": body["url"]}


@bp.route("/entries/<int:entry_id>")
@login_required
def entries_get(entry_id):
    return jsonify(serialize_entry(_get_entry(entry_id)))


@bp.route("/entries/<int:entry_id>", methods=["PUT"])
@login_required
def entries_update(entry_id):
    entry = _get_entry(entry_id)
    clean = _validated(json_body())
    try:
        update_entry(entry, clean)
    except LedgerError as e:
        raise ApiError("conflict", str(e), 409)
    return jsonify(serialize_entry(entry))
