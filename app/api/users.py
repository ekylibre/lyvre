"""Utilisateurs (méta-base, administrateurs seulement)."""
from flask import jsonify
from flask_login import current_user
from sqlalchemy import func

from app.decorators import admin_required
from app.extensions import db
from app.models import User

from . import ApiError, bp, get_or_404, invalid, json_body, notice


def user_payload(u: User) -> dict:
    return {"id": u.id, "email": u.email, "full_name": u.full_name, "is_admin": u.is_admin,
            "is_active": u.is_active,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "is_me": u.id == current_user.id}


def _apply(user: User, data: dict, creating: bool) -> None:
    email = str(data.get("email") or "").strip().lower()
    password = str(data.get("password") or "")
    if not email:
        raise invalid("L'email est obligatoire.", "email")
    if creating and not password:
        raise invalid("Le mot de passe est obligatoire.", "password")
    duplicate = db.session.query(User).filter(func.lower(User.email) == email)
    if user.id is not None:
        duplicate = duplicate.filter(User.id != user.id)
    if duplicate.first():
        raise invalid(f"Un autre utilisateur utilise déjà l'email {email}.", "email")
    is_admin, is_active = bool(data.get("is_admin")), bool(data.get("is_active", True))
    # Un administrateur ne peut pas se retirer ses droits ni se désactiver.
    if user.id == current_user.id and (not is_admin or not is_active):
        raise invalid("Vous ne pouvez pas retirer votre propre statut admin ni vous désactiver.")
    user.email, user.is_admin, user.is_active = email, is_admin, is_active
    user.full_name = str(data.get("full_name") or "").strip()[:200] or None
    if password:
        user.set_password(password)


@bp.route("/users")
@admin_required
def users_list():
    users = db.session.query(User).order_by(User.email).all()
    return jsonify(items=[user_payload(u) for u in users])


@bp.route("/users", methods=["POST"])
@admin_required
def users_create():
    user = User()
    _apply(user, json_body(), creating=True)
    db.session.add(user)
    db.session.commit()
    return jsonify(item=user_payload(user), notices=[notice(f"Utilisateur {user.email} créé.")]), 201


@bp.route("/users/<int:user_id>", methods=["PATCH"])
@admin_required
def users_update(user_id):
    user = get_or_404(User, user_id, "Utilisateur introuvable.")
    data = json_body()
    if set(data) == {"is_active"}:
        if user.id == current_user.id:
            raise ApiError("conflict", "Vous ne pouvez pas vous désactiver vous-même.", status=409)
        user.is_active = bool(data["is_active"])
        db.session.commit()
        state = "réactivé" if user.is_active else "désactivé"
        return jsonify(item=user_payload(user), notices=[notice(f"Utilisateur {user.email} {state}.")])
    _apply(user, data, creating=False)
    db.session.commit()
    return jsonify(item=user_payload(user), notices=[notice(f"Utilisateur {user.email} mis à jour.")])


@bp.route("/users/<int:user_id>", methods=["DELETE"])
@admin_required
def users_delete(user_id):
    user = get_or_404(User, user_id, "Utilisateur introuvable.")
    if user.id == current_user.id:
        raise ApiError("conflict", "Vous ne pouvez pas supprimer votre propre compte.", status=409)
    db.session.delete(user)
    db.session.commit()
    return jsonify(notices=[notice(f"Utilisateur {user.email} supprimé.")])
