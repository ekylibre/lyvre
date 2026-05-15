"""Synchronisation des commandes du Point de Vente Odoo.

Récupère via XML-RPC :
- pos.order        → table orders
- pos.order.line   → table order_lines
- pos.payment      → table order_payments
"""
import json
from datetime import datetime

from app.extensions import db
from app.models import Entity, Order, OrderLine, OrderPayment
from app.services.entity_resolver import entity_by_email, unique_entity_name
from app.services.odoo_client import from_app_config


PAGE_SIZE = 200


ORDER_FIELDS = [
    "id", "name", "pos_reference", "state",
    "session_id", "partner_id", "user_id", "company_id",
    "date_order", "amount_total", "amount_tax",
    "amount_paid", "amount_return", "currency_id",
    "lines", "payment_ids",
]
LINE_FIELDS = [
    "id", "order_id", "product_id", "full_product_name",
    "qty", "price_unit", "discount",
    "price_subtotal", "price_subtotal_incl", "tax_ids",
]
PAYMENT_FIELDS = [
    "id", "pos_order_id", "name", "payment_method_id",
    "amount", "payment_date", "card_type", "transaction_id", "currency_id",
]
PARTNER_FIELDS = ["id", "name", "email", "phone", "mobile"]


def _to_cents(value):
    if value is None:
        return 0
    return int(round(float(value) * 100))


def _to_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None


def _m2o_id(value):
    """Odoo many2one : [id, name] ou False."""
    if isinstance(value, (list, tuple)) and value:
        return value[0]
    return None


def _m2o_name(value):
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return value[1]
    return None


def _currency_code(value):
    name = _m2o_name(value)
    if not name:
        return "EUR"
    return name.upper()[:3]


def _upsert_order(item):
    odoo_id = item.get("id")
    if not odoo_id:
        return None, False
    existing = Order.query.filter_by(odoo_id=odoo_id).first()
    target = existing or Order(odoo_id=odoo_id)

    target.name = item.get("name") or None
    target.pos_reference = item.get("pos_reference") or None
    target.state = item.get("state") or None
    target.session_id = _m2o_id(item.get("session_id"))
    target.session_name = _m2o_name(item.get("session_id"))
    target.partner_id = _m2o_id(item.get("partner_id"))
    target.partner_name = _m2o_name(item.get("partner_id"))
    target.user_id = _m2o_id(item.get("user_id"))
    target.user_name = _m2o_name(item.get("user_id"))
    target.company_id = _m2o_id(item.get("company_id"))
    target.date_order = _to_datetime(item.get("date_order"))
    target.amount_total_cents = _to_cents(item.get("amount_total"))
    target.amount_tax_cents = _to_cents(item.get("amount_tax"))
    target.amount_paid_cents = _to_cents(item.get("amount_paid"))
    target.amount_return_cents = _to_cents(item.get("amount_return"))
    target.currency = _currency_code(item.get("currency_id"))
    target.note = item.get("note") or None
    target.raw_payload = json.dumps(item, ensure_ascii=False, default=str)
    target.imported_at = datetime.utcnow()

    is_new = existing is None
    if is_new:
        db.session.add(target)
    return target, is_new


def _upsert_line(item, order):
    odoo_id = item.get("id")
    if not odoo_id:
        return None, False
    existing = OrderLine.query.filter_by(odoo_id=odoo_id).first()
    target = existing or OrderLine(odoo_id=odoo_id)

    target.order_id = order.id
    target.product_id = _m2o_id(item.get("product_id"))
    target.product_name = _m2o_name(item.get("product_id"))
    target.full_product_name = item.get("full_product_name") or None
    target.qty = float(item.get("qty") or 0)
    target.price_unit_cents = _to_cents(item.get("price_unit"))
    target.discount = float(item.get("discount") or 0)
    target.price_subtotal_cents = _to_cents(item.get("price_subtotal"))
    target.price_subtotal_incl_cents = _to_cents(item.get("price_subtotal_incl"))
    tax_ids = item.get("tax_ids") or []
    target.tax_ids = ",".join(str(t) for t in tax_ids) if tax_ids else None
    target.note = item.get("note") or None
    target.raw_payload = json.dumps(item, ensure_ascii=False, default=str)
    target.imported_at = datetime.utcnow()

    is_new = existing is None
    if is_new:
        db.session.add(target)
    return target, is_new


