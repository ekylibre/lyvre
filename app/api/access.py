"""Accès à l'instance courante (administrateur de l'instance) : membres et rôles.

Un administrateur global (`users.is_admin`) a toujours accès ; il apparaît dans la liste sans
pouvoir y être modifié. Ajouter un membre : compte existant (`user_id` ou email) ou nouveau compte
(mot de passe initial transmis par l'administrateur, hors application, à changer à la première
connexion). Les règles sont dans `app/services/instance_access.py` ; les fonctions `add_member`,
`update_member` et `remove_member` servent aussi à la fiche instance (E2).
"""
from flask import g, jsonify
from flask_login import current_user

from app.access import instance_admin_required
from app.models.instance_membership import ROLE_LABELS
from app.services import instance_access
from app.services.instance_access import AccessError

from . import ApiError, bp, json_body, notice


def access_error(exc: AccessError) -> ApiError:
    """Refus du service → erreur JSON de l'API (champ rattaché s'il y en a un)."""
    return ApiError(exc.code, exc.message, status=exc.status, fields={exc.field: exc.message} if exc.field else None)


def members_response(instance, **extra):
    return jsonify(items=instance_access.members(instance, current_user.id), **extra)


def add_member(instance):
    try:
        user, created = instance_access.add_member(instance, json_body(), current_user)
    except AccessError as exc:
        raise access_error(exc) from None
    role = ROLE_LABELS[next(m.role for m in user.memberships if m.instance_id == instance.id)]
    what = "Compte créé et accès donné" if created else "Accès donné"
    return members_response(instance, notices=[notice(f"{what} à {user.email} ({role}).")]), 201


def update_member(instance, user_id):
    try:
        membership = instance_access.set_role(instance, user_id, json_body().get("role"))
    except AccessError as exc:
        raise access_error(exc) from None
    return members_response(instance, notices=[notice(
        f"Rôle de {membership.user.email} : {ROLE_LABELS[membership.role]}.")])


def remove_member(instance, user_id):
    try:
        email = instance_access.remove_member(instance, user_id)
    except AccessError as exc:
        raise access_error(exc) from None
    return members_response(instance, notices=[notice(f"Accès de {email} retiré.")])


@bp.route("/access/members")
@instance_admin_required
def access_members():
    return members_response(g.current_instance, meta={"roles": instance_access.role_options()})


@bp.route("/access/members", methods=["POST"])
@instance_admin_required
def access_add_member():
    """`{user_id | email, role, full_name?, password?}` : compte existant, ou créé si `password` est fourni."""
    return add_member(g.current_instance)


@bp.route("/access/members/<int:user_id>", methods=["PATCH"])
@instance_admin_required
def access_update_member(user_id):
    return update_member(g.current_instance, user_id)


@bp.route("/access/members/<int:user_id>", methods=["DELETE"])
@instance_admin_required
def access_remove_member(user_id):
    return remove_member(g.current_instance, user_id)
