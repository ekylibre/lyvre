from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from app.decorators import admin_required
from app.extensions import db
from app.models import User

bp = Blueprint("users", __name__, url_prefix="/users")


@bp.route("/")
@login_required
@admin_required
def index():
    users = db.session.query(User).order_by(User.email).all()
    return render_template("users/index.html", users=users)


@bp.route("/new", methods=["GET", "POST"])
@login_required
@admin_required
def new():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        full_name = (request.form.get("full_name") or "").strip() or None
        is_admin = bool(request.form.get("is_admin"))
        is_active = bool(request.form.get("is_active"))

        if not email or not password:
            flash("Email et mot de passe sont obligatoires.", "danger")
            return render_template("users/form.html", user=None, form=request.form)

        if db.session.query(User).filter(func.lower(User.email) == email).first():
            flash(f"Un utilisateur avec l'email {email} existe déjà.", "danger")
            return render_template("users/form.html", user=None, form=request.form)

        user = User(
            email=email,
            full_name=full_name,
            is_admin=is_admin,
            is_active=is_active,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash(f"Utilisateur {email} créé.", "success")
        return redirect(url_for("users.index"))

    return render_template("users/form.html", user=None, form={})


@bp.route("/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        full_name = (request.form.get("full_name") or "").strip() or None
        is_admin = bool(request.form.get("is_admin"))
        is_active = bool(request.form.get("is_active"))

        if not email:
            flash("L'email est obligatoire.", "danger")
            return render_template("users/form.html", user=user, form=request.form)

        existing = (
            db.session.query(User)
            .filter(func.lower(User.email) == email, User.id != user.id)
            .first()
        )
        if existing is not None:
            flash(f"Un autre utilisateur utilise déjà l'email {email}.", "danger")
            return render_template("users/form.html", user=user, form=request.form)

        # An admin can't lock themselves out.
        if user.id == current_user.id and (not is_admin or not is_active):
            flash("Vous ne pouvez pas retirer votre propre statut admin ni vous désactiver.", "danger")
            return render_template("users/form.html", user=user, form=request.form)

        user.email = email
        user.full_name = full_name
        user.is_admin = is_admin
        user.is_active = is_active
        if password:
            user.set_password(password)
        db.session.commit()
        flash(f"Utilisateur {email} mis à jour.", "success")
        return redirect(url_for("users.index"))

    return render_template("users/form.html", user=user, form={})


@bp.route("/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    if user.id == current_user.id:
        flash("Vous ne pouvez pas supprimer votre propre compte.", "danger")
        return redirect(url_for("users.index"))
    db.session.delete(user)
    db.session.commit()
    flash(f"Utilisateur {user.email} supprimé.", "success")
    return redirect(url_for("users.index"))


@bp.route("/<int:user_id>/toggle-active", methods=["POST"])
@login_required
@admin_required
def toggle_active(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    if user.id == current_user.id:
        flash("Vous ne pouvez pas vous désactiver vous-même.", "danger")
        return redirect(url_for("users.index"))
    user.is_active = not user.is_active
    db.session.commit()
    state = "réactivé" if user.is_active else "désactivé"
    flash(f"Utilisateur {user.email} {state}.", "success")
    return redirect(url_for("users.index"))
