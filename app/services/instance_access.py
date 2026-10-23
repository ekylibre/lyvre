"""Accès aux instances : membres, rôles et comptes créés à cette occasion (méta-base).

Seul porteur des règles d'accès, appelé par la page Accès (instance courante), la fiche instance
de l'administrateur global, la création et l'import d'une instance
(claudedocs/design_acces_instances.md §3) :

- un administrateur global (`users.is_admin`) a accès à tout, sans ligne d'accès : il ne s'ajoute
  ni ne se modifie ici ;
- une instance garde au moins un administrateur (hors administrateurs globaux) ;
- un compte créé ici reçoit un mot de passe initial et doit le changer à la première connexion
  (`must_change_password`).

`parse_grants` valide une liste de lignes sans rien écrire, pour qu'une création d'instance soit
refusée en entier avant le provisioning de sa base.
"""
from dataclasses import dataclass

from sqlalchemy import func

from app.extensions import db
from app.models import InstanceMembership, User
from app.models.instance_membership import ROLE_ADMIN, ROLE_LABELS, ROLES

MIN_PASSWORD = 8


class AccessError(Exception):
    """Refus lisible ; `field` suit le chemin du formulaire (`members.1.password`)."""

    def __init__(self, message, field=None, status=422, code=None):
        super().__init__(message)
        self.message, self.field, self.status = message, field, status
        self.code = code or {404: "not_found", 409: "conflict"}.get(status, "validation_error")


@dataclass
class Grant:
    """Ligne validée : compte existant (`user`) ou nouveau compte (`email`, `password`)."""
    role: str
    user: User | None = None
    email: str | None = None
    full_name: str | None = None
    password: str | None = None


def role_options() -> list[dict]:
    return [{"value": r, "label": ROLE_LABELS[r]} for r in ROLES]


def _user_by_email(email: str) -> User | None:
    return db.session.query(User).filter(func.lower(User.email) == email).first()


def _role(value, field="role") -> str:
    if value not in ROLES:
        raise AccessError("Rôle inconnu.", field)
    return value


def _email(value, field="email") -> str:
    email = str(value or "").strip().lower()
    if "@" not in email or len(email) > 200:
        raise AccessError("Email invalide.", field)
    return email


def _password(value, field="password") -> str:
    password = str(value or "")
    if len(password) < MIN_PASSWORD:
        raise AccessError(f"{MIN_PASSWORD} caractères au moins.", field)
    return password


def _full_name(value) -> str | None:
    return str(value or "").strip()[:200] or None


def _existing_user(value, field="user_id") -> User:
    user = db.session.get(User, value) if isinstance(value, int) and not isinstance(value, bool) else None
    if user is None:
        raise AccessError("Utilisateur introuvable.", field)
    if user.is_admin:
        raise AccessError("Administrateur global : il a déjà accès à toutes les instances.", field)
    return user


# ------------------------------------------------------------------ lignes à la création


def parse_grants(items, *, field="members") -> list[Grant]:
    """Valide toute la liste sans écrire ; lève AccessError sur la première ligne fautive."""
    if items in (None, ""):
        return []
    if not isinstance(items, list):
        raise AccessError("Utilisateurs attendus sous forme de liste.", field)
    grants, seen_ids, seen_emails = [], set(), set()
    for i, item in enumerate(items):
        path = f"{field}.{i}"
        if not isinstance(item, dict):
            raise AccessError("Ligne invalide.", path)
        role = _role(item.get("role"), f"{path}.role")
        if item.get("user_id") not in (None, ""):
            user = _existing_user(item.get("user_id"), f"{path}.user_id")
            if user.id in seen_ids:
                raise AccessError("Utilisateur déjà dans la liste.", f"{path}.user_id")
            seen_ids.add(user.id)
            seen_emails.add(user.email.lower())
            grants.append(Grant(role=role, user=user))
            continue
        email = _email(item.get("email"), f"{path}.email")
        if email in seen_emails:
            raise AccessError("Email déjà dans la liste.", f"{path}.email")
        if _user_by_email(email) is not None:
            raise AccessError("Un compte existe avec cet email : choisissez-le dans la liste.", f"{path}.email")
        seen_emails.add(email)
        grants.append(Grant(role=role, email=email, full_name=_full_name(item.get("full_name")),
                            password=_password(item.get("password"), f"{path}.password")))
    return grants


def grants_warnings(grants: list[Grant]) -> list[str]:
    """Avertissements non bloquants : aucun administrateur parmi les lignes, comptes désactivés."""
    warnings = []
    if grants and not any(g.role == ROLE_ADMIN for g in grants):
        warnings.append("Aucun administrateur parmi les utilisateurs : seuls les administrateurs globaux "
                        "pourront gérer les accès de l'instance.")
    for g in grants:
        if g.user is not None and not g.user.is_active:
            warnings.append(f"Compte {g.user.email} désactivé : l'accès prendra effet à sa réactivation.")
    return warnings


