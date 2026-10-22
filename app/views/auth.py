from flask import Blueprint, redirect, session, url_for
from flask_login import login_required, logout_user

from app.extensions import db, login_manager
from app.models import User

# Connexion et choix d'instance : pages de la SPA (app/spa_routes.json) et API
# app/api/session.py ; seuls restent le chargement de l'utilisateur et la
# déconnexion par lien (pages Jinja).
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


@bp.route("/logout")
@login_required
def logout():
    session.pop("instance_id", None)
    logout_user()
    return redirect(url_for("auth.login"))