def _upsert_payment(item, order):
    odoo_id = item.get("id")
    if not odoo_id:
        return None, False
    existing = OrderPayment.query.filter_by(odoo_id=odoo_id).first()
    target = existing or OrderPayment(odoo_id=odoo_id)

    target.order_id = order.id
    target.name = item.get("name") or None
    target.payment_method_id = _m2o_id(item.get("payment_method_id"))
    target.payment_method_name = _m2o_name(item.get("payment_method_id"))
    target.amount_cents = _to_cents(item.get("amount"))
    target.currency = _currency_code(item.get("currency_id"))
    target.payment_date = _to_datetime(item.get("payment_date"))
    target.card_type = item.get("card_type") or None
    target.transaction_id = item.get("transaction_id") or None
    target.raw_payload = json.dumps(item, ensure_ascii=False, default=str)
    target.imported_at = datetime.utcnow()

    is_new = existing is None
    if is_new:
        db.session.add(target)
    return target, is_new


def _chunked(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _fetch_partners(client, partner_ids):
    """Renvoie {partner_id: partner_data} depuis res.partner."""
    result = {}
    for chunk in _chunked(list(partner_ids), PAGE_SIZE):
        rows = client.search_read(
            "res.partner", domain=[["id", "in", chunk]],
            fields=PARTNER_FIELDS,
        )
        for row in rows:
            result[row["id"]] = row
    return result


def _resolve_partner_entity(partner, cache):
    """Crée/récupère l'Entity correspondant à un partner Odoo.

    Priorité : email. Sans email → pas de rattachement (risque de faux positif).
    Renvoie (entity, created, updated).
    """
    email = (partner.get("email") or "").strip() or None
    name = (partner.get("name") or "").strip() or None
    if not email:
        return None, False, False

    existing = entity_by_email(cache, email)
    if existing is not None:
        # On met juste à jour le name si le tiers existant n'a pas encore de nom propre
        # (cas extrême ; Entity.name est obligatoire donc rarement vide).
        return existing, False, False

    base_name = name or email
    ent = Entity(
        name=unique_entity_name(base_name, email),
        entity_type="CLIENT",
        email=email,
    )
    db.session.add(ent)
    db.session.flush()
    cache[email.lower()] = ent
    return ent, True, False


def sync_pos_orders(domain=None, limit=None, progress_cb=None):
    """Synchronise les commandes POS Odoo.

    `domain` : filtre Odoo additionnel (ex. [['date_order', '>=', '2026-01-01']]).
    `limit`  : nombre max de commandes (None = tout).
    `progress_cb(done, total, message)` : callback de progression.

    Retourne un dict de compteurs.
    """
    client = from_app_config()
    domain = list(domain or [])

    # 1. récupérer les pos.order paginés
    orders_imported = orders_updated = 0
    all_line_ids = []
    all_payment_ids = []
    order_by_id = {}

    offset = 0
    while True:
        batch_limit = PAGE_SIZE if limit is None else min(PAGE_SIZE, limit - offset)
        if batch_limit <= 0:
            break
        items = client.search_read(
            "pos.order", domain=domain, fields=ORDER_FIELDS,
            limit=batch_limit, offset=offset, order="id asc",
        )
        if not items:
            break
        for item in items:
            target, is_new = _upsert_order(item)
            if target is None:
                continue
            if is_new:
                orders_imported += 1
            else:
                orders_updated += 1
            all_line_ids.extend(item.get("lines") or [])
            all_payment_ids.extend(item.get("payment_ids") or [])
            order_by_id[item["id"]] = target
        db.session.flush()  # IDs locaux dispo pour FK
        if progress_cb:
            progress_cb(
                orders_imported + orders_updated, None,
                f"{orders_imported + orders_updated} commande(s) traitée(s)",
            )
        if len(items) < batch_limit:
            break
        offset += batch_limit
        if limit is not None and offset >= limit:
            break

    # 2. lignes — par lots d'IDs
    lines_imported = lines_updated = 0
    for chunk in _chunked(all_line_ids, PAGE_SIZE):
        items = client.search_read(
            "pos.order.line", domain=[["id", "in", chunk]],
            fields=LINE_FIELDS,
        )
        for item in items:
            order = order_by_id.get(_m2o_id(item.get("order_id")))
            if order is None:
                continue
            _, is_new = _upsert_line(item, order)
            if is_new:
                lines_imported += 1
            else:
                lines_updated += 1
        if progress_cb:
            progress_cb(
                lines_imported + lines_updated, len(all_line_ids),
                f"Lignes : {lines_imported + lines_updated}/{len(all_line_ids)}",
            )

    # 3. paiements — par lots d'IDs
    payments_imported = payments_updated = 0
    for chunk in _chunked(all_payment_ids, PAGE_SIZE):
        items = client.search_read(
            "pos.payment", domain=[["id", "in", chunk]],
            fields=PAYMENT_FIELDS,
        )
        for item in items:
            order = order_by_id.get(_m2o_id(item.get("pos_order_id")))
            if order is None:
                continue
            _, is_new = _upsert_payment(item, order)
            if is_new:
                payments_imported += 1
            else:
                payments_updated += 1
        if progress_cb:
            progress_cb(
                payments_imported + payments_updated, len(all_payment_ids),
                f"Paiements : {payments_imported + payments_updated}/{len(all_payment_ids)}",
            )

    # 4. partenaires (res.partner) → email + Entity
    partner_ids = {o.partner_id for o in order_by_id.values() if o.partner_id}
    entities_created = entities_updated = 0
    members_flagged = 0
    if partner_ids:
        partners = _fetch_partners(client, partner_ids)
        entity_cache = {}
        partner_to_entity = {}
        for pid, partner in partners.items():
            ent, created, updated = _resolve_partner_entity(partner, entity_cache)
            if created:
                entities_created += 1
            if updated:
                entities_updated += 1
            if ent is not None:
                partner_to_entity[pid] = ent.id
        # rattacher les Order à leur Entity et stocker l'email du partner
        for order in order_by_id.values():
            partner = partners.get(order.partner_id) if order.partner_id else None
            if partner:
                order.partner_email = (partner.get("email") or "").strip() or None
            order.entity_id = partner_to_entity.get(order.partner_id)
        if progress_cb:
            progress_cb(
                entities_created + entities_updated, len(partner_ids),
                f"Tiers : {entities_created} créé(s), {entities_updated} maj",
            )

    # 5. is_member : tout tiers avec une commande POS contenant un article "Adhésion"
    members_flagged = _refresh_pos_member_flag()

    db.session.commit()
    return {
        "orders_imported": orders_imported,
        "orders_updated": orders_updated,
        "orders_total": orders_imported + orders_updated,
        "lines_imported": lines_imported,
        "lines_updated": lines_updated,
        "lines_total": lines_imported + lines_updated,
        "payments_imported": payments_imported,
        "payments_updated": payments_updated,
        "payments_total": payments_imported + payments_updated,
        "entities_created": entities_created,
        "entities_updated": entities_updated,
        "members_flagged": members_flagged,
    }


def _refresh_pos_member_flag():
    """Met `is_member=True` sur toute Entity ayant une OrderLine "Adhésion" en POS.

    Idempotent : peut être appelé n'importe quand pour rattrapper d'anciens tiers.
    Renvoie le nombre de tiers passés à True (count des passés-à-True nouveaux).
    """
    member_ids = {
        eid for (eid,) in (
            db.session.query(Order.entity_id)
            .join(OrderLine, OrderLine.order_id == Order.id)
            .filter(Order.entity_id.isnot(None))
            .filter(db.or_(
                db.func.lower(OrderLine.full_product_name).like("%adh%sion%"),
                db.func.lower(OrderLine.product_name).like("%adh%sion%"),
            ))
            .distinct()
            .all()
        ) if eid is not None
    }
    if not member_ids:
        return 0
    # On ne flippe que ceux qui ne le sont pas déjà
    to_flag = [eid for (eid,) in (
        db.session.query(Entity.id)
        .filter(Entity.id.in_(member_ids))
        .filter(Entity.is_member.is_(False))
        .all()
    )]
    if not to_flag:
        return 0
    Entity.query.filter(Entity.id.in_(to_flag)).update(
        {"is_member": True, "entity_type": "ADHERENT"},
        synchronize_session=False,
    )
    return len(to_flag)
