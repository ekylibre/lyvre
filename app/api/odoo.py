"""Odoo : commandes du point de vente, factures clients (listes, fiches, synchronisations
synchrones) et import CSV de lignes de factures par lots."""
from datetime import date, datetime

from flask import current_app, jsonify, request, url_for
from markupsafe import Markup

from app.extensions import db
from app.models import CustomerInvoice, CustomerInvoiceLine, OdooImportLine, Order, OrderLine, OrderPayment
from app.models.customer_invoice import CUSTOMER_INVOICE_PAYMENT_STATES, CUSTOMER_INVOICE_STATES
from app.models.order import POS_ORDER_STATES
from app.services import external_config
from app.services.odoo_client import OdooConfigError
from app.services.odoo_importer import import_odoo_csv
from app.services.odoo_invoice_sync import sync_customer_invoices
from app.services.odoo_pos_sync import sync_pos_orders
from app.utils.list_filters import apply_date_sort, apply_month_filter, month_options_for_fy, parse_month, parse_sort

from . import ApiError, bp, get_or_404, invalid, notice

LIMIT = 500


def _iso(value):
    return value.isoformat() if value else None


def _odoo():
    return {"available": external_config.is_available("odoo"), "message": external_config.unavailable_message("odoo")}


def _options(labels: dict):
    return [{"value": k, "label": v} for k, v in labels.items()]


def _sync(run, success):
    """Synchronisation Odoo synchrone : avertissement si non configurée, message d'erreur sinon."""
    message = external_config.unavailable_message("odoo")
    if message:
        raise ApiError("conflict", message, status=409)
    try:
        result = run()
    except OdooConfigError as exc:
        raise ApiError("conflict", str(exc), status=409) from None
    except Exception as exc:  # erreur réseau ou Odoo : message lisible, détail au journal
        current_app.logger.exception("Synchronisation Odoo échouée")
        raise ApiError("sync_failed", f"Erreur de synchronisation : {exc}", status=502) from None
    return jsonify(result=result, notices=[notice(success(result))])


# ------------------------------------------------------------------ commandes POS


@bp.route("/orders")
def orders_list():
    query = apply_month_filter(Order.query, Order.date_order, parse_month(request.args.get("month")))
    query = apply_date_sort(query, Order.date_order, parse_sort(request.args.get("sort")))
    orders = query.order_by(Order.id.desc()).limit(LIMIT).all()
    states = dict(POS_ORDER_STATES)
    return jsonify(items=[{
        "id": o.id, "reference": o.name or o.pos_reference or str(o.odoo_id), "date": _iso(o.date_order),
        "session": o.session_name, "partner": o.partner_name, "total_cents": o.amount_total_cents,
        "tax_cents": o.amount_tax_cents, "paid_cents": o.amount_paid_cents,
        "lines": o.lines.count(), "payments": o.payments.count(),
        "state": o.state, "state_label": states.get(o.state, o.state or "—"),
    } for o in orders], meta={"months": month_options_for_fy(), "odoo": _odoo(), "limit": LIMIT})


@bp.route("/orders/<int:order_id>")
def orders_detail(order_id):
    o = get_or_404(Order, order_id, "Commande introuvable.")
    lines = OrderLine.query.filter_by(order_id=o.id).order_by(OrderLine.id).all()
    payments = (OrderPayment.query.filter_by(order_id=o.id)
                .order_by(OrderPayment.payment_date.asc().nullsfirst(), OrderPayment.id).all())
    return jsonify(item={
        "id": o.id, "reference": o.name or f"POS #{o.odoo_id}", "date": _iso(o.date_order), "session": o.session_name,
        "partner": o.partner_name, "total_cents": o.amount_total_cents, "tax_cents": o.amount_tax_cents,
        "paid_cents": o.amount_paid_cents, "return_cents": o.amount_return_cents,
        "state": o.state, "state_label": dict(POS_ORDER_STATES).get(o.state, o.state or "—"),
    }, lines=[{
        "id": l.id, "product": l.full_product_name or l.product_name or str(l.product_id or ""), "qty": l.qty,
        "unit_cents": l.price_unit_cents, "discount": l.discount, "subtotal_cents": l.price_subtotal_cents,
        "total_cents": l.price_subtotal_incl_cents,
    } for l in lines], payments=[{
        "id": p.id, "date": _iso(p.payment_date), "method": p.payment_method_name,
        "reference": p.transaction_id or p.name or "", "card": p.card_type or "", "amount_cents": p.amount_cents,
    } for p in payments])


@bp.route("/orders/sync", methods=["POST"])
def orders_sync():
    return _sync(sync_pos_orders, lambda r: (
        f"Synchronisation OK — {r['orders_imported']} nouvelle(s), {r['orders_updated']} mise(s) à jour, "
        f"{r['lines_total']} ligne(s), {r['payments_total']} paiement(s), {r.get('entities_created', 0)} tiers "
        f"créé(s), {r.get('members_flagged', 0)} adhérent(s) marqué(s)."))


# ------------------------------------------------------------------ factures clients


def _invoice_row(inv: CustomerInvoice) -> dict:
    return {
        "id": inv.id, "number": inv.name or str(inv.odoo_id), "ref": inv.ref, "date": _iso(inv.invoice_date),
        "due_date": _iso(inv.invoice_date_due), "partner": inv.partner_name or inv.partner_email,
        "entity_id": inv.entity_id, "untaxed_cents": inv.amount_untaxed_cents, "tax_cents": inv.amount_tax_cents,
        "total_cents": inv.amount_total_cents, "residual_cents": inv.amount_residual_cents,
        "state": inv.state, "state_label": dict(CUSTOMER_INVOICE_STATES).get(inv.state, inv.state or "—"),
        "payment_state": inv.payment_state,
        "payment_state_label": dict(CUSTOMER_INVOICE_PAYMENT_STATES).get(inv.payment_state, inv.payment_state or "—"),
    }


