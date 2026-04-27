from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app.extensions import db
from app.models import Journal

bp = Blueprint("journals", __name__, url_prefix="/journals")


@bp.route("/")
@login_required
def index():
    journals = Journal.query.order_by(Journal.code).all()
    return render_template("journals/index.html", journals=journals)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    if request.method == "POST":
        code = request.form["code"].strip().upper()
        label = request.form["label"].strip()
        if Journal.query.filter_by(code=code).first():
            flash(f"Le journal {code} existe déjà.", "danger")
            return redirect(url_for("journals.new"))
        db.session.add(Journal(code=code, label=label))
        db.session.commit()
        flash(f"Journal {code} créé.", "success")
        return redirect(url_for("journals.index"))
    return render_template("journals/form.html", journal=None)
