from datetime import date

from flask import (
    Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, url_for,
)
from flask_login import login_required
from markupsafe import escape

from app.decorators import admin_required
from app.extensions import db
from app.frontend import is_htmx
from app.models import Account, Entity, Purchase, PurchasePayment, SyncJob
from app.models.purchase import PURCHASE_SOURCES
from app.models.sync_job import SYNC_KIND_QONTO_INVOICES
from app.services import (
    attachments, catalog, counterparties, external_config, purchase_entry, purchase_posting,
    purchase_settlement, purchase_sync,
)
from app.services.attachments import AttachmentError
from app.services.ledger import LedgerError
from app.services.purchase_posting import STATE_LABELS, purchase_state
from app.services.purchase_sync import STATUS_LABELS
from app.utils.list_filters import (
    apply_date_sort, apply_month_filter, parse_month, parse_sort, sort_and_filter_context,
)

bp = Blueprint("purchases", __name__, url_prefix="/purchases")


@bp.route("/")
@login_required
def index():
    q = (request.args.get("q") or "").strip()
    source = (request.args.get("source") or "").strip()
    status = (request.args.get("status") or "").strip()
    state = (request.args.get("state") or "").strip()
    entity_id = request.args.get("entity_id", type=int)
    unpaid = request.args.get("unpaid") == "1"
    no_supplier = request.args.get("no_supplier") == "1"
    show_hidden = request.args.get("hidden") == "1"
    sort = parse_sort(request.args.get("sort"))
    month_arg = request.args.get("month")

    query = Purchase.query
    if not show_hidden:
        query = query.filter(Purchase.is_hidden.is_(False))
    if source in PURCHASE_SOURCES:
        query = query.filter(Purchase.source == source)
    if status:
        query = query.filter(Purchase.qonto_status == status)
    if entity_id:
        query = query.filter(Purchase.entity_id == entity_id)
    if unpaid:
        # Non réglée : ni payée selon Qonto, ni règlement comptabilisé dans l'application.
        settled = (db.session.query(PurchasePayment.purchase_id)
                   .filter(PurchasePayment.journal_entry_id.isnot(None)))
        query = query.filter(db.or_(Purchase.qonto_status.is_(None), Purchase.qonto_status != "paid"),
                             Purchase.id.notin_(settled))
    if no_supplier:
        query = query.filter(Purchase.entity_id.is_(None))
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(db.or_(db.func.lower(Purchase.invoice_number).like(like),
                                    db.func.lower(Purchase.supplier_name).like(like)))
    query = apply_month_filter(query, Purchase.issue_date, parse_month(month_arg))
    query = apply_date_sort(query, Purchase.issue_date, sort)
    purchases = query.order_by(Purchase.id.desc()).limit(500).all()
    states = {p.id: purchase_state(p) for p in purchases}
    if state in STATE_LABELS:
        purchases = [p for p in purchases if states[p.id].code == state]

    suppliers = (Entity.query.join(Purchase, Purchase.entity_id == Entity.id)
                 .distinct().order_by(Entity.name).all())
    return render_template(
        "purchases/index.html",
        purchases=purchases, states=states, suppliers=suppliers, status_labels=STATUS_LABELS,
        state_labels=STATE_LABELS, state=state,
        to_complete=purchase_posting.count_to_complete(),
        to_review=Purchase.query.filter(Purchase.review_reason.isnot(None)).count(),
        to_replace=sum(r.replaceable for r in purchase_settlement.to_replace()),
        supplier_proposals=counterparties.count_invoice_proposals(),
        q=q, source=source, status=status, entity_id=entity_id, unpaid=unpaid, no_supplier=no_supplier,
        show_hidden=show_hidden,
        hidden_count=Purchase.query.filter(Purchase.is_hidden.is_(True)).count(),
        without_supplier=Purchase.query.filter(Purchase.entity_id.is_(None),
                                               Purchase.is_hidden.is_(False)).count(),
        cursor=purchase_sync.cursor_row(), sync_from=purchase_sync.sync_from_date(),
        job=purchase_sync.latest_job(),
        **sort_and_filter_context(sort, month_arg),
    )


@bp.route("/sync", methods=["POST"])
@login_required
def sync():
    message = external_config.unavailable_message("qonto")
    if message:
        if is_htmx():
            return f'<div id="purchase-sync-status" class="alert alert-warning small">{escape(message)}</div>'
        flash(message, "warning")
        return redirect(url_for("purchases.index"))
    job = purchase_sync.start_sync(current_app._get_current_object())
    if is_htmx():
        return render_template("purchases/_sync_status.html", job=job)
    flash("Synchronisation des factures Qonto lancée en arrière-plan.", "info")
    return redirect(url_for("purchases.index"))


