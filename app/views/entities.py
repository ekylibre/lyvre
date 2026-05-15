import csv
from datetime import datetime
from io import StringIO
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, Response
from flask_login import login_required
from app.extensions import db
from app.models import (
    Entity, HelloAssoOrder, HelloAssoItem, HelloAssoPayment,
    Order, OrderLine, OrderPayment,
    CustomerInvoice,
)
from app.models.order import POS_ORDER_STATES
from app.models.customer_invoice import (
    CUSTOMER_INVOICE_STATES, CUSTOMER_INVOICE_PAYMENT_STATES,
)
from app.models.entity import ENTITY_TYPES
from app.services.helloasso_client import HelloAssoConfigError, from_app_config as helloasso_client
from app.services.helloasso_create import create_membership_for_entity
from app.services.helloasso_sync import sync_helloasso

bp = Blueprint("entities", __name__, url_prefix="/entities")


def _helloasso_configured():
    return all(current_app.config.get(k) for k in (
        "HELLOASSO_CLIENT_ID", "HELLOASSO_CLIENT_SECRET", "HELLOASSO_ORG_SLUG",
    ))


@bp.route("/")
@login_required
def index():
    entities = (
        Entity.query
        .filter(Entity.entity_type != "ADHERENT")
        .order_by(Entity.name)
        .all()
    )
    # Date de la dernière commande HelloAsso avec au moins un item Membership,
    # par tiers — une seule requête agrégée pour éviter le N+1.
    rows = (
        db.session.query(
            HelloAssoOrder.entity_id,
            db.func.max(HelloAssoOrder.date),
        )
        .join(HelloAssoItem, HelloAssoItem.order_id == HelloAssoOrder.id)
        .filter(HelloAssoItem.type == "Membership")
        .filter(HelloAssoOrder.entity_id.isnot(None))
        .group_by(HelloAssoOrder.entity_id)
        .all()
    )
    last_membership_by_entity = {eid: dt for eid, dt in rows}

    # Date de la dernière commande Odoo POS avec un article "Adhésion", par tiers.
    odoo_rows = (
        db.session.query(
            Order.entity_id,
            db.func.max(Order.date_order),
        )
        .join(OrderLine, OrderLine.order_id == Order.id)
        .filter(Order.entity_id.isnot(None))
        .filter(
            db.or_(
                db.func.lower(OrderLine.full_product_name).like("%adh%sion%"),
                db.func.lower(OrderLine.product_name).like("%adh%sion%"),
            )
        )
        .group_by(Order.entity_id)
        .all()
    )
    last_odoo_membership_by_entity = {eid: dt for eid, dt in odoo_rows}

    return render_template(
        "entities/index.html",
        entities=entities,
        entity_types=dict(ENTITY_TYPES),
        helloasso_configured=_helloasso_configured(),
        last_membership_by_entity=last_membership_by_entity,
        last_odoo_membership_by_entity=last_odoo_membership_by_entity,
    )


def _members_query(q):
    query = Entity.query.filter_by(entity_type="ADHERENT")
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(
            db.or_(
                db.func.lower(Entity.name).like(like),
                db.func.lower(Entity.email).like(like),
            )
        )
    return query.order_by(Entity.name)


def _parse_date(s):
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _filter_by_date_range(members_list, last_ha, last_pos, date_from, date_to):
    """Garde les adhérents dont au moins une date d'adhésion (HA ou POS),
    si elle est non nulle, tombe dans la plage [date_from, date_to]."""
    if not date_from and not date_to:
        return members_list
    result = []
    for m in members_list:
        ha = last_ha.get(m.id)
        pos = last_pos.get(m.id)
        candidates = [d.date() for d in (ha, pos) if d is not None]
        for d in candidates:
            if date_from and d < date_from:
                continue
            if date_to and d > date_to:
                continue
            result.append(m)
            break
    return result


