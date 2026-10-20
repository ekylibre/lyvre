from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app.extensions import db
from app.models import Account

bp = Blueprint("accounts", __name__, url_prefix="/accounts")


@bp.route("/")
@login_required
def index():
    query = Account.query.order_by(Account.code)
    search = request.args.get("q", "").strip()
    if search:
        query = query.filter(
            db.or_(
                Account.code.ilike(f"%{search}%"),
                Account.label.ilike(f"%{search}%"),
            )
        )
    accounts = query.all()
    return render_template("accounts/index.html", accounts=accounts, search=search)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    if request.method == "POST":
        code = request.form["code"].strip()
        label = request.form["label"].strip()
        account_type = request.form["account_type"]
        parent_code = request.form.get("parent_code", "").strip()

        if Account.query.filter_by(code=code).first():
            flash(f"Le compte {code} existe déjà.", "danger")
            return redirect(url_for("accounts.new"))

        parent = Account.query.filter_by(code=parent_code).first() if parent_code else None
        account = Account(code=code, label=label, account_type=account_type, parent=parent)
        db.session.add(account)
        db.session.commit()
        flash(f"Compte {code} créé.", "success")
        return redirect(url_for("accounts.index"))

    from app.models.account import ACCOUNT_TYPES
    return render_template("accounts/form.html", account=None, account_types=ACCOUNT_TYPES)


@bp.route("/<int:account_id>/edit", methods=["GET", "POST"])
@login_required
def edit(account_id):
    account = Account.query.get_or_404(account_id)
    if request.method == "POST":
        account.label = request.form["label"].strip()
        account.account_type = request.form["account_type"]
        db.session.commit()
        flash("Compte mis à jour.", "success")
        return redirect(url_for("accounts.index"))

    from app.models.account import ACCOUNT_TYPES
    return render_template("accounts/form.html", account=account, account_types=ACCOUNT_TYPES)
