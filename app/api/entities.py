"""Tiers : liste, fiche (commandes, factures, temps, achats), création, modification,
suppression, synchronisation HelloAsso, note Odoo. `/entities` reste la recherche des
listes de saisie (lookups.py) ; la gestion des tiers est sous `/tiers`."""
from flask import current_app, jsonify, request, url_for

from app.extensions import db
from app.models import (
    Account, CustomerInvoice, Entity, HelloAssoItem, HelloAssoOrder, HelloAssoPayment, Order,
    OrderLine, OrderPayment, Product, Purchase, WorkTime,
)
from app.models.customer_invoice import CUSTOMER_INVOICE_PAYMENT_STATES, CUSTOMER_INVOICE_STATES
from app.models.entity import ENTITY_TYPES
from app.models.order import POS_ORDER_STATES
from app.queries.entities import last_membership_dates
from app.services import catalog, external_config, odoo_partner_update
from app.services.helloasso_client import HelloAssoConfigError
from app.services.helloasso_sync import sync_helloasso
from app.services.odoo_client import OdooConfigError
from app.services.purchase_posting import purchase_state
from app.services.purchase_sync import normalize_iban, normalize_siret, normalize_vat

from . import ApiError, bp, get_or_404, invalid, json_body, notice

SIRET_MESSAGE = "Le SIRET doit comporter 14 chiffres."
TYPE_CODES = {code for code, _ in ENTITY_TYPES}


def _iso(value):
    return value.isoformat() if value else None


def integrations_state() -> dict:
    """Intégrations dont dépendent les actions des tiers et adhérents (boutons grisés sinon)."""
    return {name: {"available": external_config.is_available(name),
                   "message": external_config.unavailable_message(name)}
            for name in ("helloasso", "odoo", "smtp")}


def entity_payload(e: Entity, last_ha=None, last_pos=None, transactions=None) -> dict:
    return {
        "id": e.id, "name": e.name, "entity_type": e.entity_type, "email": e.email,
        "account_code": e.account_code, "is_member": e.is_member, "is_benevole": e.is_benevole,
        "notes": e.notes, "default_product_id": e.default_product_id,
        "default_product": e.default_product.name if e.default_product else None,
        "vat_number": e.vat_number, "siret": e.siret, "iban": e.iban,
        "last_helloasso_membership": _iso(last_ha), "last_pos_membership": _iso(last_pos),
        "transactions": e.transactions.count() if transactions is None else transactions,
    }


def _meta():
    return {"types": [{"value": v, "label": l} for v, l in ENTITY_TYPES],
            "products": [{"value": str(p.id), "label": p.name} for p in catalog.purchase_products()],
            "integrations": integrations_state()}


@bp.route("/tiers")
def tiers_list():
    """Tiers hors adhérents (les adhérents ont leur écran), recherche nom / email."""
    q = (request.args.get("q") or "").strip()
    query = Entity.query.filter(Entity.entity_type != "ADHERENT")
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(Entity.name.ilike(like), Entity.email.ilike(like)))
    entities = query.order_by(Entity.name).all()
    last_ha, last_pos = last_membership_dates()
    counts = dict(db.session.query(Entity.id, db.func.count())
                  .join(Entity.transactions).group_by(Entity.id).all())
    return jsonify(items=[entity_payload(e, last_ha.get(e.id), last_pos.get(e.id), counts.get(e.id, 0))
                          for e in entities], meta=_meta())


def _apply(entity: Entity, data: dict) -> None:
    name = str(data.get("name") or "").strip()
    if not name:
        raise invalid("Le nom est obligatoire.", "name")
    duplicate = Entity.query.filter(Entity.name == name)
    if entity.id is not None:
        duplicate = duplicate.filter(Entity.id != entity.id)
    if duplicate.first():
        raise invalid(f"Une entité nommée « {name} » existe déjà.", "name")
    siret = str(data.get("siret") or "").strip()
    if siret and normalize_siret(siret) is None:
        raise invalid(SIRET_MESSAGE, "siret")
    entity_type = data.get("entity_type") or "AUTRE"
    if entity_type not in TYPE_CODES:
        raise invalid("Type de tiers inconnu.", "entity_type")
    product_id = data.get("default_product_id")
    try:
        product_id = int(product_id) if product_id not in (None, "") else None
    except (TypeError, ValueError):
        product_id = None
    if product_id is not None and db.session.get(Product, product_id) is None:
        product_id = None
    text = lambda key, size: (str(data.get(key) or "").strip()[:size] or None)  # noqa: E731
    entity.name, entity.entity_type = name[:200], entity_type
    entity.account_code, entity.email = text("account_code", 20), text("email", 200)
    entity.is_member, entity.is_benevole = bool(data.get("is_member")), bool(data.get("is_benevole"))
    entity.notes = str(data.get("notes") or "").strip() or None
    entity.default_product_id = product_id
    entity.vat_number = normalize_vat(data.get("vat_number"))
    entity.siret = normalize_siret(siret)
    entity.iban = normalize_iban(data.get("iban"))


