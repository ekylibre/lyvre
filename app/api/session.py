"""Session de la SPA : connexion, instance courante, menus, préférences, tâches longues.

Voir claudedocs/design_front_mantine.md §4. Ces routes (sauf ``jobs``) se passent
de la base de l'instance : elles sont déclarées « sans instance » dans app.tenant
(_TENANT_FREE_ENDPOINTS).
"""
import json
from datetime import datetime

from flask import g, jsonify, session as flask_session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from flask_wtf.csrf import generate_csrf
from sqlalchemy import func

from app.access import accessible_instances, permissions, role_for
from app.extensions import db
from app.menu_config import build_nav
from app.models import Instance, SyncJob, User

from . import ApiError, bp, json_body

PREFERENCES_MAX_BYTES = 16 * 1024
COLOR_SCHEMES = ("light", "dark", "auto")

def _current_instance():
    """Instance de la session, si l'utilisateur y a (encore) accès."""
    instance_id = flask_session.get("instance_id")
    inst = db.session.get(Instance, instance_id) if instance_id is not None else None
    return inst if role_for(current_user, inst) is not None else None


def _resolve_nav(menus):
    """Menus de menu_config avec les URL résolues (url_for) pour la SPA."""
    resolved = []
    for menu in menus:
        entry = {"key": menu["key"], "label": menu["label"]}
        if "items" in menu:
            entry["items"] = [
                {"divider": True} if item.get("divider")
                else {"key": item["key"], "label": item["label"], "url": url_for(item["endpoint"])}
                for item in menu["items"]
            ]
        else:
            entry["url"] = url_for(menu["endpoint"])
        resolved.append(entry)
    return resolved


def preferences_of(user) -> dict:
    try:
        value = json.loads(user.preferences or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def session_payload() -> dict:
    """Utilisateur, instance, menus, préférences et jeton CSRF (vide si non connecté)."""
    if not current_user.is_authenticated:
        return {"user": None, "instance": None, "instances": [], "nav": [], "admin_links": [],
                "role": None, "permissions": permissions(None), "preferences": {},
                "csrf_token": generate_csrf()}
    inst = getattr(g, "current_instance", None) or _current_instance()
    is_admin = bool(current_user.is_admin)
    role = role_for(current_user, inst) if inst else None
    return {
        "user": {"id": current_user.id, "email": current_user.email,
                 "full_name": current_user.full_name, "is_admin": is_admin},
        "instance": ({"id": inst.id, "slug": inst.slug, "label": inst.label, "chart": inst.chart,
                      "bookkeeping": inst.bookkeeping} if inst else None),
        "instances": [{"id": i.id, "label": i.label} for i in accessible_instances(current_user)],
        "role": role, "permissions": permissions(role),
        "nav": _resolve_nav(build_nav(chart=inst.chart, is_admin=role == "admin", bookkeeping=inst.bookkeeping))
        if inst else [],
        # Menu de l'utilisateur (en-tête) : administration réservée aux admins.
        "admin_links": ([{"label": "Utilisateurs", "url": url_for("users.index")},
                         {"label": "Instances", "url": url_for("instances.index")}] if is_admin else []),
        "preferences": preferences_of(current_user),
        "csrf_token": generate_csrf(),
    }


@bp.route("/session")
@login_required
def session_info():
    return jsonify(session_payload())


@bp.route("/session/login", methods=["POST"])
def login():
    data = json_body()
    email = str(data.get("email") or "").strip().lower()
    password = str(data.get("password") or "")
    user = db.session.query(User).filter(func.lower(User.email) == email).first()
    if user is None or not user.check_password(password):
        raise ApiError("validation_error", "Email ou mot de passe incorrect.", status=422)
    if not user.is_active:
        raise ApiError("validation_error", "Compte désactivé. Contactez un administrateur.", status=422)
    login_user(user)
    user.last_login_at = datetime.utcnow()
    db.session.commit()
    instances = accessible_instances(user)
    if len(instances) == 1 and _current_instance() is None:
        flask_session["instance_id"] = instances[0].id
    return jsonify(session_payload())


@bp.route("/session/logout", methods=["POST"])
def logout():
    flask_session.pop("instance_id", None)
    logout_user()
    return jsonify(session_payload())


@bp.route("/session/instance", methods=["POST"])
@login_required
def select_instance():
    try:
        instance_id = int(json_body().get("instance_id"))
    except (TypeError, ValueError):
        raise ApiError("validation_error", "Sélection invalide.", status=422,
                       fields={"instance_id": "Choisissez une instance."}) from None
    inst = db.session.get(Instance, instance_id)
    if role_for(current_user, inst) is None:
        raise ApiError("validation_error", "Instance introuvable, désactivée ou non autorisée.", status=422,
                       fields={"instance_id": "Instance introuvable, désactivée ou non autorisée."})
    flask_session["instance_id"] = inst.id
    g.current_instance = inst
    return jsonify(session_payload())


def _merge(base: dict, patch: dict) -> dict:
    """Fusion profonde ; une valeur ``None`` supprime la clé."""
    merged = dict(base)
    for key, value in patch.items():
        if value is None:
            merged.pop(key, None)
        elif isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


@bp.route("/me/preferences", methods=["PATCH"])
@login_required
def update_preferences():
    patch = json_body()
    scheme = patch.get("color_scheme")
    if scheme is not None and scheme not in COLOR_SCHEMES:
        raise ApiError("validation_error", "Thème inconnu.", status=422,
                       fields={"color_scheme": "Valeurs possibles : light, dark, auto."})
    merged = _merge(preferences_of(current_user), patch)
    encoded = json.dumps(merged, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode()) > PREFERENCES_MAX_BYTES:
        raise ApiError("payload_too_large", "Préférences trop volumineuses.", status=413)
    current_user.preferences = encoded
    db.session.commit()
    return jsonify(preferences=merged)


def job_payload(job: SyncJob) -> dict:
    try:
        result = json.loads(job.result_json) if job.result_json else None
    except ValueError:
        result = None
    return {"id": job.id, "kind": job.kind, "status": job.status, "message": job.message,
            "progress_done": job.progress_done, "progress_total": job.progress_total,
            "result": result,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None}


@bp.route("/jobs/<int:job_id>")
@login_required
def job_status(job_id):
    job = db.session.get(SyncJob, job_id)
    if job is None:
        raise ApiError("not_found", "Tâche introuvable.", status=404)
    return jsonify(job=job_payload(job))
