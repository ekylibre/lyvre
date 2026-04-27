from flask import Blueprint, render_template, redirect, url_for, flash, current_app
from flask_login import login_required

from app.models import Order, OrderLine, OrderPayment
from app.models.order import POS_ORDER_STATES
from app.services.odoo_client import OdooConfigError
from app.services.odoo_pos_sync import sync_pos_orders

bp = Blueprint("orders", __name__, url_prefix="/orders")


def _odoo_configured():
    return all(current_app.config.get(k) for k in (
        "ODOO_URL", "ODOO_DB", "ODOO_USERNAME", "ODOO_API_KEY",
    ))


@bp.route("/")
@login_required
def index():
    orders = (
        Order.query.order_by(Order.date_order.desc().nullslast(), Order.id.desc())
        .limit(500)
        .all()
    )
    return render_template(
        "orders/index.html",
        orders=orders,
        states=dict(POS_ORDER_STATES),
        configured=_odoo_configured(),
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
        f"{result['lines_total']} ligne(s), {result['payments_total']} paiement(s).",
        "success",
    )
    return redirect(url_for("orders.index"))
