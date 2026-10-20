from flask import Blueprint, g, render_template, request, redirect, url_for, flash
from flask_login import login_required
from datetime import date
from app.extensions import db
from app.models import JournalEntry, FiscalYear, Journal, BankTransaction
from app.services.ledger import delete_entries, entry_is_reconciled
from app.utils.list_filters import (
    parse_sort, parse_month, apply_date_sort, apply_month_filter,
    sort_and_filter_context,
)

bp = Blueprint("entries", __name__, url_prefix="/entries")


@bp.route("/")
@login_required
def index():
    fy_id = request.args.get("fy_id", type=int)
    journal_id = request.args.get("journal_id", type=int)
    q = (request.args.get("q") or "").strip()
    sort = parse_sort(request.args.get("sort"))
    month_arg = request.args.get("month")
    month_tuple = parse_month(month_arg)

    fiscal_years = FiscalYear.query.order_by(FiscalYear.start_date.desc()).all()
    journals = Journal.query.order_by(Journal.code).all()
    active_fy = FiscalYear.query.filter_by(closed=False).order_by(FiscalYear.start_date.desc()).first()

    if fy_id is None and active_fy:
        fy_id = active_fy.id

    query = JournalEntry.query
    if fy_id:
        query = query.filter_by(fiscal_year_id=fy_id)
    if journal_id:
        query = query.filter_by(journal_id=journal_id)
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(
            JournalEntry.reference.ilike(like),
            JournalEntry.description.ilike(like),
        ))
    query = apply_month_filter(query, JournalEntry.entry_date, month_tuple)
    query = apply_date_sort(query, JournalEntry.entry_date, sort)
    entries = query.order_by(JournalEntry.id.desc()).all()

    return render_template(
        "entries/index.html",
        entries=entries,
        fiscal_years=fiscal_years,
        journals=journals,
        selected_fy_id=fy_id,
        selected_journal_id=journal_id,
        q=q,
        **sort_and_filter_context(sort, month_arg),
    )


def _account_json(account):
    return {"id": account.id, "code": account.code, "label": account.label}


def api_base_url():
    """Base de l'API (/api/v1), déduite d'une de ses routes."""
    return url_for("api.session_info").rsplit("/", 1)[0]


def entry_form_options():
    """Options partagées par les îlots qui embarquent EntryForm."""
    fiscal_years = (
        FiscalYear.query.filter_by(closed=False).order_by(FiscalYear.start_date.desc()).all()
    )
    instance = getattr(g, "current_instance", None)
    return {
        "fiscalYears": [
            {"id": fy.id, "label": fy.label,
             "start_date": fy.start_date.isoformat(), "end_date": fy.end_date.isoformat()}
            for fy in fiscal_years
        ],
        "journals": [
            {"id": j.id, "code": j.code, "label": j.label}
            for j in Journal.query.order_by(Journal.code).all()
        ],
        "recentsScope": instance.slug if instance else "default",
    }


def _form_props(mode, initial, *, entry=None, bank_transaction=None, cancel_url, after_save=None):
    """Props of the EntryForm island (frontend/src/islands/EntryForm)."""
    props = {
        "mode": mode,
        **entry_form_options(),
        "initial": initial,
        "urls": {"api": api_base_url(), "cancel": cancel_url},
    }
    if after_save:
        props["urls"]["afterSave"] = after_save
    if entry is not None:
        props["entryId"] = entry.id
        props["reference"] = entry.reference
    if bank_transaction is not None:
        props["bankTransaction"] = {
            "id": bank_transaction.id,
            "date": bank_transaction.transaction_date.isoformat(),
            "label": bank_transaction.label or "",
            "amount_cents": bank_transaction.amount_cents,
        }
    return props


def _default_fiscal_year(on_date):
    open_years = FiscalYear.query.filter_by(closed=False).order_by(FiscalYear.start_date.desc()).all()
    return next((fy for fy in open_years if fy.start_date <= on_date <= fy.end_date),
                open_years[0] if open_years else None)