@bp.route("/tiers", methods=["POST"])
def tiers_create():
    entity = Entity()
    _apply(entity, json_body())
    db.session.add(entity)
    db.session.commit()
    return jsonify(item=entity_payload(entity), notices=[notice(f"Entité « {entity.name} » créée.")]), 201


@bp.route("/tiers/<int:entity_id>", methods=["PATCH"])
def tiers_update(entity_id):
    entity = get_or_404(Entity, entity_id, "Tiers introuvable.")
    _apply(entity, json_body())
    db.session.commit()
    return jsonify(item=entity_payload(entity), notices=[notice(f"Entité « {entity.name} » mise à jour.")])


@bp.route("/tiers/<int:entity_id>", methods=["DELETE"])
def tiers_delete(entity_id):
    entity = get_or_404(Entity, entity_id, "Tiers introuvable.")
    count = entity.transactions.count()
    if count:
        raise ApiError("conflict", f"Impossible de supprimer « {entity.name} » : {count} transaction(s) "
                       "liée(s).", status=409)
    db.session.delete(entity)
    db.session.commit()
    return jsonify(notices=[notice(f"Entité « {entity.name} » supprimée.")])


def _pos_orders(entity_id):
    orders = Order.query.filter_by(entity_id=entity_id).order_by(Order.date_order.desc().nullslast()).all()
    ids = [o.id for o in orders]
    lines = {i: [] for i in ids}
    payments = {i: [] for i in ids}
    if ids:
        for ln in OrderLine.query.filter(OrderLine.order_id.in_(ids)).order_by(OrderLine.id):
            lines[ln.order_id].append({
                "product": ln.full_product_name or ln.product_name or str(ln.product_id or ""),
                "qty": ln.qty, "price_unit_cents": ln.price_unit_cents, "discount": ln.discount,
                "subtotal_cents": ln.price_subtotal_cents, "subtotal_incl_cents": ln.price_subtotal_incl_cents})
        for p in (OrderPayment.query.filter(OrderPayment.order_id.in_(ids))
                  .order_by(OrderPayment.payment_date.asc().nullsfirst(), OrderPayment.id)):
            payments[p.order_id].append({
                "date": _iso(p.payment_date), "method": p.payment_method_name, "card_type": p.card_type,
                "reference": p.transaction_id or p.name, "amount_cents": p.amount_cents})
    states = dict(POS_ORDER_STATES)
    return [{"id": o.id, "name": o.name or f"POS #{o.odoo_id}", "date": _iso(o.date_order),
             "session": o.session_name, "state": o.state, "state_label": states.get(o.state, o.state),
             "amount_total_cents": o.amount_total_cents, "lines": lines[o.id], "payments": payments[o.id]}
            for o in orders]


