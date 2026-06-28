"""Agrégats internes (économique + social), calculés en direct.

Source de vérité = tables existantes (orders, helloasso_*, work_times, entities).
Aucune donnée n'est stockée : tout est recalculé pour la période demandée, ce qui
garantit la cohérence avec la compta et les autres écrans.
"""
from datetime import timedelta

from app.extensions import db
from app.models import (
    Order, OrderLine, HelloAssoOrder, HelloAssoItem,
    WorkTime, TaskType, Entity,
)

POS_REVENUE_STATES = ("paid", "done", "invoiced")
MEMBERSHIP_VALID_DAYS = 365

# Motif "adhésion" sur les lignes POS Odoo (même logique que le dashboard).
_ADH_LIKE = "%adh%sion%"


def economic(period) -> dict:
    pos = db.session.query(
        db.func.coalesce(db.func.sum(Order.amount_total_cents), 0)
    ).filter(
        Order.date_order >= period.start,
        Order.date_order < period.end,
        Order.state.in_(POS_REVENUE_STATES),
    ).scalar() or 0

    def _ha_items_sum(item_type):
        return db.session.query(
            db.func.coalesce(db.func.sum(HelloAssoItem.amount_cents), 0)
        ).join(HelloAssoOrder, HelloAssoOrder.id == HelloAssoItem.order_id).filter(
            HelloAssoItem.type == item_type,
            HelloAssoOrder.date >= period.start,
            HelloAssoOrder.date < period.end,
        ).scalar() or 0

    return {
        "econ.pos_revenue_cents": int(pos),
        "econ.donations_cents": int(_ha_items_sum("Donation")),
        "econ.memberships_cents": int(_ha_items_sum("Membership")),
    }


def _membership_entity_ids(start, end):
    """Entités ayant un événement d'adhésion (HelloAsso ou POS) dans [start, end)."""
    ha = {
        row[0] for row in
        db.session.query(HelloAssoOrder.entity_id)
        .join(HelloAssoItem, HelloAssoItem.order_id == HelloAssoOrder.id)
        .filter(HelloAssoItem.type == "Membership")
        .filter(HelloAssoOrder.entity_id.isnot(None))
        .filter(HelloAssoOrder.date >= start, HelloAssoOrder.date < end)
        .distinct().all()
    }
    pos = {
        row[0] for row in
        db.session.query(Order.entity_id)
        .join(OrderLine, OrderLine.order_id == Order.id)
        .filter(Order.entity_id.isnot(None))
        .filter(db.or_(
            db.func.lower(OrderLine.full_product_name).like(_ADH_LIKE),
            db.func.lower(OrderLine.product_name).like(_ADH_LIKE),
        ))
        .filter(Order.date_order >= start, Order.date_order < end)
        .distinct().all()
    }
    return ha | pos


def social(period) -> dict:
    active_volunteers = db.session.query(
        db.func.count(db.distinct(WorkTime.entity_id))
    ).filter(
        WorkTime.work_date >= period.start, WorkTime.work_date < period.end
    ).scalar() or 0

    hours = db.session.query(
        db.func.coalesce(db.func.sum(WorkTime.hours), 0)
    ).filter(
        WorkTime.work_date >= period.start, WorkTime.work_date < period.end
    ).scalar() or 0

    value_cents = db.session.query(
        db.func.coalesce(
            db.func.sum(WorkTime.hours * TaskType.hourly_rate_cents), 0
        )
    ).join(TaskType, TaskType.id == WorkTime.task_type_id).filter(
        WorkTime.work_date >= period.start, WorkTime.work_date < period.end
    ).scalar() or 0

    new_members = len(_membership_entity_ids(period.start, period.end))

    members_count = db.session.query(
        db.func.count(Entity.id)
    ).filter(Entity.is_member.is_(True)).scalar() or 0

    # Taux d'adhésions à jour : membres avec un événement d'adhésion dans les 365j
    # précédant la fin de période, rapporté au total des membres.
    window_start = period.end - timedelta(days=MEMBERSHIP_VALID_DAYS)
    up_to_date = len(_membership_entity_ids(window_start, period.end))
    renewal_rate = (up_to_date / members_count) if members_count else None

    return {
        "social.active_volunteers": int(active_volunteers),
        "social.volunteer_hours": float(hours),
        "social.volunteer_value_cents": int(round(float(value_cents))),
        "social.new_members": int(new_members),
        "social.members_count": int(members_count),
        "social.renewal_rate": renewal_rate,
    }