def _last_membership_dates(member_ids):
    last_ha = {}
    last_pos = {}
    if not member_ids:
        return last_ha, last_pos
    ha_rows = (
        db.session.query(
            HelloAssoOrder.entity_id, db.func.max(HelloAssoOrder.date),
        )
        .join(HelloAssoItem, HelloAssoItem.order_id == HelloAssoOrder.id)
        .filter(HelloAssoItem.type == "Membership")
        .filter(HelloAssoOrder.entity_id.in_(member_ids))
        .group_by(HelloAssoOrder.entity_id)
        .all()
    )
    last_ha = {eid: dt for eid, dt in ha_rows}

    odoo_rows = (
        db.session.query(Order.entity_id, db.func.max(Order.date_order))
        .join(OrderLine, OrderLine.order_id == Order.id)
        .filter(Order.entity_id.in_(member_ids))
        .filter(db.or_(
            db.func.lower(OrderLine.full_product_name).like("%adh%sion%"),
            db.func.lower(OrderLine.product_name).like("%adh%sion%"),
        ))
        .group_by(Order.entity_id)
        .all()
    )
    last_pos = {eid: dt for eid, dt in odoo_rows}
    return last_ha, last_pos


@bp.route("/members")
@login_required
def members():
    q = (request.args.get("q") or "").strip()
    date_from_raw = (request.args.get("date_from") or "").strip()
    date_to_raw = (request.args.get("date_to") or "").strip()
    date_from = _parse_date(date_from_raw)
    date_to = _parse_date(date_to_raw)

    members_list = _members_query(q).all()
    last_membership_by_entity, last_odoo_membership_by_entity = _last_membership_dates(
        [m.id for m in members_list]
    )
    members_list = _filter_by_date_range(
        members_list, last_membership_by_entity, last_odoo_membership_by_entity,
        date_from, date_to,
    )

    return render_template(
        "entities/members.html",
        members=members_list,
        q=q,
        date_from=date_from_raw,
        date_to=date_to_raw,
        last_membership_by_entity=last_membership_by_entity,
        last_odoo_membership_by_entity=last_odoo_membership_by_entity,
        helloasso_configured=_helloasso_configured(),
    )


@bp.route("/members.csv")
@login_required
def members_csv():
    q = (request.args.get("q") or "").strip()
    date_from = _parse_date(request.args.get("date_from"))
    date_to = _parse_date(request.args.get("date_to"))

    members_list = _members_query(q).all()
    last_ha, last_pos = _last_membership_dates([m.id for m in members_list])
    members_list = _filter_by_date_range(members_list, last_ha, last_pos, date_from, date_to)

    output = StringIO()
    writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow([
        "Nom", "Email", "Adhérent",
        "Dernière adhésion HelloAsso", "Dernière adhésion POS",
        "Notes",
    ])
    for e in members_list:
        ha = last_ha.get(e.id)
        pos = last_pos.get(e.id)
        writer.writerow([
            e.name,
            e.email or "",
            "Oui" if e.is_member else "Non",
            ha.strftime("%d/%m/%Y") if ha else "",
            pos.strftime("%d/%m/%Y") if pos else "",
            e.notes or "",
        ])

    csv_bytes = output.getvalue().encode("utf-8-sig")
    response = Response(csv_bytes, mimetype="text/csv")
    response.headers["Content-Disposition"] = 'attachment; filename="adherents.csv"'
    return response


@bp.route("/<int:entity_id>")
@login_required
def detail(entity_id):
    entity = Entity.query.get_or_404(entity_id)
    orders = (
        HelloAssoOrder.query.filter_by(entity_id=entity.id)
        .order_by(HelloAssoOrder.date.desc().nullslast())
        .all()
    )
    items = (
        HelloAssoItem.query.filter_by(entity_id=entity.id)
        .order_by(HelloAssoItem.id.desc())
        .all()
    )
    order_ids = [o.id for o in orders]
    payments = []
    if order_ids:
        payments = (
            HelloAssoPayment.query.filter(HelloAssoPayment.order_id.in_(order_ids))
            .order_by(HelloAssoPayment.payment_date.desc().nullslast())
            .all()
        )

    # Commandes POS Odoo : on charge lignes + paiements groupés par order_id
    odoo_orders = (
        Order.query.filter_by(entity_id=entity.id)
        .order_by(Order.date_order.desc().nullslast())
        .all()
    )
    odoo_order_ids = [o.id for o in odoo_orders]
    odoo_lines_by_order = {oid: [] for oid in odoo_order_ids}
    odoo_payments_by_order = {oid: [] for oid in odoo_order_ids}
    if odoo_order_ids:
        for ln in (
            OrderLine.query.filter(OrderLine.order_id.in_(odoo_order_ids))
            .order_by(OrderLine.id).all()
        ):
            odoo_lines_by_order.setdefault(ln.order_id, []).append(ln)
        for pay in (
            OrderPayment.query.filter(OrderPayment.order_id.in_(odoo_order_ids))
            .order_by(OrderPayment.payment_date.asc().nullsfirst(), OrderPayment.id).all()
        ):
            odoo_payments_by_order.setdefault(pay.order_id, []).append(pay)

    customer_invoices = (
        CustomerInvoice.query.filter_by(entity_id=entity.id)
        .order_by(CustomerInvoice.invoice_date.desc().nullslast(),
                  CustomerInvoice.id.desc())
        .all()
    )

    return render_template(
        "entities/detail.html",
        entity=entity,
        entity_types=dict(ENTITY_TYPES),
        orders=orders, items=items, payments=payments,
        odoo_orders=odoo_orders,
        odoo_lines_by_order=odoo_lines_by_order,
        odoo_payments_by_order=odoo_payments_by_order,
        odoo_states=dict(POS_ORDER_STATES),
        customer_invoices=customer_invoices,
        invoice_states=dict(CUSTOMER_INVOICE_STATES),
        invoice_payment_states=dict(CUSTOMER_INVOICE_PAYMENT_STATES),
    )


