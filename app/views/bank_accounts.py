from datetime import date

from flask import (
    Blueprint, abort, current_app, flash, redirect, render_template, request, url_for,
)
from flask_login import login_required
from markupsafe import escape
from app.decorators import admin_required
from app.extensions import db
from app.frontend import is_htmx
from app.models import BankAccount, Account, BankTransaction, Entity, SyncJob
from app.models.sync_job import SYNC_KIND_QONTO
from app.services import counterparties, external_config, qonto_sync
from app.utils.list_filters import (
    parse_sort, parse_month, apply_date_sort, apply_month_filter,
    sort_and_filter_context,
)

bp = Blueprint("bank_accounts", __name__, url_prefix="/bank-accounts")


@bp.route("/")
@login_required
def index():
    bank_accounts = BankAccount.query.order_by(BankAccount.label).all()
    stats = {
        ba.id: {
            "total": ba.transactions.count(),
            "unreconciled": ba.transactions.filter_by(reconciled=False).count(),
        }
        for ba in bank_accounts
    }
    return render_template("bank_accounts/index.html", bank_accounts=bank_accounts, stats=stats)


def _gl_bank_accounts():
    return (
        Account.query
        .filter(Account.code.like("51%"), Account.is_header == False)  # noqa: E712
        .order_by(Account.code)
        .all()
    )


def _parse_date(value):
    try:
        return date.fromisoformat((value or "").strip())
    except ValueError:
        return None


def _qonto_accounts():
    """(comptes Qonto de l'API, message d'erreur) — aucun appel si l'intégration est indisponible."""
    if not external_config.is_available("qonto"):
        return [], None
    from app.services import integrations, qonto_client

    try:
        return qonto_client.from_app_config().bank_accounts(), None
    except Exception as exc:  # noqa: BLE001 — message lisible pour l'écran
        message = integrations.mask_secrets("qonto", integrations.describe_error("qonto", exc))
        return [], message


@bp.route("/qonto")
@login_required
@admin_required
def qonto_accounts():
    accounts, error = _qonto_accounts()
    gl_accounts = _gl_bank_accounts()
    # Par défaut, le premier compte « Banques » (512…) plutôt que la classe 51 elle-même.
    default_gl = next((a for a in gl_accounts if a.code.startswith("512")), None)
    return render_template(
        "bank_accounts/qonto_accounts.html",
        accounts=qonto_sync.list_accounts(accounts),
        error=error,
        gl_accounts=gl_accounts,
        default_gl_id=default_gl.id if default_gl else None,
        unlinked=BankAccount.query.filter(BankAccount.qonto_account_id.is_(None))
        .order_by(BankAccount.label).all(),
        default_sync_from=qonto_sync.default_sync_from(),
    )


@bp.route("/qonto/link", methods=["POST"])
@login_required
@admin_required
def qonto_link():
    accounts, error = _qonto_accounts()
    if error:
        flash(error, "danger")
        return redirect(url_for("bank_accounts.qonto_accounts"))
    qonto_id = request.form.get("qonto_account_id", "")
    qonto_account = next((a for a in accounts if a.get("id") == qonto_id), None)
    if qonto_account is None:
        flash("Compte Qonto introuvable.", "danger")
        return redirect(url_for("bank_accounts.qonto_accounts"))
    sync_from = _parse_date(request.form.get("sync_from"))
    try:
        if request.form.get("mode") == "existing":
            ba = qonto_sync.link_account(
                qonto_account, bank_account_id=request.form.get("bank_account_id", type=int),
                sync_from=sync_from,
            )
        else:
            ba = qonto_sync.link_account(
                qonto_account, label=request.form.get("label"),
                gl_account_id=request.form.get("gl_account_id", type=int), sync_from=sync_from,
            )
    except qonto_sync.QontoLinkError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("bank_accounts.qonto_accounts"))
    flash(f"Compte Qonto rattaché à « {ba.label} » (synchronisation à partir du "
          f"{ba.qonto_sync_from.strftime('%d/%m/%Y')}).", "success")
    return redirect(url_for("bank_accounts.qonto_accounts"))


@bp.route("/<int:ba_id>/qonto/unlink", methods=["POST"])
@login_required
@admin_required
def qonto_unlink(ba_id):
    ba = BankAccount.query.get_or_404(ba_id)
    qonto_sync.unlink_account(ba)
    flash(f"« {ba.label} » n'est plus rattaché à Qonto (transactions conservées).", "success")
    return redirect(url_for("bank_accounts.edit", ba_id=ba.id))


@bp.route("/<int:ba_id>/qonto/settings", methods=["POST"])
@login_required
@admin_required
def qonto_settings(ba_id):
    ba = BankAccount.query.get_or_404(ba_id)
    sync_from = _parse_date(request.form.get("sync_from"))
    if not ba.qonto_account_id or sync_from is None:
        flash("Date de début invalide.", "danger")
    else:
        qonto_sync.set_sync_from(ba, sync_from)
        flash(f"Synchronisation Qonto à partir du {sync_from.strftime('%d/%m/%Y')}.", "success")
    return redirect(url_for("bank_accounts.edit", ba_id=ba.id))


@bp.route("/<int:ba_id>/qonto/sync", methods=["POST"])
@login_required
def qonto_sync_start(ba_id):
    ba = BankAccount.query.get_or_404(ba_id)
    message = None
    if not ba.qonto_account_id:
        message = "Ce compte bancaire n'est pas rattaché à Qonto."
    else:
        message = external_config.unavailable_message("qonto")
    if message:
        if is_htmx():
            return f'<div id="qonto-sync-status" class="alert alert-warning small">{escape(message)}</div>'
        flash(message, "warning")
        return redirect(url_for("bank_accounts.transactions", ba_id=ba.id))
    job = qonto_sync.start_sync(current_app._get_current_object(), ba.id)
    if is_htmx():
        return render_template("bank_accounts/_qonto_sync_status.html", ba=ba, job=job)
    flash("Synchronisation Qonto lancée en arrière-plan.", "info")
    return redirect(url_for("bank_accounts.transactions", ba_id=ba.id))


