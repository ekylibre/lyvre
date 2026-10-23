"""Achats › Abonnements (lot S6) : contrats récurrents, échéances attendues (facture et prélèvement
rattachés, manquantes signalées), coût mensuel et annuel, rappels de préavis."""
from contextlib import contextmanager

from flask import jsonify

from app.extensions import db
from app.models import BankAccount, Entity, Subscription, SubscriptionPeriod
from app.models.subscription import CATEGORIES, PERIOD_STATUSES
from app.services import catalog, subscriptions
from app.services.sale_entry import SaleError

from . import ApiError, bp, get_or_404, invalid, json_body, notice

FREQUENCY_LABELS = {"monthly": "Mensuel", "quarterly": "Trimestriel", "yearly": "Annuel"}


@contextmanager
def _errors():
    try:
        yield
    except SaleError as exc:
        db.session.rollback()
        if exc.status == 422:
            raise invalid(exc.message, exc.field) from None
        raise ApiError("conflict", exc.message, status=exc.status) from None


def _iso(value):
    return value.isoformat() if value else None


def _period(p: SubscriptionPeriod) -> dict:
    return {"id": p.id, "due_date": _iso(p.due_date), "expected_cents": p.expected_cents, "status": p.status,
            "status_label": PERIOD_STATUSES[p.status],
            "purchase": {"id": p.purchase_id, "number": p.purchase.invoice_number, "total_cents": p.purchase.total_cents,
                         "issue_date": _iso(p.purchase.issue_date)} if p.purchase else None,
            "transaction": {"id": p.bank_transaction_id, "label": p.bank_transaction.label,
                            "amount_cents": p.bank_transaction.amount_cents, "date": _iso(p.bank_transaction.transaction_date)}
            if p.bank_transaction else None}


def subscription_payload(s: Subscription, detail: bool = False) -> dict:
    last = s.periods[0] if s.periods else None
    row = {"id": s.id, "label": s.label, "category": s.category, "category_label": CATEGORIES[s.category],
           "supplier": {"id": s.entity_id, "name": s.entity.name}, "amount_cents": s.amount_cents,
           "amount_fixed": s.amount_fixed, "frequency": s.frequency, "frequency_label": FREQUENCY_LABELS[s.frequency],
           "due_day": s.due_day, "monthly_cents": subscriptions.monthly_cents(s), "start_date": _iso(s.start_date),
           "end_date": _iso(s.end_date), "renewal_date": _iso(s.renewal_date), "notice_days": s.notice_days,
           "next_renewal": _iso(subscriptions.next_renewal(s)), "notice_deadline": _iso(subscriptions.notice_deadline(s)),
           "notice_alert": subscriptions.notice_alert(s), "active": s.active, "notes": s.notes or "",
           "product_id": str(s.product_id or ""), "bank_account_id": str(s.bank_account_id or ""),
           "last_period": _period(last) if last else None,
           "missing": sum(1 for p in s.periods if p.status == "missing")}
    if detail:
        row["periods"] = [_period(p) for p in s.periods]
    return row


@bp.route("/subscriptions")
def subscriptions_list():
    """Échéances arrivées créées et rattachées (idempotent), puis liste et totaux."""
    subscriptions.refresh()
    rows = Subscription.query.order_by(Subscription.active.desc(), Subscription.category, Subscription.label).all()
    return jsonify(items=[subscription_payload(s) for s in rows], meta={
        "summary": subscriptions.summary(rows),
        "categories": [{"value": k, "label": v} for k, v in CATEGORIES.items()],
        "frequencies": [{"value": k, "label": v} for k, v in FREQUENCY_LABELS.items()],
        "suppliers": [{"value": str(e.id), "label": e.name} for e in Entity.query.order_by(Entity.name)],
        "products": [{"value": str(p.id), "label": p.name} for p in catalog.purchase_products()],
        "bank_accounts": [{"value": str(b.id), "label": b.label} for b in BankAccount.query.order_by(BankAccount.label)]})


@bp.route("/subscriptions", methods=["POST"])
def subscriptions_create():
    with _errors():
        sub = subscriptions.create(json_body())
    return jsonify(item=subscription_payload(sub, True), notices=[notice("Abonnement enregistré.")]), 201


@bp.route("/subscriptions/<int:sub_id>")
def subscriptions_detail(sub_id):
    sub = get_or_404(Subscription, sub_id, "Abonnement introuvable.")
    subscriptions.refresh([sub])
    return jsonify(item=subscription_payload(sub, True))


@bp.route("/subscriptions/<int:sub_id>", methods=["PATCH"])
def subscriptions_update(sub_id):
    sub = get_or_404(Subscription, sub_id, "Abonnement introuvable.")
    with _errors():
        subscriptions.update(sub, json_body())
    return jsonify(item=subscription_payload(sub, True), notices=[notice("Abonnement enregistré.")])


@bp.route("/subscriptions/<int:sub_id>", methods=["DELETE"])
def subscriptions_delete(sub_id):
    sub = get_or_404(Subscription, sub_id, "Abonnement introuvable.")
    db.session.delete(sub)
    db.session.commit()
    return jsonify(notices=[notice("Abonnement supprimé (les factures d'achat restent).")])


@bp.route("/subscription-periods/<int:period_id>/candidates")
def subscription_period_candidates(period_id):
    period = get_or_404(SubscriptionPeriod, period_id, "Échéance introuvable.")
    found = subscriptions.candidates(period)
    return jsonify(
        purchases=[{"value": str(p.id), "label": f"{p.invoice_number or 'sans numéro'} du {p.issue_date:%d/%m/%Y} — "
                    f"{p.total_cents / 100:.2f} €".replace(".", ",")} for p in found["purchases"]],
        debits=[{"value": str(t.id), "label": f"{t.transaction_date:%d/%m/%Y} — {t.label or ''} — "
                 f"{-t.amount_cents / 100:.2f} €".replace(".", ",")} for t in found["debits"]])


@bp.route("/subscription-periods/<int:period_id>/link", methods=["POST"])
def subscription_period_link(period_id):
    """`{purchase_id?, bank_transaction_id?}` : rattachement à la main."""
    period = get_or_404(SubscriptionPeriod, period_id, "Échéance introuvable.")
    data = json_body()
    purchase_id = int(data["purchase_id"]) if str(data.get("purchase_id") or "").isdigit() else None
    txn_id = int(data["bank_transaction_id"]) if str(data.get("bank_transaction_id") or "").isdigit() else None
    if purchase_id is None and txn_id is None:
        raise invalid("Choisissez une facture ou un prélèvement.")
    with _errors():
        subscriptions.link(period, purchase_id, txn_id)
    return jsonify(item=subscription_payload(period.subscription, True), notices=[notice("Échéance rattachée.")])


@bp.route("/subscription-periods/<int:period_id>/skip", methods=["POST"])
def subscription_period_skip(period_id):
    """`{skipped}` : échéance ignorée (pas de facture attendue), ou de nouveau attendue."""
    period = get_or_404(SubscriptionPeriod, period_id, "Échéance introuvable.")
    subscriptions.skip(period, bool(json_body().get("skipped", True)))
    return jsonify(item=subscription_payload(period.subscription, True), notices=[notice("Échéance mise à jour.")])