@bp.route("/create-helloasso-memberships", methods=["GET", "POST"])
@login_required
def create_helloasso_memberships():
    """Liste les tiers ayant une adhésion POS sans adhésion HA, et offre la création.

    GET  : preview (liste des tiers concernés)
    POST : exécution effective via l'API HelloAsso.
    """
    # Sous-requête : entités qui ONT déjà une adhésion HA
    ha_subq = (
        db.session.query(HelloAssoOrder.entity_id)
        .join(HelloAssoItem, HelloAssoItem.order_id == HelloAssoOrder.id)
        .filter(HelloAssoItem.type == "Membership")
        .filter(HelloAssoOrder.entity_id.isnot(None))
        .distinct()
        .subquery()
    )
    # Tiers cibles : adhésion POS mais pas dans ha_subq
    target_rows = (
        db.session.query(
            Order.entity_id,
            db.func.max(Order.date_order).label("last_pos_date"),
        )
        .join(OrderLine, OrderLine.order_id == Order.id)
        .filter(Order.entity_id.isnot(None))
        .filter(db.or_(
            db.func.lower(OrderLine.full_product_name).like("%adh%sion%"),
            db.func.lower(OrderLine.product_name).like("%adh%sion%"),
        ))
        .filter(~Order.entity_id.in_(db.session.query(ha_subq)))
        .group_by(Order.entity_id)
        .all()
    )
    targets = []
    for entity_id, last_pos_date in target_rows:
        ent = Entity.query.get(entity_id)
        if not ent:
            continue
        # Récupère le montant de la ligne adhésion la plus récente pour ce tiers
        line = (
            db.session.query(OrderLine)
            .join(Order, Order.id == OrderLine.order_id)
            .filter(Order.entity_id == entity_id)
            .filter(db.or_(
                db.func.lower(OrderLine.full_product_name).like("%adh%sion%"),
                db.func.lower(OrderLine.product_name).like("%adh%sion%"),
            ))
            .order_by(Order.date_order.desc())
            .first()
        )
        targets.append({
            "entity": ent,
            "last_pos_date": last_pos_date,
            "amount_cents": line.price_subtotal_incl_cents if line else 0,
            "has_email": bool(ent.email),
        })

    # Form HelloAsso à utiliser : le plus fréquent parmi les Memberships connus,
    # avec fallback codé en dur.
    form_row = (
        db.session.query(HelloAssoOrder.form_slug, HelloAssoOrder.form_type, db.func.count())
        .join(HelloAssoItem, HelloAssoItem.order_id == HelloAssoOrder.id)
        .filter(HelloAssoItem.type == "Membership")
        .group_by(HelloAssoOrder.form_slug, HelloAssoOrder.form_type)
        .order_by(db.func.count().desc())
        .first()
    )
    form_slug = (form_row[0] if form_row else None) or "adhesion"
    form_type = (form_row[1] if form_row else None) or "Membership"

    if request.method == "POST":
        if not _helloasso_configured():
            flash("HelloAsso non configuré — abandon.", "warning")
            return redirect(url_for("entities.index"))
        try:
            client = helloasso_client()
        except HelloAssoConfigError as e:
            flash(str(e), "warning")
            return redirect(url_for("entities.index"))
        success = errors = skipped = 0
        error_lines = []
        for t in targets:
            ent = t["entity"]
            if not t["has_email"]:
                skipped += 1
                error_lines.append(f"{ent.name} — pas d'email, ignoré")
                continue
            ok, info = create_membership_for_entity(
                entity=ent,
                amount_cents=t["amount_cents"],
                payment_date=t["last_pos_date"],
                form_type=form_type, form_slug=form_slug,
                client=client,
            )
            if ok:
                success += 1
            else:
                errors += 1
                error_lines.append(f"{ent.name} <{ent.email}> — {info}")
        msg = (
            f"HelloAsso : {success} adhésion(s) créée(s), {errors} erreur(s), "
            f"{skipped} ignoré(s) (sans email)."
        )
        if errors or skipped:
            flash(msg + " Détail : " + " | ".join(error_lines[:5]),
                  "warning" if success else "danger")
        else:
            flash(msg, "success")
        return redirect(url_for("entities.index"))

    return render_template(
        "entities/create_helloasso_memberships.html",
        targets=targets,
        form_slug=form_slug,
        form_type=form_type,
        helloasso_configured=_helloasso_configured(),
    )


