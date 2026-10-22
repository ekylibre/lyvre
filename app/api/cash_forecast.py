"""Prévisionnel de trésorerie (lot C.4) : 12 mois glissants, saisies manuelles."""
from contextlib import contextmanager
from datetime import date

from flask import jsonify, request

from app.extensions import db
from app.models import BankAccount, CashForecastItem
from app.services import cash_forecast

from . import ApiError, bp, get_or_404, json_body, notice


@contextmanager
def _errors():
    try:
        yield
    except cash_forecast.ForecastError as exc:
        db.session.rollback()
        raise ApiError("validation_error", exc.message, 422, {exc.field: exc.message} if exc.field else None) from None


@bp.route("/cash-forecast")
def cash_forecast_get():
    """`?today=` (tests, simulation) ; soldes de départ, 12 mois, alerte, saisies manuelles."""
    try:
        today = date.fromisoformat(request.args["today"]) if request.args.get("today") else None
    except ValueError:
        raise ApiError("validation_error", "Date invalide.", 422) from None
    data = cash_forecast.forecast(today)
    items = [cash_forecast.item_payload(i) for i in CashForecastItem.query.order_by(CashForecastItem.date)]
    bank_accounts = [{"value": str(b.id), "label": b.label} for b in BankAccount.query.order_by(BankAccount.label)]
    return jsonify(items=items, bank_accounts=bank_accounts, **data)


@bp.route("/cash-forecast/items", methods=["POST"])
def cash_forecast_item_create():
    with _errors():
        item = cash_forecast.save_item(None, json_body())
    return jsonify(item=cash_forecast.item_payload(item), notices=[notice(f"« {item.label} » ajouté au prévisionnel.")]), 201


@bp.route("/cash-forecast/items/<int:item_id>", methods=["PUT"])
def cash_forecast_item_update(item_id):
    item = get_or_404(CashForecastItem, item_id, "Saisie introuvable.")
    with _errors():
        cash_forecast.save_item(item, json_body())
    return jsonify(item=cash_forecast.item_payload(item), notices=[notice(f"« {item.label} » enregistré.")])


@bp.route("/cash-forecast/items/<int:item_id>", methods=["DELETE"])
def cash_forecast_item_delete(item_id):
    item = get_or_404(CashForecastItem, item_id, "Saisie introuvable.")
    label = item.label
    db.session.delete(item)
    db.session.commit()
    return jsonify(notices=[notice(f"« {label} » retiré du prévisionnel.")])
