"""Versements Stancer et leurs paiements ; synchronisations en arrière-plan."""
from flask import current_app, jsonify, request

from app.models import Payment, Payout
from app.models.payment import PAYMENT_STATUSES
from app.models.payout import PAYOUT_STATUSES
from app.services import external_config, stancer_async
from app.utils.list_filters import (
    apply_date_sort, apply_month_filter, month_options_for_fy, parse_month, parse_sort,
)

from . import ApiError, bp, get_or_404
from .session import job_payload


def _iso(value):
    return value.isoformat() if value else None


def payout_payload(p: Payout, statuses=dict(PAYOUT_STATUSES)) -> dict:
    bt = p.bank_transaction
    return {"id": p.id, "stancer_id": p.stancer_id, "date_payout": _iso(p.date_payout),
            "date_bank": _iso(p.date_bank), "description": p.statement_description or p.description or "",
            "amount_cents": p.amount_cents, "fees_cents": p.fees_cents or 0, "currency": p.currency,
            "status": p.status, "status_label": statuses.get(p.status, p.status),
            "payments": p.payments.count(), "imported_at": _iso(p.imported_at),
            "bank_transaction": ({"date": bt.transaction_date.isoformat(), "amount_cents": bt.amount_cents,
                                  "label": bt.label or ""} if bt else None)}


def _stancer():
    return {"available": external_config.is_available("stancer"),
            "message": external_config.unavailable_message("stancer")}


@bp.route("/payouts")
def payouts_list():
    query = apply_month_filter(Payout.query, Payout.date_payout, parse_month(request.args.get("month")))
    payouts = apply_date_sort(query, Payout.date_payout, parse_sort(request.args.get("sort"))).all()
    job = stancer_async.latest_payouts_job()
    return jsonify(items=[payout_payload(p) for p in payouts], meta={
        "months": month_options_for_fy(), "stancer": _stancer(), "job": job_payload(job) if job else None})


@bp.route("/payouts/<int:payout_id>")
def payouts_detail(payout_id):
    payout = get_or_404(Payout, payout_id, "Versement introuvable.")
    query = Payment.query.filter_by(payout_id=payout.id)
    query = apply_month_filter(query, Payment.date_payment, parse_month(request.args.get("month")))
    payments = apply_date_sort(query, Payment.date_payment, parse_sort(request.args.get("sort"))) \
        .order_by(Payment.created_at.desc()).all()
    statuses = dict(PAYMENT_STATUSES)
    job = stancer_async.latest_job_for_payout(payout.id)
    return jsonify(item=payout_payload(payout), payments=[{
        "id": p.id, "stancer_id": p.stancer_id, "date": _iso(p.date_payment), "method": p.method,
        "customer": p.customer_name or p.customer_email or "", "description": p.description or "",
        "amount_cents": p.amount_cents, "status": p.status, "status_label": statuses.get(p.status, p.status),
    } for p in payments], meta={"months": month_options_for_fy(), "stancer": _stancer(),
                                "job": job_payload(job) if job else None})


def _require_stancer():
    message = external_config.unavailable_message("stancer")
    if message:
        raise ApiError("conflict", message, status=409)


@bp.route("/payouts/sync", methods=["POST"])
def payouts_sync():
    _require_stancer()
    return jsonify(job=job_payload(stancer_async.start_sync_payouts(current_app._get_current_object())))


@bp.route("/payouts/<int:payout_id>/sync-payments", methods=["POST"])
def payouts_sync_payments(payout_id):
    payout = get_or_404(Payout, payout_id, "Versement introuvable.")
    _require_stancer()
    return jsonify(job=job_payload(stancer_async.start_sync_payments_for_payout(
        current_app._get_current_object(), payout.id)))
