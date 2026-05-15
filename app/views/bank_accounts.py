from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app.extensions import db
from app.models import BankAccount, Account, BankTransaction
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
    sort = parse_sort(request.args.get("sort"))
    month_arg = request.args.get("month")
    month_tuple = parse_month(month_arg)

    query = ba.transactions
    if only_unreconciled:
        query = query.filter_by(reconciled=False)
    query = apply_month_filter(query, BankTransaction.transaction_date, month_tuple)
    query = apply_date_sort(query, BankTransaction.transaction_date, sort)
    txns = query.all()
    return render_template(
        "bank_accounts/transactions.html",
        ba=ba,
        txns=txns,
        only_unreconciled=only_unreconciled,
        **sort_and_filter_context(sort, month_arg),
    )