@bp.route("/<int:ba_id>/qonto/sync/<int:job_id>")
@login_required
def qonto_sync_status(ba_id, job_id):
    ba = BankAccount.query.get_or_404(ba_id)
    job = db.session.get(SyncJob, job_id)
    if job is None or job.kind != SYNC_KIND_QONTO or job.bank_account_id != ba.id:
        abort(404)
    return render_template("bank_accounts/_qonto_sync_status.html", ba=ba, job=job)


@bp.route("/<int:ba_id>/counterparties", methods=["GET", "POST"])
@login_required
def counterparties_view(ba_id):
    ba = BankAccount.query.get_or_404(ba_id)
    if request.method == "POST":
        action = request.form.get("action")
        key = request.form.get("name_key", "")
        label = request.form.get("label", "")
        try:
            if action == "ignore":
                counterparties.ignore(key, label)
                flash(f"« {label} » ne sera plus proposé.", "success")
            elif action == "link":
                entity, n = counterparties.accept(key, entity_id=request.form.get("entity_id", type=int))
                flash(f"{n} transaction(s) rattachée(s) à « {entity.name} ».", "success")
            else:
                entity, n = counterparties.accept(key, create_name=request.form.get("name"))
                flash(f"Fournisseur « {entity.name} » : {n} transaction(s) rattachée(s).", "success")
        except ValueError as exc:
            flash(str(exc), "danger")
        return redirect(url_for("bank_accounts.counterparties_view", ba_id=ba.id))

    return render_template(
        "bank_accounts/counterparties.html",
        ba=ba,
        proposals=counterparties.proposals(ba.id),
        entities=Entity.query.order_by(Entity.name).all(),
    )


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    gl_accounts = (
        Account.query
        .filter(Account.code.like("51%"), Account.is_header == False)
        .order_by(Account.code)
        .all()
    )
    if request.method == "POST":
        label = request.form["label"].strip()
        iban = request.form.get("iban", "").strip().upper().replace(" ", "")
        account_id = request.form.get("account_id", type=int)

        if not label:
            flash("Le libellé est obligatoire.", "danger")
        elif not account_id:
            flash("Le compte GL est obligatoire.", "danger")
        else:
            db.session.add(BankAccount(label=label, iban=iban or None, account_id=account_id))
            db.session.commit()
            flash(f"Compte bancaire « {label} » créé.", "success")
            return redirect(url_for("bank_accounts.index"))

    return render_template("bank_accounts/form.html", bank_account=None, gl_accounts=gl_accounts)


@bp.route("/<int:ba_id>/edit", methods=["GET", "POST"])
@login_required
def edit(ba_id):
    ba = BankAccount.query.get_or_404(ba_id)
    gl_accounts = (
        Account.query
        .filter(Account.code.like("51%"), Account.is_header == False)
        .order_by(Account.code)
        .all()
    )
    if request.method == "POST":
        ba.label = request.form["label"].strip()
        ba.iban = request.form.get("iban", "").strip().upper().replace(" ", "") or None
        ba.account_id = request.form.get("account_id", type=int)
        db.session.commit()
        flash("Compte bancaire mis à jour.", "success")
        return redirect(url_for("bank_accounts.index"))

    return render_template("bank_accounts/form.html", bank_account=ba, gl_accounts=gl_accounts)


@bp.route("/<int:ba_id>/delete", methods=["POST"])
@login_required
def delete(ba_id):
    ba = BankAccount.query.get_or_404(ba_id)
    if ba.transactions.count() > 0:
        flash(
            f"Impossible de supprimer « {ba.label} » : {ba.transactions.count()} transaction(s) associée(s).",
            "danger",
        )
        return redirect(url_for("bank_accounts.index"))
    db.session.delete(ba)
    db.session.commit()
    flash(f"Compte bancaire « {ba.label} » supprimé.", "success")
    return redirect(url_for("bank_accounts.index"))


@bp.route("/<int:ba_id>/transactions")
@login_required
def transactions(ba_id):
    ba = BankAccount.query.get_or_404(ba_id)
    only_unreconciled = request.args.get("unreconciled", "0") == "1"
    only_missing = request.args.get("missing", "0") == "1"
    sort = parse_sort(request.args.get("sort"))
    month_arg = request.args.get("month")
    month_tuple = parse_month(month_arg)

    query = ba.transactions
    if only_unreconciled:
        query = query.filter_by(reconciled=False)
    if only_missing:
        # Justificatif exigé mais absent, ou déclaré perdu (transactions Qonto).
        query = query.filter(db.or_(
            db.and_(BankTransaction.attachment_required.is_(True),
                    BankTransaction.attachment_count == 0),
            BankTransaction.attachment_lost.is_(True),
        ))
    query = apply_month_filter(query, BankTransaction.transaction_date, month_tuple)
    query = apply_date_sort(query, BankTransaction.transaction_date, sort)
    txns = query.all()
    return render_template(
        "bank_accounts/transactions.html",
        ba=ba,
        txns=txns,
        qonto_job=qonto_sync.latest_job(ba.id) if ba.qonto_account_id else None,
        proposal_count=counterparties.count_proposals(ba.id),
        only_unreconciled=only_unreconciled,
        only_missing=only_missing,
        reversed_reconciled=ba.transactions.filter_by(is_reversed=True, reconciled=True).all(),
        **sort_and_filter_context(sort, month_arg),
    )
