"""Accès aux instances et rôles (méta-base, `instance_memberships`).

- Administrateur global (`users.is_admin`) : rôle `admin` sur toutes les instances actives.
- Autres utilisateurs : seulement les instances où ils ont un rôle (`admin`, `treasurer`,
  `accountant`).
- `accountant` (expert-comptable) : lecture seule, contrôlée côté serveur pour toute l'API
  (`app/api/__init__.py`).

Le rôle de la requête courante est posé par le hook tenant dans `g.instance_role`.
"""
from functools import wraps

from flask import abort, g
from flask_login import current_user

from app.extensions import db
from app.models import Instance, InstanceMembership
from app.models.instance_membership import ROLE_ACCOUNTANT, ROLE_ADMIN


def role_for(user, instance) -> str | None:
    """Rôle de l'utilisateur sur l'instance, ou None s'il n'y a pas accès."""
    if user is None or instance is None or not instance.is_active:
        return None
    if user.is_admin:
        return ROLE_ADMIN
    membership = (db.session.query(InstanceMembership)
                  .filter_by(user_id=user.id, instance_id=instance.id).first())
    return membership.role if membership else None


def accessible_instances(user) -> list[Instance]:
    """Instances actives accessibles à l'utilisateur, par libellé."""
    query = db.session.query(Instance).filter(Instance.is_active.is_(True))
    if not user.is_admin:
        query = query.join(InstanceMembership, InstanceMembership.instance_id == Instance.id).filter(
            InstanceMembership.user_id == user.id)
    return query.order_by(Instance.label).all()


def current_role() -> str | None:
    return getattr(g, "instance_role", None)


def permissions(role: str | None) -> dict:
    """Droits affichés par la SPA (le serveur reste seul juge)."""
    return {"write": role is not None and role != ROLE_ACCOUNTANT, "instance_admin": role == ROLE_ADMIN}


def instance_admin_required(view):
    """Administration de l'instance courante (rôle `admin`, ou administrateur global)."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or current_role() != ROLE_ADMIN:
            abort(403)
        return view(*args, **kwargs)

    return wrapped
