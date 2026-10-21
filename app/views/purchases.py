from datetime import date

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import login_required
from markupsafe import escape

from app.decorators import admin_required
from app.extensions import db
from app.frontend import is_htmx
from app.models import Account, Entity, Purchase, SyncJob
from app.models.sync_job import SYNC_KIND_QONTO_INVOICES
from app.services import catalog, external_config, purchase_posting, purchase_sync
from app.services.ledger import LedgerError
from app.services.purchase_posting import STATE_LABELS, purchase_state
from app.services.purchase_sync import STATUS_LABELS
from app.utils.list_filters import (
    apply_date_sort, apply_month_filter, parse_month, parse_sort, sort_and_filter_context,
)

bp = Blueprint("purchases", __name__, url_prefix="/purchases")


@bp.route("/")
@login_required
def index():
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()
    state = (request.args.get("state") or "").strip()
    entity_id = request.args.get("entity_id", type=int)
    unpaid = request.args.get("unpaid") == "1"
    no_supplier = request.args.get("no_supplier") == "1"
    show_hidden = request.args.get("hidden") == "1"
    sort = parse_sort(request.args.get("sort"))
    month_arg = request.args.get("month")

    query = Purchase.query
    if not show_hidden:
        query = query.filter(Purchase.is_hidden.is_(False))
    if status:
        query = query.filter(Purchase.qonto_status == status)
    if entity_id:
        query = query.filter(Purchase.entity_id == entity_id)
    if unpaid:
        query = query.filter(db.or_(Purchase.qonto_status.is_(None), Purchase.qonto_status != "paid"))
    if no_supplier:
        query = query.filter(Purchase.entity_id.is_(None))
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(db.or_(db.func.lower(Purchase.invoice_number).like(like),
                                    db.func.lower(Purchase.supplier_name).like(like)))
    query = apply_month_filter(query, Purchase.issue_date, parse_month(month_arg))
    query = apply_date_sort(query, Purchase.issue_date, sort)
    purchases = query.order_by(Purchase.id.desc()).limit(500).all()
    states = {p.id: purchase_state(p) for p in purchases}
    if state in STATE_LABELS:
        purchases = [p for p in purchases if states[p.id].code == state]

    suppliers = (Entity.query.join(Purchase, Purchase.entity_id == Entity.id)
                 .distinct().order_by(Entity.name).all())
    return render_template(
        "purchases/index.html",
        purchases=purchases, states=states, suppliers=suppliers, status_labels=STATUS_LABELS,
        state_labels=STATE_LABELS, state=state,
        to_complete=purchase_posting.count_to_complete(),
        to_review=Purchase.query.filter(Purchase.review_reason.isnot(None)).count(),
        q=q, status=status, entity_id=entity_id, unpaid=unpaid, no_supplier=no_supplier,
        show_hidden=show_hidden,
        hidden_count=Purchase.query.filter(Purchase.is_hidden.is_(True)).count(),
        without_supplier=Purchase.query.filter(Purchase.entity_id.is_(None),
                                               Purchase.is_hidden.is_(False)).count(),
        cursor=purchase_sync.cursor_row(), sync_from=purchase_sync.sync_from_date(),
        job=purchase_sync.latest_job(),
        **sort_and_filter_context(sort, month_arg),
    )


@bp.route("/sync", methods=["POST"])
@login_required
def sync():
    message = external_config.unavailable_message("qonto")
    if message:
        if is_htmx():
            return f'<div id="purchase-sync-status" class="alert alert-warning small">{escape(message)}</div>'
        flash(message, "warning")
        return redirect(url_for("purchases.index"))
    job = purchase_sync.start_sync(current_app._get_current_object())
    if is_htmx():
        return render_template("purchases/_sync_status.html", job=job)
    flash("Synchronisation des factures Qonto lancée en arrière-plan.", "info")
    return redirect(url_for("purchases.index"))


@bp.route("/sync/<int:job_id>")
@login_required
def sync_status(job_id):
    job = db.session.get(SyncJob, job_id)
    if job is None or job.kind != SYNC_KIND_QONTO_INVOICES:
        abort(404)
    return render_template("purchases/_sync_status.html", job=job)


@bp.route("/sync/settings", methods=["POST"])
@login_required
@admin_required
def sync_settings():
    try:
        sync_from = date.fromisoformat(request.form.get("sync_from") or "")
    except ValueError:
        flash("Date de début invalide.", "danger")
        return redirect(url_for("purchases.index"))
    purchase_sync.set_sync_from(sync_from)
    flash(f"Factures Qonto synchronisées à partir du {sync_from.strftime('%d/%m/%Y')}.", "success")
    return redirect(url_for("purchases.index"))


def _rows(form):
    """Lignes du formulaire de la fiche (champs répétés)."""
    keys = ("product_id", "account_code", "label", "untaxed", "vat_rate", "vat")
    columns = [form.getlist(f"{key}[]") for key in keys]
    return [dict(zip(keys, values)) for values in zip(*columns)]


@bp.route("/<int:purchase_id>")
@login_required
def detail(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)
    fy = purchase_posting.fiscal_year_for(purchase.issue_date)
    return render_template(
        "purchases/detail.html", purchase=purchase, state=purchase_state(purchase),
        fiscal_year=fy, status_labels=STATUS_LABELS, products=catalog.purchase_products(),
        charge_accounts=(Account.query.filter(Account.code.like("6%"), Account.is_header.is_(False))
                         .order_by(Account.code).all()),
    )


@bp.route("/<int:purchase_id>/lines", methods=["POST"])
@login_required
def save_lines(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)
    try:
        outcome = purchase_posting.save_lines(purchase, _rows(request.form))
    except LedgerError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("purchases.detail", purchase_id=purchase.id))
    if outcome["posted"]:
        flash("Lignes enregistrées, facture comptabilisée.", "success")
    else:
        flash("Lignes enregistrées.", "success")
    for error in outcome["errors"]:
        flash(error, "danger")
    return redirect(url_for("purchases.detail", purchase_id=purchase.id))


@bp.route("/<int:purchase_id>/post", methods=["POST"])
@login_required
def post(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)
    outcome = purchase_posting.post_ready([purchase])
    if outcome["posted"]:
        flash("Facture comptabilisée.", "success")
    for error in outcome["errors"] or ([] if outcome["posted"] else
                                       [" ".join(purchase_state(purchase).reasons)]):
        flash(error, "danger")
    return redirect(url_for("purchases.detail", purchase_id=purchase.id))


@bp.route("/<int:purchase_id>/unpost", methods=["POST"])
@login_required
def unpost(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)
    try:
        purchase_posting.unpost(purchase)
        flash("Comptabilisation annulée : l'écriture d'achat est supprimée.", "success")
    except LedgerError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("purchases.detail", purchase_id=purchase.id))


@bp.route("/post-ready", methods=["POST"])
@login_required
def post_ready():
    outcome = purchase_posting.post_ready(purchase_posting.ready_purchases())
    flash(f"{outcome['posted']} facture(s) comptabilisée(s).", "success")
    for error in outcome["errors"][:10]:
        flash(error, "danger")
    return redirect(url_for("purchases.index"))