@bp.route("/sync-helloasso", methods=["POST"])
@login_required
def sync_helloasso_route():
    try:
        result = sync_helloasso()
    except HelloAssoConfigError as e:
        flash(str(e), "warning")
        return redirect(url_for("entities.index"))
    except Exception as e:
        current_app.logger.exception("Sync HelloAsso échouée")
        flash(f"Erreur HelloAsso : {e}", "danger")
        return redirect(url_for("entities.index"))
    flash(
        "Sync HelloAsso OK — "
        f"{result['orders_imported'] + result['orders_updated']} commande(s), "
        f"{result['items_imported'] + result['items_updated']} article(s), "
        f"{result['payments_imported'] + result['payments_updated']} paiement(s), "
        f"{result['members_created']} adhérent(s) créé(s), "
        f"{result['members_flagged']} adhérent(s) marqué(s).",
        "success",
    )
    return redirect(url_for("entities.index"))


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    if request.method == "POST":
        name = request.form["name"].strip()
        if not name:
            flash("Le nom est obligatoire.", "danger")
        elif Entity.query.filter_by(name=name).first():
            flash(f"Une entité nommée « {name} » existe déjà.", "danger")
        else:
            entity = Entity(
                name=name,
                entity_type=request.form.get("entity_type", "AUTRE"),
                account_code=request.form.get("account_code", "").strip() or None,
                email=request.form.get("email", "").strip() or None,
                is_member=bool(request.form.get("is_member")),
                notes=request.form.get("notes", "").strip() or None,
            )
            db.session.add(entity)
            db.session.commit()
            flash(f"Entité « {name} » créée.", "success")
            return redirect(url_for("entities.index"))

    return render_template("entities/form.html", entity=None, entity_types=ENTITY_TYPES)


@bp.route("/<int:entity_id>/edit", methods=["GET", "POST"])
@login_required
def edit(entity_id):
    entity = Entity.query.get_or_404(entity_id)
    if request.method == "POST":
        name = request.form["name"].strip()
        if not name:
            flash("Le nom est obligatoire.", "danger")
        else:
            existing = Entity.query.filter(Entity.name == name, Entity.id != entity_id).first()
            if existing:
                flash(f"Une autre entité nommée « {name} » existe déjà.", "danger")
            else:
                entity.name = name
                entity.entity_type = request.form.get("entity_type", "AUTRE")
                entity.account_code = request.form.get("account_code", "").strip() or None
                entity.email = request.form.get("email", "").strip() or None
                entity.is_member = bool(request.form.get("is_member"))
                entity.notes = request.form.get("notes", "").strip() or None
                db.session.commit()
                flash("Entité mise à jour.", "success")
                return redirect(url_for("entities.index"))

    return render_template("entities/form.html", entity=entity, entity_types=ENTITY_TYPES)


@bp.route("/<int:entity_id>/delete", methods=["POST"])
@login_required
def delete(entity_id):
    entity = Entity.query.get_or_404(entity_id)
    count = entity.transactions.count()
    if count > 0:
        flash(
            f"Impossible de supprimer « {entity.name} » : {count} transaction(s) liée(s).",
            "danger",
        )
        return redirect(url_for("entities.index"))
    db.session.delete(entity)
    db.session.commit()
    flash(f"Entité « {entity.name} » supprimée.", "success")
    return redirect(url_for("entities.index"))
