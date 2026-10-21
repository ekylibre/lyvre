import csv
from datetime import datetime
from io import StringIO, BytesIO
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, Response
from flask_login import login_required
from app.extensions import db
from app.models import (
    Entity, HelloAssoOrder, HelloAssoItem, HelloAssoPayment,
    Order, OrderLine, OrderPayment,
    CustomerInvoice, EmailTemplate, Product, WorkTime,
)
from app.models.order import POS_ORDER_STATES
from app.models.customer_invoice import (
    CUSTOMER_INVOICE_STATES, CUSTOMER_INVOICE_PAYMENT_STATES,
)
from app.models.entity import ENTITY_TYPES
from app.models.email_template import (
    MEMBERSHIP_REMINDER_KEY, DEFAULT_REMINDER_SUBJECT, DEFAULT_REMINDER_BODY,
)
from app.services import catalog, external_config
from app.services.helloasso_client import HelloAssoConfigError, from_app_config as helloasso_client
from app.services.helloasso_create import create_membership_for_entity
from app.services.helloasso_sync import sync_helloasso
from app.services.membership_status import build_member_rows, sort_member_rows
from app.services import membership_reminders
from app.services import odoo_partner_update
from app.services.odoo_client import OdooConfigError

bp = Blueprint("entities", __name__, url_prefix="/entities")


def _helloasso_configured():
    from app.services import external_config
    return external_config.is_available("helloasso")


def _smtp_configured():
    return membership_reminders.smtp_configured()


def _odoo_configured():
    return odoo_partner_update.is_configured()


VALID_SORT_BY = ("name", "birthday", "status")


def _parse_member_sort(args):
    sort_by = (args.get("sort_by") or "name").strip().lower()
    if sort_by not in VALID_SORT_BY:
        sort_by = "name"
    sort = (args.get("sort") or "asc").strip().lower()
    if sort not in ("asc", "desc"):
        sort = "asc"
    return sort_by, sort


def _member_rows(args):
    """Construit la liste filtrée + triée des adhérents (partagée liste/export)."""
    q = (args.get("q") or "").strip()
    date_from = _parse_date(args.get("date_from"))
    date_to = _parse_date(args.get("date_to"))
    sort_by, sort = _parse_member_sort(args)

    members_list = _members_query(q).all()
    last_ha, last_pos = _last_membership_dates([m.id for m in members_list])
    members_list = _filter_by_date_range(members_list, last_ha, last_pos, date_from, date_to)

    rows = build_member_rows(members_list, last_ha, last_pos)
    rows = sort_member_rows(rows, sort_by, sort)
    return rows, q, sort_by, sort


@bp.route("/")
@login_required
def index():
    q = (request.args.get("q") or "").strip()
    query = Entity.query.filter(Entity.entity_type != "ADHERENT")
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(Entity.name.ilike(like), Entity.email.ilike(like)))
    entities = query.order_by(Entity.name).all()
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
        q=q,
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
    rows, q, sort_by, sort = _member_rows(request.args)
    return render_template(
        "entities/members.html",
        rows=rows,
        q=q,
        date_from=(request.args.get("date_from") or "").strip(),
        date_to=(request.args.get("date_to") or "").strip(),
        sort_by=sort_by,
        sort=sort,
        helloasso_configured=_helloasso_configured(),
        smtp_configured=_smtp_configured(),
        odoo_configured=_odoo_configured(),
    )


EXPORT_HEADERS = [
    "Nom", "Email", "Adhérent", "Bénévole",
    "Dernière adhésion HelloAsso", "Dernière adhésion POS",
    "Date anniversaire", "Statut", "Couleur", "Notes",
]


def _export_record(row):
    """Transforme une row enrichie en liste de valeurs prêtes à exporter."""
    ha = row["last_ha"]
    pos = row["last_pos"]
    return [
        row["name"],
        row["email"] or "",
        "Oui" if row["is_member"] else "Non",
        "Oui" if row["is_benevole"] else "Non",
        ha.strftime("%d/%m/%Y") if ha else "",
        pos.strftime("%d/%m/%Y") if pos else "",
        row["birthday"].strftime("%d/%m/%Y"),
        row["status"],
        row["color"],
        row["notes"] or "",
    ]


def _render_members_csv(rows):
    output = StringIO()
    writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(EXPORT_HEADERS)
    for row in rows:
        writer.writerow(_export_record(row))
    csv_bytes = output.getvalue().encode("utf-8-sig")
    response = Response(csv_bytes, mimetype="text/csv")
    response.headers["Content-Disposition"] = 'attachment; filename="adherents.csv"'
    return response


