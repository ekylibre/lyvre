"""Tiers et adhérents : dates de dernière adhésion (HelloAsso, caisse Odoo), lignes
de la liste des adhérents (filtres, tri) partagées par l'API et les exports."""
from datetime import datetime

from app.extensions import db
from app.models import Entity, HelloAssoItem, HelloAssoOrder, Order, OrderLine
from app.services.membership_status import build_member_rows, sort_member_rows

VALID_SORT_BY = ("name", "birthday", "status")


def _pos_membership_line():
    """Ligne de caisse « Adhésion » (libellé produit)."""
    return db.or_(
        db.func.lower(OrderLine.full_product_name).like("%adh%sion%"),
        db.func.lower(OrderLine.product_name).like("%adh%sion%"),
    )


def last_membership_dates(entity_ids=None):
    """({entity_id: date HA}, {entity_id: date caisse}) des dernières adhésions.

    `entity_ids` None : tous les tiers (une requête agrégée par source, sans N+1).
    """
    if entity_ids is not None and not entity_ids:
        return {}, {}
    ha = (db.session.query(HelloAssoOrder.entity_id, db.func.max(HelloAssoOrder.date))
          .join(HelloAssoItem, HelloAssoItem.order_id == HelloAssoOrder.id)
          .filter(HelloAssoItem.type == "Membership", HelloAssoOrder.entity_id.isnot(None)))
    pos = (db.session.query(Order.entity_id, db.func.max(Order.date_order))
           .join(OrderLine, OrderLine.order_id == Order.id)
           .filter(Order.entity_id.isnot(None), _pos_membership_line()))
    if entity_ids is not None:
        ha = ha.filter(HelloAssoOrder.entity_id.in_(entity_ids))
        pos = pos.filter(Order.entity_id.in_(entity_ids))
    return (dict(ha.group_by(HelloAssoOrder.entity_id).all()),
            dict(pos.group_by(Order.entity_id).all()))


def parse_date(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_member_sort(args):
    sort_by = (args.get("sort_by") or "name").strip().lower()
    sort = (args.get("sort") or "asc").strip().lower()
    return (sort_by if sort_by in VALID_SORT_BY else "name"), (sort if sort in ("asc", "desc") else "asc")


def members_query(q):
    query = Entity.query.filter_by(entity_type="ADHERENT")
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(db.or_(db.func.lower(Entity.name).like(like),
                                    db.func.lower(Entity.email).like(like)))
    return query.order_by(Entity.name)


def filter_by_date_range(members, last_ha, last_pos, date_from, date_to):
    """Adhérents dont une date d'adhésion (HA ou caisse) tombe dans [date_from, date_to]."""
    if not date_from and not date_to:
        return members
    kept = []
    for m in members:
        for d in (x.date() for x in (last_ha.get(m.id), last_pos.get(m.id)) if x is not None):
            if (not date_from or d >= date_from) and (not date_to or d <= date_to):
                kept.append(m)
                break
    return kept


def member_rows(args):
    """Lignes filtrées et triées des adhérents (liste, exports, relances).

    `args` : mapping avec `q`, `date_from`, `date_to`, `sort_by`, `sort`.
    """
    q = (args.get("q") or "").strip()
    sort_by, sort = parse_member_sort(args)
    members = members_query(q).all()
    last_ha, last_pos = last_membership_dates([m.id for m in members])
    members = filter_by_date_range(members, last_ha, last_pos,
                                   parse_date(args.get("date_from")), parse_date(args.get("date_to")))
    return sort_member_rows(build_member_rows(members, last_ha, last_pos), sort_by, sort)
