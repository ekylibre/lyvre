"""Types de tâches des temps de travaux (taux horaire en centimes)."""
from flask import jsonify

from app.extensions import db
from app.models import TaskType

from . import ApiError, bp, get_or_404, invalid, json_body, notice


def task_type_payload(tt: TaskType) -> dict:
    return {"id": tt.id, "name": tt.name, "hourly_rate_cents": tt.hourly_rate_cents,
            "is_active": tt.is_active, "work_times": tt.work_times.count()}


def _apply(tt: TaskType, data: dict) -> None:
    name = str(data.get("name") or "").strip()
    if not name:
        raise invalid("Le nom est obligatoire.", "name")
    duplicate = TaskType.query.filter(db.func.lower(TaskType.name) == name.lower())
    if tt.id is not None:
        duplicate = duplicate.filter(TaskType.id != tt.id)
    if duplicate.first():
        raise invalid(f"Un type nommé « {name} » existe déjà.", "name")
    rate = data.get("hourly_rate_cents") or 0
    if not isinstance(rate, int) or isinstance(rate, bool) or rate < 0:
        raise invalid("Taux horaire invalide.", "hourly_rate_cents")
    tt.name, tt.hourly_rate_cents = name[:150], rate
    tt.is_active = bool(data.get("is_active", True))


@bp.route("/task-types")
def task_types_list():
    types = TaskType.query.order_by(TaskType.name).all()
    return jsonify(items=[task_type_payload(tt) for tt in types])


@bp.route("/task-types", methods=["POST"])
def task_types_create():
    tt = TaskType()
    _apply(tt, json_body())
    db.session.add(tt)
    db.session.commit()
    return jsonify(item=task_type_payload(tt),
                   notices=[notice(f"Type de tâche « {tt.name} » créé.")]), 201


@bp.route("/task-types/<int:task_type_id>", methods=["PATCH"])
def task_types_update(task_type_id):
    tt = get_or_404(TaskType, task_type_id, "Type de tâche introuvable.")
    _apply(tt, json_body())
    db.session.commit()
    return jsonify(item=task_type_payload(tt),
                   notices=[notice(f"Type de tâche « {tt.name} » mis à jour.")])


@bp.route("/task-types/<int:task_type_id>", methods=["DELETE"])
def task_types_delete(task_type_id):
    tt = get_or_404(TaskType, task_type_id, "Type de tâche introuvable.")
    count = tt.work_times.count()
    if count:
        raise ApiError("conflict", f"Impossible de supprimer « {tt.name} » : {count} temps de "
                       "travaux y sont rattachés.", status=409)
    db.session.delete(tt)
    db.session.commit()
    return jsonify(notices=[notice(f"Type de tâche « {tt.name} » supprimé.")])
