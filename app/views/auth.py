from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func

from app.extensions import db, login_manager
from app.models import Instance, User

bp = Blueprint("auth", __name__)


@login_manager.user_loader
def load_user(user_id):
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return None
    user = db.session.get(User, uid)
    if user is None or not user.is_active:
        return None
    return user


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("auth.select_instance"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        user = (
            db.session.query(User)
            .filter(func.lower(User.email) == email)
            .first()
        )
        if user is None or not user.check_password(password):
            flash("Email ou mot de passe incorrect.", "danger")
        elif not user.is_active:
            flash("Compte désactivé. Contactez un administrateur.", "danger")
        else:
            login_user(user)
            user.last_login_at = datetime.utcnow()
            db.session.commit()
            next_url = request.args.get("next")
            return redirect(next_url or url_for("auth.select_instance"))

    return render_template("auth/login.html")


@bp.route("/select-instance", methods=["GET", "POST"])
@login_required
def select_instance():
    instances = (
        db.session.query(Instance)
        .filter(Instance.is_active.is_(True))
        .order_by(Instance.label)
        .all()
    )

    if not instances:
        flash(
            "Aucune instance disponible. Contactez un administrateur pour en créer une.",
            "warning",
        )

    if request.method == "POST":
        try:
            instance_id = int(request.form.get("instance_id", ""))
        except ValueError:
            flash("Sélection invalide.", "danger")
            return render_template("auth/select_instance.html", instances=instances)

        match = next((i for i in instances if i.id == instance_id), None)
        if match is None:
            flash("Instance introuvable ou désactivée.", "danger")
            return render_template("auth/select_instance.html", instances=instances)

        session["instance_id"] = match.id
        next_url = request.args.get("next")
        return redirect(next_url or url_for("dashboard.index"))

    # Auto-select if a single instance is available and none chosen yet.
    if len(instances) == 1 and "instance_id" not in session:
        session["instance_id"] = instances[0].id
        next_url = request.args.get("next")
        return redirect(next_url or url_for("dashboard.index"))

    return render_template("auth/select_instance.html", instances=instances)


@bp.route("/logout")
@login_required
def logout():
    session.pop("instance_id", None)
    logout_user()
    return redirect(url_for("auth.login"))
