from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app.extensions import login_manager
import os

bp = Blueprint("auth", __name__)


class _User(UserMixin):
    id = "1"
    username = "admin"

    def get_id(self):
        return self.id


_ADMIN = _User()
_PASSWORD_HASH = generate_password_hash(os.environ.get("ADMIN_PASSWORD", "admin"))


@login_manager.user_loader
def load_user(user_id):
    if user_id == "1":
        return _ADMIN
    return None


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if check_password_hash(_PASSWORD_HASH, password):
            login_user(_ADMIN)
            return redirect(request.args.get("next") or url_for("dashboard.index"))
        flash("Mot de passe incorrect.", "danger")
    return render_template("auth/login.html")


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