def _render_members_xlsx(rows):
    import pandas as pd
    from openpyxl.styles import PatternFill

    records = [_export_record(row) for row in rows]
    df = pd.DataFrame(records, columns=EXPORT_HEADERS)
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Adhérents")
        ws = writer.sheets["Adhérents"]
        # Colore la cellule "Statut" (colonne 8) selon la couleur d'échéance.
        status_col = EXPORT_HEADERS.index("Statut") + 1
        fills = {
            "red": PatternFill("solid", fgColor="F8D7DA"),
            "orange": PatternFill("solid", fgColor="FFF3CD"),
            "green": PatternFill("solid", fgColor="D1E7DD"),
        }
        for i, row in enumerate(rows, start=2):  # ligne 1 = en-têtes
            fill = fills.get(row["color"])
            if fill:
                ws.cell(row=i, column=status_col).fill = fill

    response = Response(
        buf.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response.headers["Content-Disposition"] = 'attachment; filename="adherents.xlsx"'
    return response


@bp.route("/members/export")
@login_required
def members_export():
    fmt = (request.args.get("format") or "csv").strip().lower()
    if fmt == "xls":  # alias legacy -> xlsx
        fmt = "xlsx"
    rows, _, _, _ = _member_rows(request.args)
    if fmt == "xlsx":
        return _render_members_xlsx(rows)
    return _render_members_csv(rows)


@bp.route("/members/bulk-benevole", methods=["POST"])
@login_required
def bulk_benevole():
    """Marque/retire en masse le statut bénévole des adhérents cochés."""
    action = (request.form.get("action") or "").strip().lower()
    if action not in ("set", "unset"):
        flash("Action invalide.", "danger")
        return redirect(url_for("entities.members"))

    selected_ids = [int(i) for i in request.form.getlist("selected") if i.isdigit()]
    redirect_args = {
        k: v for k, v in {
            "q": (request.form.get("q") or "").strip(),
            "date_from": (request.form.get("date_from") or "").strip(),
            "date_to": (request.form.get("date_to") or "").strip(),
            "sort_by": (request.form.get("sort_by") or "").strip(),
            "sort": (request.form.get("sort") or "").strip(),
        }.items() if v
    }

    if not selected_ids:
        flash("Aucun adhérent sélectionné.", "warning")
        return redirect(url_for("entities.members", **redirect_args))

    new_value = action == "set"
    updated = (
        Entity.query
        .filter(Entity.id.in_(selected_ids))
        .update({Entity.is_benevole: new_value}, synchronize_session=False)
    )
    db.session.commit()

    if new_value:
        flash(f"{updated} adhérent(s) marqué(s) bénévole(s).", "success")
    else:
        flash(f"{updated} adhérent(s) retiré(s) des bénévoles.", "success")
    return redirect(url_for("entities.members", **redirect_args))


@bp.route("/members/update-odoo-notes", methods=["POST"])
@login_required
def update_odoo_notes():
    """Met à jour la fiche Odoo (Notes interne) des adhérents cochés."""
    redirect_args = {
        k: v for k, v in {
            "q": (request.form.get("q") or "").strip(),
            "date_from": (request.form.get("date_from") or "").strip(),
            "date_to": (request.form.get("date_to") or "").strip(),
            "sort_by": (request.form.get("sort_by") or "").strip(),
            "sort": (request.form.get("sort") or "").strip(),
        }.items() if v
    }

    if not _odoo_configured():
        flash(external_config.unavailable_message("odoo"), "warning")
        return redirect(url_for("entities.members", **redirect_args))

    selected_ids = {i for i in request.form.getlist("selected") if i.isdigit()}
    if not selected_ids:
        flash("Aucun adhérent sélectionné.", "warning")
        return redirect(url_for("entities.members", **redirect_args))

    rows, _, _, _ = _member_rows(request.form)
    chosen = [
        r for r in rows
        if r["entity"] is not None and str(r["entity"].id) in selected_ids
    ]
    if not chosen:
        flash("Aucun adhérent sélectionné.", "warning")
        return redirect(url_for("entities.members", **redirect_args))

    try:
        result = odoo_partner_update.update_member_notes(chosen)
    except OdooConfigError as e:
        flash(str(e), "warning")
        return redirect(url_for("entities.members", **redirect_args))
    except Exception as e:  # noqa: BLE001 — remonte l'erreur à l'UI
        current_app.logger.exception("Mise à jour notes Odoo échouée")
        flash(f"Erreur Odoo : {e}", "danger")
        return redirect(url_for("entities.members", **redirect_args))

    msg = (
        f"Odoo : {result['updated']} fiche(s) mise(s) à jour, "
        f"{result['skipped']} ignorée(s), {result['errors']} erreur(s)."
    )
    if result["errors"] or result["skipped"]:
        flash(msg + (" Détail : " + " | ".join(result["error_lines"][:5])
                     if result["error_lines"] else ""),
              "warning" if result["updated"] else "danger")
    else:
        flash(msg, "success")
    return redirect(url_for("entities.members", **redirect_args))


@bp.route("/members.csv")
@login_required
def members_csv():
    """Compat : ancien lien d'export CSV."""
    args = request.args.to_dict()
    args["format"] = "csv"
    return redirect(url_for("entities.members_export", **args))


@bp.route("/members/reminders", methods=["GET", "POST"])
@login_required
def members_reminders():
    """Relance email des adhérents expirés (statut rouge)."""
    rows, q, _, _ = _member_rows(request.args)
    targets = membership_reminders.members_to_remind(rows)

    if request.method == "POST":
        if not _smtp_configured():
            flash(external_config.unavailable_message("smtp"), "warning")
            return redirect(url_for("entities.members"))
        # Ne relance que les adhérents cochés dans le sélecteur.
        selected_ids = set(request.form.getlist("selected"))
        chosen = [
            t for t in targets
            if t["entity"] is not None and str(t["entity"].id) in selected_ids
        ]
        if not chosen:
            flash("Aucun adhérent sélectionné.", "warning")
            return redirect(url_for("entities.members_reminders", q=q))
        try:
            result = membership_reminders.send_reminders(chosen)
        except Exception as exc:
            current_app.logger.exception("Relance adhérents échouée")
            flash(f"Erreur lors de l'envoi : {exc}", "danger")
            return redirect(url_for("entities.members"))
        msg = (
            f"Relance : {result['sent']} email(s) envoyé(s), "
            f"{result['errors']} erreur(s)."
        )
        if result["errors"]:
            flash(msg + " Détail : " + " | ".join(result["error_lines"][:5]),
                  "warning" if result["sent"] else "danger")
        else:
            flash(msg, "success")
        return redirect(url_for("entities.members"))

    return render_template(
        "entities/reminder_preview.html",
        targets=targets,
        q=q,
        helloasso_url=membership_reminders.helloasso_renewal_url(),
        smtp_configured=_smtp_configured(),
    )


def _sample_expired_row():
    """Retourne (row, is_real) : un adhérent expiré réel pour l'aperçu, sinon
    un exemple fictif si aucun adhérent n'est en relance."""
    rows, _, _, _ = _member_rows(request.args)
    targets = membership_reminders.members_to_remind(rows)
    if targets:
        return targets[0], True
    from datetime import date, timedelta
    sample = {
        "name": "Jean Dupont",
        "email": "jean.dupont@example.org",
        "birthday": date.today() - timedelta(days=10),
        "status": "ok", "color": "red", "label": "ok", "css": "bg-danger",
        "entity": None,
    }
    return sample, False


@bp.route("/members/reminder-template", methods=["GET", "POST"])
@login_required
def reminder_template():
    """Édition du gabarit d'email de relance (stocké en base) + aperçu HTML."""
    tpl = EmailTemplate.query.filter_by(key=MEMBERSHIP_REMINDER_KEY).first()
    action = request.form.get("action", "save")

    if request.method == "POST" and action == "save":
        subject = (request.form.get("subject") or "").strip()
        body_html = request.form.get("body_html") or ""
        if not subject or not body_html.strip():
            flash("Le sujet et le corps sont obligatoires.", "danger")
        else:
            if tpl is None:
                tpl = EmailTemplate(key=MEMBERSHIP_REMINDER_KEY)
                db.session.add(tpl)
            tpl.subject = subject
            tpl.body_html = body_html
            db.session.commit()
            flash("Gabarit d'email mis à jour.", "success")
            return redirect(url_for("entities.members"))

    # Contenu courant des champs : valeurs soumises (aperçu/échec) sinon en base
    # sinon gabarit par défaut.
    if request.method == "POST":
        cur_subject = request.form.get("subject") or ""
        cur_body = request.form.get("body_html") or ""
    elif tpl is not None:
        cur_subject, cur_body = tpl.subject, tpl.body_html
    else:
        cur_subject, cur_body = DEFAULT_REMINDER_SUBJECT, DEFAULT_REMINDER_BODY

    # Aperçu rendu avec les données d'un adhérent expiré.
    sample_row, sample_is_real = _sample_expired_row()
    helloasso_url = membership_reminders.helloasso_renewal_url()
    preview_tpl = EmailTemplate(
        key=MEMBERSHIP_REMINDER_KEY, subject=cur_subject, body_html=cur_body,
    )
    try:
        preview_subject, preview_body = membership_reminders.render_reminder(
            preview_tpl, sample_row, helloasso_url,
        )
        preview_error = None
    except Exception as exc:  # erreur de syntaxe Jinja dans le gabarit
        preview_subject = preview_body = ""
        preview_error = str(exc)

    return render_template(
        "entities/reminder_template_form.html",
        subject=cur_subject,
        body_html=cur_body,
        preview_subject=preview_subject,
        preview_body=preview_body,
        preview_error=preview_error,
        sample_row=sample_row,
        sample_is_real=sample_is_real,
        helloasso_url=helloasso_url,
    )


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

    # Temps de travaux du bénévole (si rattachés), avec totaux.
    work_times = (
        entity.work_times
        .order_by(WorkTime.work_date.desc(), WorkTime.id.desc())
        .all()
    )
    work_times_total_hours = sum(float(wt.hours) for wt in work_times)
    work_times_total_valuation_cents = sum(wt.valuation_cents for wt in work_times)

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
        work_times=work_times,
        work_times_total_hours=work_times_total_hours,
        work_times_total_valuation_cents=work_times_total_valuation_cents,
        odoo_configured=_odoo_configured(),
    )