def create_user(email: str, full_name: str | None, password: str) -> User:
    """Nouveau compte (non administrateur) avec mot de passe initial à changer."""
    user = User(email=email, full_name=full_name, is_active=True, must_change_password=True)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    return user


def apply_grants(instance, grants: list[Grant], by_user) -> dict:
    """Crée les comptes et les accès des lignes validées ; flush, sans commit."""
    created = 0
    for g in grants:
        user = g.user
        if user is None:
            user = create_user(g.email, g.full_name, g.password)
            created += 1
        db.session.add(InstanceMembership(user_id=user.id, instance_id=instance.id, role=g.role,
                                          created_by_user_id=by_user.id if by_user else None))
    db.session.flush()
    return {"created": created, "granted": len(grants)}


def grants_summary(counts: dict) -> str:
    """« 1 compte créé, 2 accès donnés » (vide sans ligne)."""
    if not counts["granted"]:
        return ""
    parts = []
    if counts["created"]:
        parts.append(f"{counts['created']} compte{'s' if counts['created'] > 1 else ''} créé{'s' if counts['created'] > 1 else ''}")
    parts.append(f"{counts['granted']} accès donné{'s' if counts['granted'] > 1 else ''}")
    return ", ".join(parts)


# ------------------------------------------------------------------ membres d'une instance


def _member(user: User, membership: InstanceMembership | None, me_id) -> dict:
    role = ROLE_ADMIN if user.is_admin else membership.role
    return {"user_id": user.id, "email": user.email, "full_name": user.full_name, "role": role,
            "role_label": ROLE_LABELS[role], "global_admin": user.is_admin, "is_active": user.is_active,
            "is_me": user.id == me_id}


def members(instance, me_id=None) -> list[dict]:
    """Membres de l'instance, administrateurs globaux compris (non modifiables), par email."""
    memberships = {m.user_id: m for m in db.session.query(InstanceMembership).filter_by(instance_id=instance.id)}
    users = db.session.query(User).filter(db.or_(User.is_admin.is_(True), User.id.in_(list(memberships) or [0])))
    return [_member(u, memberships.get(u.id), me_id) for u in users.order_by(User.email)]


def _membership(instance, user_id) -> InstanceMembership:
    membership = (db.session.query(InstanceMembership)
                  .filter_by(instance_id=instance.id, user_id=user_id).first())
    if membership is None:
        user = db.session.get(User, user_id)
        if user is not None and user.is_admin:
            raise AccessError("Administrateur global : accès à toutes les instances, non modifiable ici.", status=409)
        raise AccessError("Membre introuvable.", status=404)
    return membership


def _ensure_an_admin_remains(instance, excluded: InstanceMembership) -> None:
    """Refuse de retirer ou rétrograder le dernier administrateur (hors administrateurs globaux)."""
    others = (db.session.query(InstanceMembership)
              .filter(InstanceMembership.instance_id == instance.id, InstanceMembership.role == ROLE_ADMIN,
                      InstanceMembership.id != excluded.id).count())
    if excluded.role == ROLE_ADMIN and others == 0:
        raise AccessError("L'instance doit garder au moins un administrateur.", status=409)


def add_member(instance, data: dict, by_user) -> tuple[User, bool]:
    """`{user_id | email, role, full_name?, password?}` : compte existant, ou créé si `password` est
    fourni. Renvoie (utilisateur, créé ?) ; commit."""
    role = _role(data.get("role"))
    if data.get("user_id") not in (None, ""):
        user = _existing_user(data.get("user_id"))
    else:
        email = _email(data.get("email"))
        user = _user_by_email(email)
        if user is not None and user.is_admin:
            raise AccessError("Administrateur global : il a déjà accès à toutes les instances.", status=409)
    created = user is None
    if created:
        if len(str(data.get("password") or "")) < MIN_PASSWORD:
            raise AccessError("Aucun compte avec cet email : saisissez un mot de passe initial "
                              f"({MIN_PASSWORD} caractères au moins) pour le créer.", "password")
        user = create_user(email, _full_name(data.get("full_name")), str(data["password"]))
    elif db.session.query(InstanceMembership).filter_by(user_id=user.id, instance_id=instance.id).first():
        raise AccessError(f"{user.email} a déjà accès à cette instance.",
                          "user_id" if data.get("user_id") not in (None, "") else "email")
    db.session.add(InstanceMembership(user_id=user.id, instance_id=instance.id, role=role,
                                      created_by_user_id=by_user.id if by_user else None))
    db.session.commit()
    return user, created


def set_role(instance, user_id, role) -> InstanceMembership:
    membership = _membership(instance, user_id)
    role = _role(role)
    if role != ROLE_ADMIN:
        _ensure_an_admin_remains(instance, membership)
    membership.role = role
    db.session.commit()
    return membership


def remove_member(instance, user_id) -> str:
    """Retire l'accès ; renvoie l'email du membre retiré."""
    membership = _membership(instance, user_id)
    _ensure_an_admin_remains(instance, membership)
    email = membership.user.email
    db.session.delete(membership)
    db.session.commit()
    return email