@bp.route("/sync/<int:job_id>")
@login_required
def sync_status(job_id):
    job = db.session.get(SyncJob, job_id)
    if job is None or job.kind != SYNC_KIND_QONTO_INVOICES:
        abort(404)
    return render_template("purchases/_sync_status.html", job=job)


@bp.route("/sync/settings", methods=["POST"])
@login_required
@admin_required
def sync_settings():
    try:
        sync_from = date.fromisoformat(request.form.get("sync_from") or "")
    except ValueError:
        flash("Date de début invalide.", "danger")
        return redirect(url_for("purchases.index"))
    purchase_sync.set_sync_from(sync_from)
    flash(f"Factures Qonto synchronisées à partir du {sync_from.strftime('%d/%m/%Y')}.", "success")
    return redirect(url_for("purchases.index"))


def _rows(form):
    """Lignes du formulaire de la fiche (champs répétés)."""
    keys = ("product_id", "account_code", "label", "untaxed", "vat_rate", "vat")
    columns = [form.getlist(f"{key}[]") for key in keys]
    return [dict(zip(keys, values)) for values in zip(*columns)]


def _charge_accounts():
    return (Account.query.filter(Account.code.like("6%"), Account.is_header.is_(False))
            .order_by(Account.code).all())


@bp.route("/<int:purchase_id>")
@login_required
def detail(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)
    fy = purchase_posting.fiscal_year_for(purchase.issue_date)
    return render_template(
        "purchases/detail.html", purchase=purchase, state=purchase_state(purchase),
        fiscal_year=fy, status_labels=STATUS_LABELS, products=catalog.purchase_products(),
        charge_accounts=_charge_accounts(), rows=purchase_entry.line_rows(purchase.lines),
        suggestions=(purchase_settlement.match_candidates(purchase)
                     if purchase_settlement.awaiting_payment(purchase) else []),
        awaiting_payment=purchase_settlement.awaiting_payment(purchase),
        match_window=purchase_settlement.match_window(purchase) if purchase.issue_date else None,
        qonto_upload=purchase_entry.qonto_upload_available(),
        can_send=purchase_entry.can_send_to_qonto(purchase),
    )


@bp.route("/<int:purchase_id>/payments", methods=["POST"])
@login_required
def link_payment(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)
    try:
        outcome = purchase_settlement.link_manual(
            purchase, request.form.get("bank_transaction_id", type=int))
    except LedgerError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("purchases.detail", purchase_id=purchase.id))
    if outcome["settled"]:
        flash("Règlement passé et rapproché.", "success")
    elif not outcome["errors"]:
        flash("Paiement rattaché : la transaction est déjà passée par une règle, "
              "remplacez son écriture (Règlements à remplacer).", "warning")
    for error in outcome["errors"]:
        flash(error, "danger")
    return redirect(url_for("purchases.detail", purchase_id=purchase.id))


@bp.route("/<int:purchase_id>/payments/<int:payment_id>/delete", methods=["POST"])
@login_required
def unlink_payment(purchase_id, payment_id):
    payment = PurchasePayment.query.filter_by(id=payment_id, purchase_id=purchase_id).first_or_404()
    try:
        purchase_settlement.unlink(payment)
        flash("Règlement défait : l'écriture est supprimée et la transaction n'est plus rapprochée.",
              "success")
    except LedgerError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("purchases.detail", purchase_id=purchase_id))


# ------------------------------------------------------------------ saisie

def _render_entry(form=None, purchase=None, token=None, errors=(), duplicates=(), preview=None):
    preview_url = preview_mime = None
    if token:
        preview_url = url_for("purchases.staged", token=token)
        preview_mime = preview
    elif purchase is not None and purchase.attachment_path:
        preview_url = url_for("purchases.attachment", purchase_id=purchase.id)
        preview_mime = purchase.attachment_mime
    return render_template(
        "purchases/new.html", form=form, purchase=purchase, token=token, errors=list(errors),
        duplicates=list(duplicates), preview_url=preview_url, preview_mime=preview_mime,
        entities=Entity.query.order_by(Entity.name).all(), products=catalog.purchase_products(),
        charge_accounts=_charge_accounts(), qonto_upload=purchase_entry.qonto_upload_available(),
    )


def _posted_message(p, outcome, verb):
    kind = "Avoir" if p.is_credit_note else "Facture"
    if outcome["posted"]:
        flash(f"{kind} {verb} et comptabilisé{'' if p.is_credit_note else 'e'}.", "success")
    else:
        flash(f"{kind} {verb}.", "success")
    for error in outcome["errors"]:
        flash(error, "danger")