@bp.route("/tiers/<int:entity_id>")
def tiers_detail(entity_id):
    """Fiche du tiers : identité et toutes ses pièces rattachées."""
    entity = get_or_404(Entity, entity_id, "Tiers introuvable.")
    last_ha, last_pos = last_membership_dates([entity.id])

    ha_orders = (HelloAssoOrder.query.filter_by(entity_id=entity.id)
                 .order_by(HelloAssoOrder.date.desc().nullslast()).all())
    ha_items = HelloAssoItem.query.filter_by(entity_id=entity.id).order_by(HelloAssoItem.id.desc()).all()
    ha_payments = []
    if ha_orders:
        ha_payments = (HelloAssoPayment.query.filter(HelloAssoPayment.order_id.in_([o.id for o in ha_orders]))
                       .order_by(HelloAssoPayment.payment_date.desc().nullslast()).all())

    invoice_states, payment_states = dict(CUSTOMER_INVOICE_STATES), dict(CUSTOMER_INVOICE_PAYMENT_STATES)
    invoices = (CustomerInvoice.query.filter_by(entity_id=entity.id)
                .order_by(CustomerInvoice.invoice_date.desc().nullslast(), CustomerInvoice.id.desc()).all())
    work_times = entity.work_times.order_by(WorkTime.work_date.desc(), WorkTime.id.desc()).all()
    purchases = (Purchase.query.filter_by(entity_id=entity.id)
                 .order_by(Purchase.issue_date.desc().nullslast(), Purchase.id.desc()).all())
    account = Account.query.filter_by(code=entity.account_code).first() if entity.account_code else None
    balance = None
    if account is not None:
        debit, credit = account.balance()
        balance = credit - debit

    return jsonify(
        item=entity_payload(entity, last_ha.get(entity.id), last_pos.get(entity.id)),
        supplier={"account_code": account.code if account else None, "balance_cents": balance},
        purchases=[{"id": p.id, "url": url_for("purchases.detail", purchase_id=p.id),
                    "issue_date": _iso(p.issue_date), "invoice_number": p.invoice_number,
                    "is_credit_note": p.is_credit_note, "is_hidden": p.is_hidden,
                    "total_cents": p.total_cents, "state": purchase_state(p).label} for p in purchases],
        pos_orders=_pos_orders(entity.id),
        customer_invoices=[{
            "id": inv.id, "url": url_for("customer_invoices.detail", invoice_id=inv.id),
            "date": _iso(inv.invoice_date), "name": inv.name or str(inv.odoo_id), "ref": inv.ref,
            "amount_total_cents": inv.amount_total_cents, "amount_residual_cents": inv.amount_residual_cents,
            "state": inv.state, "state_label": invoice_states.get(inv.state, inv.state),
            "payment_state": inv.payment_state,
            "payment_state_label": payment_states.get(inv.payment_state, inv.payment_state)}
            for inv in invoices],
        work_times=[{"id": wt.id, "date": _iso(wt.work_date), "task_type": wt.task_type.name,
                     "hours": float(wt.hours), "valuation_cents": wt.valuation_cents, "notes": wt.notes}
                    for wt in work_times],
        helloasso={
            "orders": [{"date": _iso(o.date), "form_slug": o.form_slug, "form_type": o.form_type,
                        "amount_total_cents": o.amount_total_cents,
                        "payer": " ".join(filter(None, (o.payer_first_name, o.payer_last_name)))}
                       for o in ha_orders],
            "items": [{"name": it.name, "type": it.type, "state": it.state, "amount_cents": it.amount_cents,
                       "beneficiary": " ".join(filter(None, (it.user_first_name, it.user_last_name)))}
                      for it in ha_items],
            "payments": [{"date": _iso(p.payment_date), "means": p.payment_means, "state": p.state,
                          "amount_cents": p.amount_cents} for p in ha_payments],
        },
        meta=_meta(),
    )


@bp.route("/tiers/<int:entity_id>/odoo-note", methods=["POST"])
def tiers_update_odoo_note(entity_id):
    """Écrit la date anniversaire et le statut d'adhésion dans « Notes interne » d'Odoo."""
    entity = get_or_404(Entity, entity_id, "Tiers introuvable.")
    if not odoo_partner_update.is_configured():
        raise ApiError("conflict", external_config.unavailable_message("odoo"), status=409)
    last_ha, last_pos = last_membership_dates([entity.id])
    try:
        ok, message = odoo_partner_update.update_single_member(
            entity, last_ha.get(entity.id), last_pos.get(entity.id))
    except OdooConfigError as e:
        raise ApiError("conflict", str(e), status=409) from None
    except Exception as e:  # noqa: BLE001 — l'erreur d'Odoo est montrée telle quelle
        current_app.logger.exception("Mise à jour note Odoo échouée")
        raise ApiError("bad_gateway", f"Erreur Odoo : {e}", status=502) from None
    return jsonify(notices=[notice(message, "success" if ok else "warning")])


@bp.route("/helloasso/sync", methods=["POST"])
def helloasso_sync():
    try:
        result = sync_helloasso()
    except HelloAssoConfigError as e:
        raise ApiError("conflict", str(e), status=409) from None
    except Exception as e:  # noqa: BLE001
        current_app.logger.exception("Sync HelloAsso échouée")
        raise ApiError("bad_gateway", f"Erreur HelloAsso : {e}", status=502) from None
    return jsonify(result=result, notices=[notice(
        "Synchronisation HelloAsso terminée : "
        f"{result['orders_imported'] + result['orders_updated']} commande(s), "
        f"{result['items_imported'] + result['items_updated']} article(s), "
        f"{result['payments_imported'] + result['payments_updated']} paiement(s), "
        f"{result['members_created']} adhérent(s) créé(s), "
        f"{result['members_flagged']} adhérent(s) marqué(s).")])
