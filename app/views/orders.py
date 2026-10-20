from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required

from app.models import Order, OrderLine, OrderPayment
from app.models.order import POS_ORDER_STATES
from app.services import external_config
from app.services.odoo_client import OdooConfigError
from app.services.odoo_pos_sync import sync_pos_orders
from app.utils.list_filters import (
    parse_sort, parse_month, apply_date_sort, apply_month_filter,
    sort_and_filter_context,
)

bp = Blueprint("orders", __name__, url_prefix="/orders")


def _odoo_configured():
    return external_config.is_available("odoo")


@bp.route("/")
@login_required
def index():
    sort = parse_sort(request.args.get("sort"))
    month_arg = request.args.get("month")
    month_tuple = parse_month(month_arg)

    query = Order.query
    query = apply_month_filter(query, Order.date_order, month_tuple)
    query = apply_date_sort(query, Order.date_order, sort)
    orders = query.order_by(Order.id.desc()).limit(500).all()
    return render_template(
        "orders/index.html",
        orders=orders,
        states=dict(POS_ORDER_STATES),
        configured=_odoo_configured(),
        **sort_and_filter_context(sort, month_arg),
    )


@bp.route("/<int:order_id>")
@login_required
def detail(order_id):
    order = Order.query.get_or_404(order_id)
    lines = OrderLine.query.filter_by(order_id=order.id).order_by(OrderLine.id).all()
    payments = (
        OrderPayment.query.filter_by(order_id=order.id)
        .order_by(OrderPayment.payment_date.asc().nullsfirst(), OrderPayment.id)
        .all()
    )
    return render_template(
        "orders/detail.html",
        order=order, lines=lines, payments=payments,
        states=dict(POS_ORDER_STATES),
    )


@bp.route("/sync", methods=["POST"])
@login_required
def sync():
    try:
        result = sync_pos_orders()
    except OdooConfigError as e:
        flash(str(e), "warning")
        return redirect(url_for("orders.index"))
    except Exception as e:
        current_app.logger.exception("Sync POS Odoo échouée")
        flash(f"Erreur de synchronisation : {e}", "danger")
        return redirect(url_for("orders.index"))

    flash(
        "Synchronisation OK — "
        f"{result['orders_imported']} nouvelle(s), {result['orders_updated']} mise(s) à jour, "
        f"{result['lines_total']} ligne(s), {result['payments_total']} paiement(s), "
        f"{result.get('entities_created', 0)} tiers créé(s), "
        f"{result.get('members_flagged', 0)} adhérent(s) marqué(s).",
        "success",
    )
    return redirect(url_for("orders.index"))
