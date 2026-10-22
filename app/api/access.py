"""Accès à l'instance courante (administrateur de l'instance) : membres et rôles.

Un administrateur global (`users.is_admin`) a toujours accès ; il apparaît dans la liste sans
pouvoir y être modifié. Ajouter un membre : compte existant (par email) ou nouveau compte
(mot de passe initial transmis par l'administrateur, hors application).
"""
from flask import g, jsonify
from flask_login import current_user
from sqlalchemy import func

from app.access import instance_admin_required
from app.extensions import db
from app.models import InstanceMembership, User
from app.models.instance_membership import ROLE_ADMIN, ROLE_LABELS, ROLES

from . import ApiError, bp, invalid, json_body, notice


def _member(user: User, membership: InstanceMembership | None) -> dict:
    role = ROLE_ADMIN if user.is_admin else membership.role
    return {"user_id": user.id, "email": user.email, "full_name": user.full_name, "role": role,
            "role_label": ROLE_LABELS[role], "global_admin": user.is_admin, "is_active": user.is_active,
            "is_me": user.id == current_user.id}


def _members():
    instance = g.current_instance
    memberships = {m.user_id: m for m in db.session.query(InstanceMembership).filter_by(instance_id=instance.id)}
    users = db.session.query(User).filter(db.or_(User.is_admin.is_(True), User.id.in_(list(memberships) or [0])))
    return [_member(u, memberships.get(u.id)) for u in users.order_by(User.email)]


def _role(data):
    role = data.get("role")
    if role not in ROLES:
        raise invalid("Rôle inconnu.", "role")
    return role


def _membership(user_id) -> InstanceMembership:
    membership = (db.session.query(InstanceMembership)
                  .filter_by(instance_id=g.current_instance.id, user_id=user_id).first())
    if membership is None:
        user = db.session.get(User, user_id)
        if user is not None and user.is_admin:
            raise ApiError("conflict", "Administrateur global : accès à toutes les instances, non modifiable ici.",
                           status=409)
        raise ApiError("not_found", "Membre introuvable.", status=404)
    return membership


def _ensure_an_admin_remains(excluded: InstanceMembership):
    """Refuse de retirer ou rétrograder le dernier administrateur (hors administrateurs globaux)."""
    others = (db.session.query(InstanceMembership)
              .filter(InstanceMembership.instance_id == g.current_instance.id,
                      InstanceMembership.role == ROLE_ADMIN, InstanceMembership.id != excluded.id).count())
    if excluded.role == ROLE_ADMIN and others == 0:
        raise ApiError("conflict", "L'instance doit garder au moins un administrateur.", status=409)


@bp.route("/access/members")
@instance_admin_required
def access_members():
    return jsonify(items=_members(), meta={"roles": [{"value": r, "label": ROLE_LABELS[r]} for r in ROLES]})


@bp.route("/access/members", methods=["POST"])
@instance_admin_required
def access_add_member():
    """`{email, role, full_name?, password?}` : compte existant, ou créé si `password` est fourni."""
    data = json_body()
    role = _role(data)
    email = str(data.get("email") or "").strip().lower()
    if "@" not in email:
        raise invalid("Email invalide.", "email")
    user = db.session.query(User).filter(func.lower(User.email) == email).first()
    if user is None:
        password = str(data.get("password") or "")
        if len(password) < 8:
            raise ApiError("validation_error", "Aucun compte avec cet email : saisissez un mot de passe initial "
                           "(8 caractères au moins) pour le créer.", status=422,
                           fields={"password": "8 caractères au moins pour créer le compte."})
        user = User(email=email, full_name=str(data.get("full_name") or "").strip()[:200] or None, is_active=True)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        created = True
    else:
        created = False
        if user.is_admin:
            raise ApiError("conflict", "Administrateur global : il a déjà accès à toutes les instances.", status=409)
        if db.session.query(InstanceMembership).filter_by(user_id=user.id, instance_id=g.current_instance.id).first():
            raise invalid(f"{email} a déjà accès à cette instance.", "email")
    db.session.add(InstanceMembership(user_id=user.id, instance_id=g.current_instance.id, role=role,
                                      created_by_user_id=current_user.id))
    db.session.commit()
    what = "Compte créé et accès donné" if created else "Accès donné"
    return jsonify(items=_members(), notices=[notice(f"{what} à {email} ({ROLE_LABELS[role]}).")]), 201


@bp.route("/access/members/<int:user_id>", methods=["PATCH"])
@instance_admin_required
def access_update_member(user_id):
    membership = _membership(user_id)
    role = _role(json_body())
    if role != ROLE_ADMIN:
        _ensure_an_admin_remains(membership)
    membership.role = role
    db.session.commit()
    return jsonify(items=_members(), notices=[notice(f"Rôle de {membership.user.email} : {ROLE_LABELS[role]}.")])


@bp.route("/access/members/<int:user_id>", methods=["DELETE"])
@instance_admin_required
def access_remove_member(user_id):
    membership = _membership(user_id)
    _ensure_an_admin_remains(membership)
    email = membership.user.email
    db.session.delete(membership)
    db.session.commit()
    return jsonify(items=_members(), notices=[notice(f"Accès de {email} retiré.")])
