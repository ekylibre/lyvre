from flask import Blueprint, render_template, redirect, url_for, flash, current_app, abort
from flask_login import login_required

from app.models import Payout, Payment, SyncJob
from app.models.payout import PAYOUT_STATUSES
from app.models.payment import PAYMENT_STATUSES
from app.services import stancer_async

bp = Blueprint("payouts", __name__, url_prefix="/payouts")


@bp.route("/")
@login_required
def index():
    payouts = Payout.query.order_by(Payout.date_payout.desc().nullslast()).all()
    has_key = bool(current_app.config.get("STANCER_SECRET_KEY"))
    last_job = stancer_async.latest_payouts_job()
    return render_template(
        "payouts/index.html",
        payouts=payouts,
        statuses=dict(PAYOUT_STATUSES),
        has_key=has_key,
        last_job=last_job,
    )


@bp.route("/<int:payout_id>")
@login_required
def detail(payout_id):
    payout = Payout.query.get_or_404(payout_id)
    payments = (
        Payment.query.filter_by(payout_id=payout.id)
        .order_by(Payment.date_payment.desc().nullslast(), Payment.created_at.desc())
        .all()
    )
    last_job = stancer_async.latest_job_for_payout(payout.id)
    return render_template(
        "payouts/detail.html",
        payout=payout,
        payments=payments,
        payout_statuses=dict(PAYOUT_STATUSES),
        payment_statuses=dict(PAYMENT_STATUSES),
        last_job=last_job,
    )


@bp.route("/sync", methods=["POST"])
@login_required
def sync():
    """Démarre la sync globale en arrière-plan et renvoie un fragment HTMX
    qui s'auto-rafraîchit. En non-HTMX, redirige vers la liste."""
    job = stancer_async.start_sync_payouts(current_app._get_current_object())
    if request_is_htmx():
        return render_template("payouts/_sync_status.html", job=job)
    flash("Synchronisation lancée en arrière-plan.", "info")
    return redirect(url_for("payouts.index"))


@bp.route("/<int:payout_id>/sync-payments", methods=["POST"])
@login_required
def sync_payments_route(payout_id):
    payout = Payout.query.get_or_404(payout_id)
    job = stancer_async.start_sync_payments_for_payout(
        current_app._get_current_object(), payout.id,
    )
    if request_is_htmx():
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


def request_is_htmx():
    from flask import request
    return request.headers.get("HX-Request") == "true"