@bp.route("/<int:entity_id>/update-odoo-note", methods=["POST"])
@login_required
def update_odoo_note(entity_id):
    """Met à jour la fiche Odoo (Notes interne) d'un seul adhérent."""
    entity = Entity.query.get_or_404(entity_id)
    if not _odoo_configured():
        flash(external_config.unavailable_message("odoo"), "warning")
        return redirect(url_for("entities.detail", entity_id=entity.id))

    last_ha, last_pos = _last_membership_dates([entity.id])
    try:
        ok, message = odoo_partner_update.update_single_member(
            entity, last_ha.get(entity.id), last_pos.get(entity.id),
        )
    except OdooConfigError as e:
        flash(str(e), "warning")
        return redirect(url_for("entities.detail", entity_id=entity.id))
    except Exception as e:  # noqa: BLE001 — remonte l'erreur à l'UI
        current_app.logger.exception("Mise à jour note Odoo échouée")
        flash(f"Erreur Odoo : {e}", "danger")
        return redirect(url_for("entities.detail", entity_id=entity.id))

    flash(message, "success" if ok else "warning")
    return redirect(url_for("entities.detail", entity_id=entity.id))


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
            flash(external_config.unavailable_message("helloasso"), "warning")
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


def _supplier_fields(form) -> dict:
    """Champs fournisseur du formulaire : produit par défaut, TVA, IBAN."""
    product_id = form.get("default_product_id", type=int)
    if product_id is not None and db.session.get(Product, product_id) is None:
        product_id = None
    return {
        "default_product_id": product_id,
        "vat_number": (form.get("vat_number") or "").replace(" ", "").upper()[:30] or None,
        "iban": (form.get("iban") or "").replace(" ", "").upper()[:34] or None,
    }


def _render_form(entity):
    return render_template("entities/form.html", entity=entity, entity_types=ENTITY_TYPES,
                           purchase_products=catalog.purchase_products())


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
                is_benevole=bool(request.form.get("is_benevole")),
                notes=request.form.get("notes", "").strip() or None,
                **_supplier_fields(request.form),
            )
            db.session.add(entity)
            db.session.commit()
            flash(f"Entité « {name} » créée.", "success")
            return redirect(url_for("entities.index"))

    return _render_form(None)


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
                entity.is_benevole = bool(request.form.get("is_benevole"))
                entity.notes = request.form.get("notes", "").strip() or None
                for key, value in _supplier_fields(request.form).items():
                    setattr(entity, key, value)
                db.session.commit()
                flash("Entité mise à jour.", "success")
                return redirect(url_for("entities.index"))

    return _render_form(entity)


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
