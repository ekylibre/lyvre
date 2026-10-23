"""Recettes et dépenses (comptabilité simplifiée, lot D.3) : liste, saisie, modification,
suppression ; transactions bancaires à catégoriser."""
from contextlib import contextmanager
from datetime import date, timedelta

from flask import jsonify, request

from app.extensions import db
from app.models import BankAccount, Entity, FiscalYear
from app.services import projects, simple_categories, simple_operations
from app.services.ledger import LedgerError

from . import ApiError, bp, json_body, notice


@contextmanager
def _errors():
    try:
        yield
    except simple_operations.OperationError as exc:
        db.session.rollback()
        code = {404: "not_found", 422: "validation_error"}.get(exc.status, "conflict")
        raise ApiError(code, exc.message, exc.status, {exc.field: exc.message} if exc.field else None) from None
    except LedgerError as exc:
        db.session.rollback()
        raise ApiError("conflict", str(exc), 409) from None


def _int(name):
    value = request.args.get(name)
    return int(value) if value and value.isdigit() else None


def _period():
    """`?fiscal_year_id=` (défaut : exercice du jour), `?month=AAAA-MM` facultatif."""
    fy = db.session.get(FiscalYear, _int("fiscal_year_id")) if _int("fiscal_year_id") else None
    today = date.today()
    fy = fy or FiscalYear.query.filter(FiscalYear.start_date <= today, FiscalYear.end_date >= today).first() \
        or FiscalYear.query.order_by(FiscalYear.end_date.desc()).first()
    month = request.args.get("month")
    if month:
        try:
            year, number = (int(x) for x in month.split("-"))
            start = date(year, number, 1)
            end = date(year + (number == 12), number % 12 + 1, 1) - timedelta(days=1)
            return fy, start, end
        except ValueError:
            raise ApiError("validation_error", "Mois invalide (AAAA-MM).", 422) from None
    return fy, (fy.start_date if fy else today), (fy.end_date if fy else today)


@bp.route("/simple/operations")
def simple_operations_list():
    """Recettes et dépenses de l'exercice (ou du mois), filtres catégorie, sens, compte, projet ;
    options de saisie (catégories actives, comptes, tiers, projets, exercices)."""
    fy, start, end = _period()
    data = simple_operations.operations(start, end, category_id=_int("category_id"), kind=request.args.get("kind") or None,
                                        bank_account_id=_int("bank_account_id"), project_id=_int("project_id"))
    categories = [simple_categories.payload(c) for c in simple_categories.listing(include_inactive=False)]
    return jsonify(
        fiscal_year={"id": fy.id, "label": fy.label, "closed": fy.closed} if fy else None, **data,
        meta={"categories": categories,
              "bank_accounts": [{"value": str(b.id), "label": b.label, "kind": b.kind}
                                for b in BankAccount.query.order_by(BankAccount.kind, BankAccount.label)],
              "entities": [{"value": str(e.id), "label": e.name} for e in Entity.query.order_by(Entity.name)],
              "projects": projects.options(),
              "fiscal_years": [{"value": str(y.id), "label": y.label}
                               for y in FiscalYear.query.order_by(FiscalYear.start_date.desc())]})


@bp.route("/simple/operations", methods=["POST"])
def simple_operations_create():
    """`{date, label, amount_cents, category_id, bank_account_id, entity_id?, project_id?}`."""
    with _errors():
        entry = simple_operations.create(json_body())
    return jsonify(notices=[notice(f"Opération enregistrée ({entry.reference}).")]), 201


@bp.route("/simple/operations/<int:entry_id>", methods=["PUT"])
def simple_operations_update(entry_id):
    with _errors():
        entry = simple_operations.update(entry_id, json_body())
    return jsonify(notices=[notice(f"Opération {entry.reference} modifiée.")])


@bp.route("/simple/operations/<int:entry_id>", methods=["DELETE"])
def simple_operations_delete(entry_id):
    with _errors():
        reference = simple_operations.delete(entry_id)
    return jsonify(notices=[notice(f"Opération {reference} supprimée.")])


@bp.route("/simple/to-categorize")
def simple_to_categorize():
    """Transactions bancaires importées non rapprochées (à catégoriser)."""
    return jsonify(items=simple_operations.to_categorize())


@bp.route("/simple/to-categorize/<int:transaction_id>", methods=["POST"])
def simple_categorize(transaction_id):
    """`{category_id, label?, entity_id?, project_id?}` : opération créée et rapprochée."""
    with _errors():
        entry = simple_operations.categorize(transaction_id, json_body())
    return jsonify(notices=[notice(f"Transaction catégorisée ({entry.reference}).")]), 201