@bp.route("/customer-invoices")
def customer_invoices_list():
    args = request.args
    query = CustomerInvoice.query
    if args.get("state"):
        query = query.filter(CustomerInvoice.state == args["state"])
    if args.get("payment_state"):
        query = query.filter(CustomerInvoice.payment_state == args["payment_state"])
    q = (args.get("q") or "").strip()
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(db.or_(*(db.func.lower(col).like(like) for col in (
            CustomerInvoice.name, CustomerInvoice.partner_name, CustomerInvoice.partner_email, CustomerInvoice.ref))))
    query = apply_month_filter(query, CustomerInvoice.invoice_date, parse_month(args.get("month")))
    query = apply_date_sort(query, CustomerInvoice.invoice_date, parse_sort(args.get("sort")))
    invoices = query.order_by(CustomerInvoice.id.desc()).limit(LIMIT).all()
    return jsonify(items=[_invoice_row(inv) for inv in invoices], meta={
        "states": _options(dict(CUSTOMER_INVOICE_STATES)),
        "payment_states": _options(dict(CUSTOMER_INVOICE_PAYMENT_STATES)),
        "months": month_options_for_fy(), "odoo": _odoo(), "limit": LIMIT,
    })


@bp.route("/customer-invoices/<int:invoice_id>")
def customer_invoices_detail(invoice_id):
    inv = get_or_404(CustomerInvoice, invoice_id, "Facture introuvable.")
    lines = CustomerInvoiceLine.query.filter_by(invoice_id=inv.id).order_by(CustomerInvoiceLine.id).all()
    return jsonify(item={
        **_invoice_row(inv), "origin": inv.invoice_origin, "currency": inv.currency, "journal": inv.journal_name,
        "partner_email": inv.partner_email,
        # Note Odoo en HTML : texte seul (pas de HTML venu d'Odoo dans la page).
        "narration": Markup(inv.narration).striptags() if inv.narration else None,
    }, lines=[{
        "id": l.id, "product": l.product_name, "description": l.description or "", "qty": l.qty,
        "unit_cents": l.price_unit_cents, "discount": l.discount, "subtotal_cents": l.price_subtotal_cents,
        "total_cents": l.price_total_cents,
    } for l in lines])


@bp.route("/customer-invoices/sync", methods=["POST"])
def customer_invoices_sync():
    return _sync(sync_customer_invoices, lambda r: (
        f"Synchronisation OK — {r['invoices_imported']} nouvelle(s), {r['invoices_updated']} mise(s) à jour, "
        f"{r['lines_total']} ligne(s), {r.get('entities_created', 0)} tiers créé(s)."))


# ------------------------------------------------------------------ import Odoo par lots


def _jsonable(value):
    return value.isoformat() if isinstance(value, (date, datetime)) else value


@bp.route("/imports/odoo")
def odoo_batches():
    batches = (db.session.query(OdooImportLine.import_batch, db.func.count(OdooImportLine.id))
               .group_by(OdooImportLine.import_batch).order_by(OdooImportLine.import_batch.desc()).all())
    return jsonify(items=[{"name": name, "lines": count,
                           "url": url_for("imports.odoo_batch", batch_name=name)} for name, count in batches])


@bp.route("/imports/odoo", methods=["POST"])
def odoo_import():
    file = request.files.get("csv_file")
    if file is None or not file.filename:
        raise invalid("Veuillez choisir un fichier CSV.", "csv_file")
    batch = (request.form.get("batch_name") or "").strip()[:50] or f"odoo-{datetime.now():%Y%m%d-%H%M%S}"
    try:
        result = import_odoo_csv(file.stream, batch)
    except Exception as exc:  # CSV illisible, colonnes manquantes
        db.session.rollback()
        raise invalid(f"Erreur lors de l'import Odoo : {exc}", "csv_file") from None
    level = "warning" if result["errors"] else "success"
    return jsonify(result={
        "batch": batch, "imported": result["imported"], "errors": result["errors"],
        "preview": [{k: _jsonable(v) for k, v in row.items()} for row in result.get("preview", [])],
        "url": url_for("imports.odoo_batch", batch_name=batch),
    }, notices=[notice(f"{result['imported']} ligne(s) importée(s) dans le lot « {batch} ».", level)])


@bp.route("/imports/odoo/batches/<path:batch_name>")
def odoo_batch_lines(batch_name):
    query = OdooImportLine.query.filter_by(import_batch=batch_name)
    query = apply_month_filter(query, OdooImportLine.invoice_date, parse_month(request.args.get("month")))
    query = apply_date_sort(query, OdooImportLine.invoice_date, parse_sort(request.args.get("sort")))
    return jsonify(items=[{
        "id": l.id, "invoice_number": l.invoice_number, "date": _iso(l.invoice_date), "partner": l.partner_name,
        "product": l.product_name, "untaxed_cents": l.amount_ht_cents, "tax_cents": l.tax_amount_cents,
        "total_cents": l.amount_ttc_cents, "account_code": l.account_code,
        "entry_url": url_for("entries.detail", entry_id=l.journal_entry_id) if l.journal_entry_id else None,
    } for l in query.order_by(OdooImportLine.id).all()], meta={"batch": batch_name, "months": month_options_for_fy()})