@bp.route("/new")
@login_required
def new():
    """Saisie d'une écriture (îlot React EntryForm, enregistrement via /api/v1)."""
    bt_id = request.args.get("bt_id", type=int)
    bt = db.session.get(BankTransaction, bt_id) if bt_id else None
    if bt is not None and bt.reconciled:
        flash("Cette transaction bancaire est déjà rapprochée.", "warning")
        return redirect(url_for("reconciliation.index", bank_account_id=bt.bank_account_id))

    journals = Journal.query.order_by(Journal.code).all()
    if bt is None:
        today = date.today()
        fy = _default_fiscal_year(today)
        initial = {
            "fiscal_year_id": fy.id if fy else None,
            "journal_id": journals[0].id if journals else None,
            "entry_date": today.isoformat(),
            "description": "",
            "lines": [],
        }
        props = _form_props("create", initial, cancel_url=url_for("entries.index"))
    else:
        fy = _default_fiscal_year(bt.transaction_date)
        bq = next((j for j in journals if j.code == "BQ"), journals[0] if journals else None)
        amount = abs(bt.amount_cents)
        inflow = bt.amount_cents >= 0
        initial = {
            "fiscal_year_id": fy.id if fy else None,
            "journal_id": bq.id if bq else None,
            "entry_date": bt.transaction_date.isoformat(),
            "description": bt.label or "",
            "lines": [{
                "account": _account_json(bt.bank_account.account),
                "label": bt.label or "",
                "debit_cents": amount if inflow else 0,
                "credit_cents": 0 if inflow else amount,
            }],
        }
        back = url_for("reconciliation.index", bank_account_id=bt.bank_account_id)
        props = _form_props("create", initial, bank_transaction=bt,
                            cancel_url=back, after_save=back)
    return render_template("entries/form.html", props=props, entry=None, bank_transaction=bt)


@bp.route("/<int:entry_id>")
@login_required
def detail(entry_id):
    entry = JournalEntry.query.get_or_404(entry_id)
    return render_template("entries/detail.html", entry=entry)


@bp.route("/<int:entry_id>/edit")
@login_required
def edit(entry_id):
    """Modification d'une écriture (îlot React EntryForm, enregistrement via /api/v1)."""
    entry = JournalEntry.query.get_or_404(entry_id)
    if entry.fiscal_year.closed:
        flash("Impossible de modifier une écriture d'un exercice clôturé.", "danger")
        return redirect(url_for("entries.detail", entry_id=entry_id))
    if entry_is_reconciled(entry):
        flash(
            "Cette écriture est rapprochée à une transaction bancaire. "
            "Annulez le rapprochement avant de la modifier.",
            "danger",
        )
        return redirect(url_for("entries.detail", entry_id=entry_id))

    initial = {
        "fiscal_year_id": entry.fiscal_year_id,
        "journal_id": entry.journal_id,
        "entry_date": entry.entry_date.isoformat(),
        "description": entry.description or "",
        "lines": [
            {"account": _account_json(l.account), "label": l.label or "",
             "debit_cents": l.debit_cents, "credit_cents": l.credit_cents}
            for l in entry.lines
        ],
    }
    props = _form_props("edit", initial, entry=entry,
                        cancel_url=url_for("entries.detail", entry_id=entry.id))
    return render_template("entries/form.html", props=props, entry=entry, bank_transaction=None)


@bp.route("/<int:entry_id>/delete", methods=["POST"])
@login_required
def delete(entry_id):
    JournalEntry.query.get_or_404(entry_id)
    result = delete_entries([entry_id])[0]
    if result["status"] != "ok":
        flash(f"Impossible de supprimer l'écriture : {result['message']}", "danger")
        return redirect(url_for("entries.detail", entry_id=entry_id))
    flash(f"Écriture {result['reference']} supprimée.", "success")
    return redirect(url_for("entries.index"))
