"""Synchronisation HelloAsso : forms + orders + items + payments.

Stratégie :
- 1 appel /forms pour cataloguer les formulaires
- 1 appel /orders avec withDetails=true pour récupérer items + payments embarqués
- Rattachement aux Entity par email (item.user.email d'abord, puis payer.email)
- is_member positionné à True sur l'Entity dès qu'un item de type "Membership" est trouvé
"""
import json
from datetime import datetime

from app.extensions import db
from app.models import (
    Entity, HelloAssoForm, HelloAssoOrder, HelloAssoItem, HelloAssoPayment,
)
from app.services.entity_resolver import entity_by_email, unique_entity_name
from app.services.helloasso_client import from_app_config


def _to_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _amount_cents(value):
    """HelloAsso renvoie déjà des montants en centimes (entier)."""
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _amount_block_cents(amount):
    """`amount` peut être un int (cents) ou un dict {total, vat, ...}."""
    if isinstance(amount, dict):
        return _amount_cents(amount.get("total"))
    return _amount_cents(amount)


def _vat_block_cents(amount):
    if isinstance(amount, dict):
        return _amount_cents(amount.get("vat"))
    return 0


def _get_or_create_member(cache, email, first_name, last_name):
    """Renvoie l'Entity adhérente ; la crée en type ADHERENT si l'email est inconnu.

    Renvoie (entity, created_bool).
    """
    if not email:
        return None, False
    existing = entity_by_email(cache, email)
    if existing is not None:
        return existing, False
    base_name = " ".join(p for p in (first_name, last_name) if p).strip() or email
    ent = Entity(
        name=unique_entity_name(base_name, email),
        entity_type="ADHERENT",
        email=email,
        is_member=True,
    )
    db.session.add(ent)
    db.session.flush()  # id dispo pour FK
    cache[email.strip().lower()] = ent
    return ent, True


def _upsert_form(item):
    ha_id = item.get("id")
    if not ha_id:
        return None, False
    existing = HelloAssoForm.query.filter_by(helloasso_id=ha_id).first()
    target = existing or HelloAssoForm(helloasso_id=ha_id)
    target.form_slug = item.get("formSlug") or item.get("slug")
    target.form_type = item.get("formType")
    target.title = item.get("title")
    target.organization_slug = item.get("organizationSlug")
    target.state = item.get("state")
    target.raw_payload = json.dumps(item, ensure_ascii=False, default=str)
    target.imported_at = datetime.utcnow()
    is_new = existing is None
    if is_new:
        db.session.add(target)
    return target, is_new


def _upsert_order(item, form_by_slug, entity_cache):
    ha_id = item.get("id")
    if not ha_id:
        return None, False
    existing = HelloAssoOrder.query.filter_by(helloasso_id=ha_id).first()
    target = existing or HelloAssoOrder(helloasso_id=ha_id)

    payer = item.get("payer") or {}
    target.date = _to_datetime(item.get("date"))
    target.amount_total_cents = _amount_block_cents(item.get("amount"))
    target.amount_vat_cents = _vat_block_cents(item.get("amount"))
    target.payer_first_name = payer.get("firstName")
    target.payer_last_name = payer.get("lastName")
    target.payer_email = (payer.get("email") or "").strip() or None
    target.form_slug = item.get("formSlug")
    target.form_type = item.get("formType")
    target.organization_slug = item.get("organizationSlug")
    target.raw_payload = json.dumps(item, ensure_ascii=False, default=str)
    target.imported_at = datetime.utcnow()

    form = form_by_slug.get(target.form_slug) if target.form_slug else None
    target.form_id = form.id if form else None

    ent = entity_by_email(entity_cache, target.payer_email)
    target.entity_id = ent.id if ent else None

    is_new = existing is None
    if is_new:
        db.session.add(target)
    return target, is_new


def _upsert_item(item, order, entity_cache):
    ha_id = item.get("id")
    if not ha_id:
        return None, False
    existing = HelloAssoItem.query.filter_by(helloasso_id=ha_id).first()
    target = existing or HelloAssoItem(helloasso_id=ha_id)

    user = item.get("user") or {}
    target.order_id = order.id
    target.name = item.get("name")
    target.type = item.get("type")
    target.state = item.get("state")
    target.amount_cents = _amount_block_cents(item.get("amount"))
    target.user_first_name = user.get("firstName")
    target.user_last_name = user.get("lastName")
    target.user_email = (user.get("email") or "").strip() or None
    target.raw_payload = json.dumps(item, ensure_ascii=False, default=str)
    target.imported_at = datetime.utcnow()

    created_entity = False
    ent = None
    # Pour une adhésion : créer un tiers Adhérent si l'email est inconnu.
    if target.type == "Membership":
        ent, created_entity = _get_or_create_member(
            entity_cache, target.user_email,
            target.user_first_name, target.user_last_name,
        )
        if ent is None and order.payer_email:
            ent, created_entity = _get_or_create_member(
                entity_cache, order.payer_email,
                order.payer_first_name, order.payer_last_name,
            )
            if created_entity and order.entity_id is None:
                order.entity_id = ent.id
    if ent is None:
        # priorité à l'email du bénéficiaire, sinon le payeur déjà rattaché.
        ent = (
            entity_by_email(entity_cache, target.user_email)
            or (order.entity if order.entity_id else None)
        )
    target.entity_id = ent.id if ent else None

    is_new = existing is None
    if is_new:
        db.session.add(target)
    return target, is_new, created_entity


