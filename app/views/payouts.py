from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, abort
from markupsafe import escape
from app.frontend import is_htmx
from flask_login import login_required

from app.models import Payout, Payment, SyncJob
from app.models.payout import PAYOUT_STATUSES
from app.models.payment import PAYMENT_STATUSES
from app.services import external_config, stancer_async
from app.utils.list_filters import (
    parse_sort, parse_month, apply_date_sort, apply_month_filter,
    sort_and_filter_context,
)

bp = Blueprint("payouts", __name__, url_prefix="/payouts")


@bp.route("/")
@login_required
def index():
    sort = parse_sort(request.args.get("sort"))
    month_arg = request.args.get("month")
    month_tuple = parse_month(month_arg)

    query = Payout.query
    query = apply_month_filter(query, Payout.date_payout, month_tuple)
    query = apply_date_sort(query, Payout.date_payout, sort)
    payouts = query.all()
    has_key = external_config.is_available("stancer")
    last_job = stancer_async.latest_payouts_job()
    return render_template(
        "payouts/index.html",
        payouts=payouts,
        statuses=dict(PAYOUT_STATUSES),
        has_key=has_key,
        last_job=last_job,
        **sort_and_filter_context(sort, month_arg),
    )


@bp.route("/<int:payout_id>")
@login_required
def detail(payout_id):
    payout = Payout.query.get_or_404(payout_id)
    sort = parse_sort(request.args.get("sort"))
    month_arg = request.args.get("month")
    month_tuple = parse_month(month_arg)

    query = Payment.query.filter_by(payout_id=payout.id)
    query = apply_month_filter(query, Payment.date_payment, month_tuple)
    query = apply_date_sort(query, Payment.date_payment, sort)
    payments = query.order_by(Payment.created_at.desc()).all()
    last_job = stancer_async.latest_job_for_payout(payout.id)
    return render_template(
        "payouts/detail.html",
        payout=payout,
        payments=payments,
        payout_statuses=dict(PAYOUT_STATUSES),
        payment_statuses=dict(PAYMENT_STATUSES),
        last_job=last_job,
        **sort_and_filter_context(sort, month_arg),
    )


@bp.route("/sync", methods=["POST"])
@login_required
def sync():
    """Démarre la sync globale en arrière-plan et renvoie un fragment HTMX
    qui s'auto-rafraîchit. En non-HTMX, redirige vers la liste."""
    message = external_config.unavailable_message("stancer")
    if message:
        if is_htmx():
            return f'<div class="alert alert-warning small">{escape(message)}</div>'
        flash(message, "warning")
        return redirect(url_for("payouts.index"))
    job = stancer_async.start_sync_payouts(current_app._get_current_object())
    if is_htmx():
        return render_template("payouts/_sync_status.html", job=job)
    flash("Synchronisation lancée en arrière-plan.", "info")
    return redirect(url_for("payouts.index"))


@bp.route("/<int:payout_id>/sync-payments", methods=["POST"])
@login_required
def sync_payments_route(payout_id):
    payout = Payout.query.get_or_404(payout_id)
    message = external_config.unavailable_message("stancer")
    if message:
        if is_htmx():
            return f'<div class="alert alert-warning small">{escape(message)}</div>'
        flash(message, "warning")
        return redirect(url_for("payouts.detail", payout_id=payout.id))
    job = stancer_async.start_sync_payments_for_payout(
        current_app._get_current_object(), payout.id,
    )
    if is_htmx():
        return render_template("payouts/_sync_status.html", job=job)
    flash("Synchronisation des paiements lancée en arrière-plan.", "info")
    return redirect(url_for("payouts.detail", payout_id=payout.id))


@bp.route("/sync/status/<int:job_id>")
@login_required
def sync_status(job_id):
    """Endpoint de polling HTMX. Retourne le fragment d'état du job."""
    job = SyncJob.query.get(job_id)
    if job is None:
        abort(404)
    return render_template("payouts/_sync_status.html", job=job)