def _check_duplicates(clean, exclude_id=None):
    if request.form.get("confirm_duplicate"):
        return []
    entity = purchase_entry.chosen_supplier(clean)
    return purchase_entry.duplicates(
        entity.id if entity else None, clean["invoice_number"], clean["issue_date"],
        clean["total_cents"], supplier_name=clean["new_name"] or clean["supplier_name"],
        exclude_id=exclude_id)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    if request.method == "GET":
        return _render_entry(purchase_entry.EntryForm() if request.args.get("manual") else None)

    if request.form.get("step") == "read":
        try:
            token = attachments.stage(request.files.get("invoice_file"))
        except AttachmentError as exc:
            flash(str(exc), "danger")
            return _render_entry()
        _, meta = attachments.staged(token)
        form = purchase_entry.form_from_extraction(purchase_entry.read_staged(token))
        db.session.commit()  # produit « Achats divers » créé au besoin pour les lignes proposées
        return _render_entry(form, token=token, preview=meta["mime"])

    token = request.form.get("token") or None
    form = purchase_entry.EntryForm(values=request.form.to_dict(), rows=_rows(request.form),
                                    source=request.form.get("source", "none"))
    clean, errors = purchase_entry.validate_header(request.form)
    preview = None
    if token:
        try:
            preview = attachments.staged(token)[1]["mime"]
        except AttachmentError as exc:
            errors.append(str(exc))
            token = None
    dups = [] if errors else _check_duplicates(clean)
    if errors or dups:
        return _render_entry(form, token=token, errors=errors, duplicates=dups, preview=preview)
    try:
        purchase, outcome = purchase_entry.create(clean, _rows(request.form), token)
    except (LedgerError, AttachmentError) as exc:
        db.session.rollback()
        return _render_entry(form, token=token, errors=[str(exc)], preview=preview)
    _posted_message(purchase, outcome, "enregistré" if purchase.is_credit_note else "enregistrée")
    if request.form.get("send_to_qonto") and token and purchase_entry.qonto_upload_available():
        _upload_message(purchase, purchase_entry.send_to_qonto(purchase))
    return redirect(url_for("purchases.detail", purchase_id=purchase.id))


def _upload_message(purchase, sent):
    if sent:
        flash("Facture déposée dans Qonto.", "success")
    else:
        flash(f"Envoi à Qonto en échec : {purchase.qonto_upload_error} — utilisez « Renvoyer à Qonto ».",
              "danger")


@bp.route("/<int:purchase_id>/qonto", methods=["POST"])
@login_required
def send_to_qonto(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)
    message = external_config.unavailable_message("qonto")
    if message:
        flash(message, "warning")
    elif not purchase_entry.can_send_to_qonto(purchase):
        flash("Cette facture ne peut pas être envoyée à Qonto (pièce absente ou déjà envoyée).",
              "warning")
    else:
        _upload_message(purchase, purchase_entry.send_to_qonto(purchase))
    return redirect(url_for("purchases.detail", purchase_id=purchase.id))


@bp.route("/<int:purchase_id>/edit", methods=["GET", "POST"])
@login_required
def edit(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)
    if purchase.source != "manual" or purchase.journal_entry_id is not None:
        flash("Seule une facture saisie et non comptabilisée se modifie.", "warning")
        return redirect(url_for("purchases.detail", purchase_id=purchase.id))
    if request.method == "GET":
        form = purchase_entry.EntryForm(values=purchase_entry.header_values(purchase))
        return _render_entry(form, purchase=purchase)

    form = purchase_entry.EntryForm(values=request.form.to_dict())
    clean, errors = purchase_entry.validate_header(request.form)
    token = None
    upload = request.files.get("invoice_file")
    if upload is not None and upload.filename and not errors:
        try:
            token = attachments.stage(upload)
        except AttachmentError as exc:
            errors.append(str(exc))
    dups = [] if errors else _check_duplicates(clean, exclude_id=purchase.id)
    if errors or dups:
        return _render_entry(form, purchase=purchase, errors=errors, duplicates=dups)
    try:
        outcome = purchase_entry.update(purchase, clean, token)
    except (LedgerError, AttachmentError) as exc:
        db.session.rollback()
        return _render_entry(form, purchase=purchase, errors=[str(exc)])
    _posted_message(purchase, outcome, "modifié" if purchase.is_credit_note else "modifiée")
    return redirect(url_for("purchases.detail", purchase_id=purchase.id))


@bp.route("/<int:purchase_id>/attachment")
@login_required
def attachment(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)
    path = attachments.path_of(purchase)
    if path is None:
        abort(404)
    return send_file(path, mimetype=purchase.attachment_mime,
                     as_attachment=bool(request.args.get("download")),
                     download_name=purchase.attachment_name or path.name)


