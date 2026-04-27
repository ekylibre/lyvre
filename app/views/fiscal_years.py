from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from datetime import date
from app.extensions import db
from app.models import FiscalYear

bp = Blueprint("fiscal_years", __name__, url_prefix="/fiscal-years")


@bp.route("/")
@login_required
def index():
    fiscal_years = FiscalYear.query.order_by(FiscalYear.start_date.desc()).all()
    return render_template("fiscal_years/index.html", fiscal_years=fiscal_years)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    if request.method == "POST":
        fy = FiscalYear(
            label=request.form["label"].strip(),
            start_date=date.fromisoformat(request.form["start_date"]),
            end_date=date.fromisoformat(request.form["end_date"]),
        )
        db.session.add(fy)
        db.session.commit()
        flash(f"Exercice « {fy.label} » créé.", "success")
        return redirect(url_for("fiscal_years.index"))
    return render_template("fiscal_years/form.html", fy=None)


@bp.route("/<int:fy_id>/close", methods=["POST"])
@login_required
def close(fy_id):
    fy = FiscalYear.query.get_or_404(fy_id)
    if fy.closed:
        flash("Cet exercice est déjà clôturé.", "warning")
    else:
        fy.closed = True
        db.session.commit()
        flash(f"Exercice « {fy.label} » clôturé.", "success")
    return redirect(url_for("fiscal_years.index"))
