from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from datetime import date
from app.extensions import db
from app.models import JournalEntry, JournalLine, FiscalYear, Journal, Account, BankTransaction
from app.services.ledger import post_entry, validate_lines, LedgerError
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


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    from types import SimpleNamespace
    from app.services.reconciler import reconcile
    fiscal_years = FiscalYear.query.filter_by(closed=False).order_by(FiscalYear.start_date.desc()).all()
    journals = Journal.query.order_by(Journal.code).all()

    bt_id = request.values.get("bt_id", type=int)
    bt = BankTransaction.query.get(bt_id) if bt_id else None

    if request.method == "POST":
        try:
            fy_id = int(request.form["fiscal_year_id"])
            journal_id = int(request.form["journal_id"])
            entry_date = date.fromisoformat(request.form["entry_date"])
            description = request.form.get("description", "").strip()

            account_ids = request.form.getlist("account_id[]")
            labels = request.form.getlist("line_label[]")
            debits = request.form.getlist("debit[]")
            credits = request.form.getlist("credit[]")

            lines = []
            for acc_id, lbl, deb, crd in zip(account_ids, labels, debits, credits):
                if not acc_id:
                    continue
                debit_cents = int(round(float(deb or 0) * 100))
                credit_cents = int(round(float(crd or 0) * 100))
                lines.append({
                    "account_id": int(acc_id),
                    "label": lbl,
                    "debit_cents": debit_cents,
                    "credit_cents": credit_cents,
                })

            entry = post_entry(fy_id, journal_id, entry_date, description, lines)

            if bt and not bt.journal_line_id:
                bank_line = next(
                    (l for l in entry.lines if l.account_id == bt.bank_account.account_id),
                    None,
                )
                if bank_line:
                    reconcile(bt.id, bank_line.id)
                    flash(
                        f"Écriture {entry.reference} créée et transaction bancaire rapprochée.",
                        "success",
                    )
                    return redirect(url_for(
                        "reconciliation.index", bank_account_id=bt.bank_account_id
                    ))

            flash(f"Écriture {entry.reference} créée.", "success")
            return redirect(url_for("entries.detail", entry_id=entry.id))

        except LedgerError as e:
            flash(str(e), "danger")
        except (ValueError, KeyError) as e:
            flash(f"Données invalides : {e}", "danger")

    prefill = None
    if bt:
        bq = Journal.query.filter_by(code="BQ").first()
        fy_match = next(
            (fy for fy in fiscal_years
             if fy.start_date <= bt.transaction_date <= fy.end_date),
            None,
        )
        amount = abs(bt.amount_cents)
        is_inflow = bt.amount_cents >= 0
        gl = bt.bank_account.account
        bank_line = SimpleNamespace(
            account=SimpleNamespace(id=gl.id, code=gl.code, label=gl.label),
            label=bt.label or "",
            debit_cents=amount if is_inflow else 0,
            credit_cents=0 if is_inflow else amount,
        )
        prefill = SimpleNamespace(
            entry_date=bt.transaction_date,
            description=bt.label or "",
            fiscal_year_id=fy_match.id if fy_match else None,
            journal_id=bq.id if bq else None,
            lines=[bank_line, None],  # bank line + empty placeholder for counterpart
            bank_transaction=bt,
        )

    return render_template(
        "entries/form.html",
        fiscal_years=fiscal_years,
        journals=journals,
        prefill=prefill,
        bt_id=bt_id,
    )


@bp.route("/<int:entry_id>")
@login_required
def detail(entry_id):
    entry = JournalEntry.query.get_or_404(entry_id)
    return render_template("entries/detail.html", entry=entry)


@bp.route("/<int:entry_id>/edit", methods=["GET", "POST"])
@login_required
def edit(entry_id):
    entry = JournalEntry.query.get_or_404(entry_id)

    if entry.fiscal_year.closed:
        flash("Impossible de modifier une écriture d'un exercice clôturé.", "danger")
        return redirect(url_for("entries.detail", entry_id=entry_id))

    fiscal_years = FiscalYear.query.filter_by(closed=False).order_by(FiscalYear.start_date.desc()).all()
    journals = Journal.query.order_by(Journal.code).all()

    if request.method == "POST":
        line_ids = [l.id for l in entry.lines]
        linked = (
            BankTransaction.query.filter(BankTransaction.journal_line_id.in_(line_ids)).first()
            if line_ids else None
        )
        if linked:
            flash(
                "Cette écriture est rapprochée à une transaction bancaire. "
                "Annulez le rapprochement avant de la modifier.",
                "danger",
            )
            return redirect(url_for("entries.detail", entry_id=entry_id))

        try:
            fy_id = int(request.form["fiscal_year_id"])
            journal_id = int(request.form["journal_id"])
            entry_date = date.fromisoformat(request.form["entry_date"])
            description = request.form.get("description", "").strip()

            account_ids = request.form.getlist("account_id[]")
            labels = request.form.getlist("line_label[]")
            debits = request.form.getlist("debit[]")
            credits = request.form.getlist("credit[]")

            new_lines = []
            for acc_id, lbl, deb, crd in zip(account_ids, labels, debits, credits):
                if not acc_id:
                    continue
                new_lines.append({
                    "account_id": int(acc_id),
                    "label": lbl,
                    "debit_cents": int(round(float(deb or 0) * 100)),
                    "credit_cents": int(round(float(crd or 0) * 100)),
                })

            validate_lines(new_lines)

            new_fy = FiscalYear.query.get(fy_id)
            if new_fy is None:
                raise LedgerError("Exercice introuvable.")
            if new_fy.closed:
                raise LedgerError(f"L'exercice « {new_fy.label} » est clôturé.")

            for line in list(entry.lines):
                db.session.delete(line)
            db.session.flush()

            entry.fiscal_year_id = fy_id
            entry.journal_id = journal_id
            entry.entry_date = entry_date
            entry.description = description
            entry.is_balanced = True

            for l in new_lines:
                db.session.add(JournalLine(
                    entry_id=entry.id,
                    account_id=l["account_id"],
                    label=l.get("label", ""),
                    debit_cents=l["debit_cents"],
                    credit_cents=l["credit_cents"],
                ))

            db.session.commit()
            flash(f"Écriture {entry.reference} modifiée.", "success")
            return redirect(url_for("entries.detail", entry_id=entry.id))

        except LedgerError as e:
            db.session.rollback()
            flash(str(e), "danger")
        except (ValueError, KeyError) as e:
            db.session.rollback()
            flash(f"Données invalides : {e}", "danger")

    return render_template("entries/form.html", fiscal_years=fiscal_years, journals=journals, entry=entry)


@bp.route("/<int:entry_id>/delete", methods=["POST"])
@login_required
def delete(entry_id):
    entry = JournalEntry.query.get_or_404(entry_id)
    if entry.fiscal_year.closed:
        flash("Impossible de supprimer une écriture d'un exercice clôturé.", "danger")
        return redirect(url_for("entries.detail", entry_id=entry_id))
    db.session.delete(entry)
    db.session.commit()
    flash("Écriture supprimée.", "success")
    return redirect(url_for("entries.index"))


@bp.route("/new-line")
@login_required
def new_line():
    """HTMX: returns a new empty line row for the entry form."""
    index = request.args.get("index", 0, type=int)
    return render_template("entries/_line_row.html", index=index, line=None)