def _upsert_payment(item, order):
    ha_id = item.get("id")
    if not ha_id:
        return None, False
    existing = HelloAssoPayment.query.filter_by(helloasso_id=ha_id).first()
    target = existing or HelloAssoPayment(helloasso_id=ha_id)

    payer = item.get("payer") or {}
    target.order_id = order.id
    target.amount_cents = _amount_block_cents(item.get("amount"))
    target.state = item.get("state")
    target.payment_means = item.get("paymentMeans") or item.get("paymentMean")
    target.payment_date = _to_datetime(item.get("date"))
    target.payer_email = (payer.get("email") or order.payer_email or "").strip() or None
    target.raw_payload = json.dumps(item, ensure_ascii=False, default=str)
    target.imported_at = datetime.utcnow()

    is_new = existing is None
    if is_new:
        db.session.add(target)
    return target, is_new


def _refresh_is_member(entity_ids):
    """Met `is_member=True` sur les Entity ayant au moins un item d'adhésion."""
    if not entity_ids:
        return 0
    rows = (
        db.session.query(HelloAssoItem.entity_id)
        .filter(HelloAssoItem.entity_id.in_(entity_ids))
        .filter(HelloAssoItem.type == "Membership")
        .distinct()
        .all()
    )
    member_ids = {r[0] for r in rows if r[0] is not None}
    if not member_ids:
        return 0
    Entity.query.filter(Entity.id.in_(member_ids)).update(
        {"is_member": True, "entity_type": "ADHERENT"},
        synchronize_session=False,
    )
    return len(member_ids)


def sync_helloasso(progress_cb=None):
    """Synchronise forms + orders + items + payments. Retourne un dict de compteurs."""
    client = from_app_config()

    # 1) Forms
    forms_imported = forms_updated = 0
    form_by_slug = {}
    for it in client.paginate(client.org_path("/forms")):
        target, is_new = _upsert_form(it)
        if target is None:
            continue
        if is_new:
            forms_imported += 1
        else:
            forms_updated += 1
        if target.form_slug:
            form_by_slug[target.form_slug] = target
        if progress_cb:
            progress_cb(forms_imported + forms_updated, None,
                        f"Formulaires : {forms_imported + forms_updated}")
    db.session.flush()

    # 2) Orders (+ items + payments embarqués via withDetails)
    orders_imported = orders_updated = 0
    items_imported = items_updated = 0
    payments_imported = payments_updated = 0
    members_created = 0
    entity_cache = {}
    touched_entity_ids = set()

    for it in client.paginate(
        client.org_path("/orders"),
        params={"withDetails": "true"},
    ):
        order, is_new = _upsert_order(it, form_by_slug, entity_cache)
        if order is None:
            continue
        if is_new:
            orders_imported += 1
        else:
            orders_updated += 1
        db.session.flush()

        for li in it.get("items") or []:
            line, was_new, created = _upsert_item(li, order, entity_cache)
            if line is None:
                continue
            if was_new:
                items_imported += 1
            else:
                items_updated += 1
            if created:
                members_created += 1
            if line.entity_id:
                touched_entity_ids.add(line.entity_id)

        for pay in it.get("payments") or []:
            _, was_new = _upsert_payment(pay, order)
            if was_new:
                payments_imported += 1
            else:
                payments_updated += 1

        if progress_cb:
            progress_cb(orders_imported + orders_updated, None,
                        f"Commandes : {orders_imported + orders_updated}")

    # 3) Mise à jour is_member sur les entités touchées
    members_flagged = _refresh_is_member(touched_entity_ids)

    db.session.commit()
    return {
        "forms_imported": forms_imported,
        "forms_updated": forms_updated,
        "orders_imported": orders_imported,
        "orders_updated": orders_updated,
        "items_imported": items_imported,
        "items_updated": items_updated,
        "payments_imported": payments_imported,
        "payments_updated": payments_updated,
        "members_flagged": members_flagged,
        "members_created": members_created,
        # Adhérents touchés : leur synchronisation Brevo suit (lot B3).
        "member_ids": sorted(i for i in touched_entity_ids if i),
    }
