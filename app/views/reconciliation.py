from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from app.models import BankAccount, BankTransaction, JournalLine
from app.services.reconciler import reconcile, unreconcile, suggest_matches, auto_reconcile

bp = Blueprint("reconciliation", __name__, url_prefix="/reconciliation")


@bp.route("/")
@login_required
def index():
    bank_accounts = BankAccount.query.order_by(BankAccount.label).all()
    selected_id = request.args.get("bank_account_id", type=int)
    if selected_id is None and bank_accounts:
        selected_id = bank_accounts[0].id

    unreconciled = []
    if selected_id:
        unreconciled = (
            BankTransaction.query.filter_by(bank_account_id=selected_id, reconciled=False)
            .order_by(BankTransaction.transaction_date.desc())
            .all()
        )

    return render_template(
        "reconciliation/index.html",
        bank_accounts=bank_accounts,
        selected_id=selected_id,
        unreconciled=unreconciled,
    )


@bp.route("/suggest/<int:bt_id>")
@login_required
def suggest(bt_id):
    """HTMX: returns candidate journal lines for a bank transaction."""
    matches = suggest_matches(bt_id)
    bt = BankTransaction.query.get_or_404(bt_id)
    return render_template("reconciliation/_suggestions.html", bt=bt, matches=matches)


@bp.route("/link", methods=["POST"])
@login_required
def link():
    bt_id = request.form.get("bank_transaction_id", type=int)
    line_id = request.form.get("journal_line_id", type=int)
    reconcile(bt_id, line_id)
    flash("Transaction rapprochée.", "success")
    bank_account_id = BankTransaction.query.get(bt_id).bank_account_id
    return redirect(url_for("reconciliation.index", bank_account_id=bank_account_id))


@bp.route("/unlink/<int:bt_id>", methods=["POST"])
@login_required
def unlink(bt_id):
    bt = unreconcile(bt_id)
    flash("Rapprochement annulé.", "info")
    return redirect(url_for("reconciliation.index", bank_account_id=bt.bank_account_id))


@bp.route("/auto", methods=["POST"])
@login_required
def auto():
    bank_account_id = request.form.get("bank_account_id", type=int)
    count = auto_reconcile(bank_account_id)
    flash(f"{count} transaction(s) rapprochée(s) automatiquement.", "success")
    return redirect(url_for("reconciliation.index", bank_account_id=bank_account_id))
