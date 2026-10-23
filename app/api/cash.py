"""Caisse (lot D.1) : mouvements d'un compte de caisse, saisie d'un mouvement, dépôt en banque."""
from contextlib import contextmanager
from datetime import date

from flask import jsonify, request

from app.extensions import db
from app.models import BankAccount
from app.services import cash
from app.services.ledger import LedgerError

from . import ApiError, bp, json_body, notice
from .bank_accounts import bank_account_payload


@contextmanager
def _errors():
    try:
        yield
    except cash.CashError as exc:
        db.session.rollback()
        code = {404: "not_found", 422: "validation_error"}.get(exc.status, "conflict")
        raise ApiError(code, exc.message, exc.status, {exc.field: exc.message} if exc.field else None) from None
    except LedgerError as exc:
        db.session.rollback()
        raise ApiError("conflict", str(exc), 409) from None


def _date(name):
    value = request.args.get(name)
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        raise ApiError("validation_error", "Date invalide.", 422) from None


@bp.route("/bank-accounts/<int:ba_id>/cash")
def cash_movements(ba_id):
    """Mouvements `?start=&end=` (solde d'ouverture, solde courant), comptes bancaires de dépôt."""
    with _errors():
        ba = cash.cash_account(ba_id)
    data = cash.movements(ba, _date("start"), _date("end"))
    banks = [{"value": str(b.id), "label": b.label} for b in BankAccount.query.filter_by(kind="bank").order_by(BankAccount.label)]
    return jsonify(item=bank_account_payload(ba), banks=banks, **data)


@bp.route("/bank-accounts/<int:ba_id>/cash", methods=["POST"])
def cash_record(ba_id):
    """`{date, label, direction (in|out), amount_cents, account_id, project_id?}`."""
    with _errors():
        entry = cash.record(cash.cash_account(ba_id), json_body())
    return jsonify(notices=[notice(f"Mouvement de caisse enregistré ({entry.reference}).")]), 201


@bp.route("/bank-accounts/<int:ba_id>/cash/deposit", methods=["POST"])
def cash_deposit(ba_id):
    """`{date, amount_cents, bank_account_id, label?}` : dépôt d'espèces par le compte 581."""
    with _errors():
        out, into = cash.deposit(cash.cash_account(ba_id), json_body())
    return jsonify(notices=[notice(f"Dépôt en banque enregistré ({out.reference}, {into.reference}) ; "
                                   "la ligne bancaire se rapprochera du relevé.")]), 201
