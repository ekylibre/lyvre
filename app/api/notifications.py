"""Notifications de l'utilisateur connecté dans l'instance courante (fin des tâches en
arrière-plan) : liste avec le nombre de non lues, marquage comme lu."""
from flask import jsonify, request
from flask_login import current_user

from app.models import Notification
from app.services import notifications

from . import bp, invalid, json_body

MAX_LIMIT = 100


def _iso(value):
    return value.isoformat() if value else None


def notification_payload(n: Notification) -> dict:
    return {"id": n.id, "kind": n.kind, "level": n.level, "title": n.title, "message": n.message, "url": n.url,
            "job_id": n.job_id, "created_at": _iso(n.created_at), "read": n.is_read}


@bp.route("/notifications")
def notifications_list():
    """`?unread=1` : non lues seulement ; `?limit=` (20 par défaut, 100 au plus)."""
    limit = min(max(request.args.get("limit", 20, type=int), 1), MAX_LIMIT)
    query = notifications.visible_to(current_user.id)
    if request.args.get("unread") == "1":
        query = query.filter(Notification.read_at.is_(None))
    items = query.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit).all()
    return jsonify(items=[notification_payload(n) for n in items],
                   meta={"unread": notifications.unread_count(current_user.id)})


@bp.route("/notifications/read", methods=["POST"])
def notifications_mark_read():
    """`{ids: [..]}` marque ces notifications comme lues ; sans `ids`, toutes."""
    ids = json_body().get("ids")
    if ids is not None and (not isinstance(ids, list) or not all(isinstance(i, int) for i in ids)):
        raise invalid("Liste d'identifiants attendue.", "ids")
    marked = notifications.mark_read(current_user.id, ids)
    return jsonify(marked=marked, meta={"unread": notifications.unread_count(current_user.id)})
