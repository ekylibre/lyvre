from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required

from app.extensions import db
from app.models import CustomerInvoice, CustomerInvoiceLine
from app.models.customer_invoice import (
    CUSTOMER_INVOICE_STATES,
    CUSTOMER_INVOICE_PAYMENT_STATES,
)
from app.services import external_config
from app.services.odoo_client import OdooConfigError
from app.services.odoo_invoice_sync import sync_customer_invoices
from app.utils.list_filters import (
    parse_sort, parse_month, apply_date_sort, apply_month_filter,
    sort_and_filter_context,
)

bp = Blueprint("customer_invoices", __name__, url_prefix="/customer-invoices")


def _odoo_configured():
    return external_config.is_configured("odoo")


@bp.route("/")
@login_required
def index():
    state = (request.args.get("state") or "").strip()
    payment_state = (request.args.get("payment_state") or "").strip()
    q = (request.args.get("q") or "").strip()
    sort = parse_sort(request.args.get("sort"))
    month_arg = request.args.get("month")
    month_tuple = parse_month(month_arg)

    query = CustomerInvoice.query
    if state:
        query = query.filter(CustomerInvoice.state == state)
    if payment_state:
        query = query.filter(CustomerInvoice.payment_state == payment_state)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(
            db.or_(
                db.func.lower(CustomerInvoice.name).like(like),
                db.func.lower(CustomerInvoice.partner_name).like(like),
                db.func.lower(CustomerInvoice.partner_email).like(like),
                db.func.lower(CustomerInvoice.ref).like(like),
            )
        )
    query = apply_month_filter(query, CustomerInvoice.invoice_date, month_tuple)
    query = apply_date_sort(query, CustomerInvoice.invoice_date, sort)
    invoices = query.order_by(CustomerInvoice.id.desc()).limit(500).all()
    return render_template(
        "customer_invoices/index.html",
        invoices=invoices,
        states=dict(CUSTOMER_INVOICE_STATES),
        payment_states=dict(CUSTOMER_INVOICE_PAYMENT_STATES),
        configured=_odoo_configured(),
        state=state, payment_state=payment_state, q=q,
        **sort_and_filter_context(sort, month_arg),
    )


@bp.route("/<int:invoice_id>")
@login_required
def detail(invoice_id):
    invoice = CustomerInvoice.query.get_or_404(invoice_id)
    lines = (
        CustomerInvoiceLine.query.filter_by(invoice_id=invoice.id)
        .order_by(CustomerInvoiceLine.id)
        .all()
    )
    return render_template(
        "customer_invoices/detail.html",
        invoice=invoice, lines=lines,
        states=dict(CUSTOMER_INVOICE_STATES),
        payment_states=dict(CUSTOMER_INVOICE_PAYMENT_STATES),
    )


@bp.route("/sync", methods=["POST"])
@login_required
def sync():
    try:
        result = sync_customer_invoices()
    except OdooConfigError as e:
        flash(str(e), "warning")
        return redirect(url_for("customer_invoices.index"))
    except Exception as e:
        current_app.logger.exception("Sync factures Odoo échouée")
        flash(f"Erreur de synchronisation : {e}", "danger")
        return redirect(url_for("customer_invoices.index"))

    flash(
        "Synchronisation OK — "
        f"{result['invoices_imported']} nouvelle(s), "
        f"{result['invoices_updated']} mise(s) à jour, "
        f"{result['lines_total']} ligne(s), "
        f"{result.get('entities_created', 0)} tiers créé(s).",
        "success",
    )
    return redirect(url_for("customer_invoices.index"))