@bp.route("/staged/<token>")
@login_required
def staged(token):
    try:
        path, meta = attachments.staged(token)
    except AttachmentError:
        abort(404)
    return send_file(path, mimetype=meta["mime"], download_name=meta["name"])


@bp.route("/<int:purchase_id>/lines", methods=["POST"])
@login_required
def save_lines(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)
    try:
        outcome = purchase_posting.save_lines(purchase, _rows(request.form))
    except LedgerError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("purchases.detail", purchase_id=purchase.id))
    if outcome["posted"]:
        flash("Lignes enregistrées, facture comptabilisée.", "success")
    else:
        flash("Lignes enregistrées.", "success")
    for error in outcome["errors"]:
        flash(error, "danger")
    return redirect(url_for("purchases.detail", purchase_id=purchase.id))


@bp.route("/<int:purchase_id>/post", methods=["POST"])
@login_required
def post(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)
    outcome = purchase_posting.post_ready([purchase])
    if outcome["posted"]:
        flash("Facture comptabilisée.", "success")
    for error in outcome["errors"] or ([] if outcome["posted"] else
                                       [" ".join(purchase_state(purchase).reasons)]):
        flash(error, "danger")
    return redirect(url_for("purchases.detail", purchase_id=purchase.id))


@bp.route("/<int:purchase_id>/unpost", methods=["POST"])
@login_required
def unpost(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)
    try:
        purchase_posting.unpost(purchase)
        flash("Comptabilisation annulée : l'écriture d'achat est supprimée.", "success")
    except LedgerError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("purchases.detail", purchase_id=purchase.id))


@bp.route("/<int:purchase_id>/delete", methods=["POST"])
@login_required
def delete(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)
    label = f"{'Avoir' if purchase.is_credit_note else 'Facture'} {purchase.invoice_number or 'sans numéro'}"
    try:
        reference = purchase_posting.delete(purchase)
    except LedgerError as exc:
        db.session.rollback()
        flash(f"{label} : {exc}", "danger")
        return redirect(url_for("purchases.index"))
    flash(f"{label} supprimée" + (f", ainsi que son écriture {reference}." if reference else "."), "success")
    return redirect(url_for("purchases.index"))


@bp.route("/post-ready", methods=["POST"])
@login_required
def post_ready():
    outcome = purchase_posting.post_ready(purchase_posting.ready_purchases())
    flash(f"{outcome['posted']} facture(s) comptabilisée(s).", "success")
    for error in outcome["errors"][:10]:
        flash(error, "danger")
    return redirect(url_for("purchases.index"))


@bp.route("/settlements")
@login_required
def settlements():
    rows = purchase_settlement.to_replace()
    return render_template("purchases/settlements.html",
                           replaceable=[r for r in rows if r.replaceable],
                           manual=[r for r in rows if not r.replaceable])


@bp.route("/settlements/replace", methods=["POST"])
@login_required
def replace_settlements():
    ids = [int(i) for i in request.form.getlist("transaction_ids") if i.isdigit()]
    if not ids:
        flash("Aucune transaction sélectionnée.", "warning")
        return redirect(url_for("purchases.settlements"))
    outcome = purchase_settlement.replace_many(ids)
    if outcome["counters"]["ok"]:
        flash(f"{outcome['counters']['ok']} écriture(s) de règle remplacée(s) par un règlement "
              "fournisseur.", "success")
    for row in outcome["results"]:
        if row["status"] == "error":
            flash(f"Transaction {row['id']} : {row['message']}", "danger")
    return redirect(url_for("purchases.settlements"))


@bp.route("/suppliers", methods=["GET", "POST"])
@login_required
def suppliers():
    if request.method == "POST":
        action = request.form.get("action")
        key = request.form.get("name_key", "")
        label = request.form.get("label", "")
        try:
            if action == "ignore":
                counterparties.ignore(key, label)
                flash(f"« {label} » ne sera plus proposé.", "success")
            else:
                if action == "link":
                    entity, n_txn, n_inv = counterparties.accept(
                        key, entity_id=request.form.get("entity_id", type=int))
                else:
                    entity, n_txn, n_inv = counterparties.accept(
                        key, create_name=request.form.get("name"))
                flash(f"« {entity.name} » : {n_inv} facture(s) et {n_txn} transaction(s) rattachée(s).",
                      "success")
        except ValueError as exc:
            flash(str(exc), "danger")
        return redirect(url_for("purchases.suppliers"))
    return render_template("purchases/suppliers.html",
                           proposals=counterparties.invoice_proposals(),
                           entities=Entity.query.order_by(Entity.name).all())
