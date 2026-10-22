"""Temps de travaux des bénévoles : liste filtrée avec totaux, saisie, import CSV / XLSX."""
from datetime import date

from flask import current_app, jsonify, request

from app.extensions import db
from app.models import Entity, TaskType, WorkTime
from app.services.work_time_import import import_work_times
from app.utils.list_filters import (
    apply_date_sort, apply_month_filter, month_options_for_fy, parse_month, parse_sort,
)

from . import ApiError, bp, get_or_404, invalid, json_body, notice


def work_time_payload(wt: WorkTime) -> dict:
    return {"id": wt.id, "entity_id": wt.entity_id, "entity_name": wt.entity.name,
            "task_type_id": wt.task_type_id, "task_type": wt.task_type.name,
            "work_date": wt.work_date.isoformat(), "hours": float(wt.hours),
            "valuation_cents": wt.valuation_cents, "notes": wt.notes}


def _options():
    return {
        "benevoles": [{"value": str(e.id), "label": e.name}
                      for e in Entity.query.filter_by(is_benevole=True).order_by(Entity.name)],
        "task_types": [{"value": str(t.id), "label": t.name, "active": t.is_active}
                       for t in TaskType.query.order_by(TaskType.name)],
        "months": month_options_for_fy(),
    }


@bp.route("/work-times")
def work_times_list():
    query = WorkTime.query
    entity_id = request.args.get("entity_id", type=int)
    task_type_id = request.args.get("task_type_id", type=int)
    if entity_id:
        query = query.filter(WorkTime.entity_id == entity_id)
    if task_type_id:
        query = query.filter(WorkTime.task_type_id == task_type_id)
    query = apply_month_filter(query, WorkTime.work_date, parse_month(request.args.get("month")))
    rows = apply_date_sort(query, WorkTime.work_date, parse_sort(request.args.get("sort"))).all()
    return jsonify(items=[work_time_payload(wt) for wt in rows], meta={
        **_options(),
        "total_hours": sum(float(wt.hours) for wt in rows),
        "total_valuation_cents": sum(wt.valuation_cents for wt in rows),
    })


def _apply(wt: WorkTime, data: dict) -> None:
    errors = {}
    try:
        entity_id = int(data.get("entity_id"))
    except (TypeError, ValueError):
        entity_id = None
    if entity_id is None or db.session.get(Entity, entity_id) is None:
        errors["entity_id"] = "Bénévole obligatoire."
    try:
        task_type_id = int(data.get("task_type_id"))
    except (TypeError, ValueError):
        task_type_id = None
    if task_type_id is None or db.session.get(TaskType, task_type_id) is None:
        errors["task_type_id"] = "Type de tâche obligatoire."
    try:
        work_date = date.fromisoformat(str(data.get("work_date") or ""))
    except ValueError:
        work_date = None
        errors["work_date"] = "Date obligatoire."
    hours = data.get("hours")
    if not isinstance(hours, (int, float)) or isinstance(hours, bool) or hours <= 0 or hours > 24:
        errors["hours"] = "Le nombre d'heures doit être compris entre 0 et 24."
    if errors:
        raise ApiError("validation_error", "Le temps saisi contient des erreurs.", status=422,
                       fields=errors)
    wt.entity_id, wt.task_type_id, wt.work_date, wt.hours = entity_id, task_type_id, work_date, hours
    wt.notes = str(data.get("notes") or "").strip() or None


@bp.route("/work-times", methods=["POST"])
def work_times_create():
    wt = WorkTime()
    _apply(wt, json_body())
    db.session.add(wt)
    db.session.commit()
    return jsonify(item=work_time_payload(wt), notices=[notice("Temps de travaux enregistré.")]), 201


@bp.route("/work-times/<int:work_time_id>", methods=["PATCH"])
def work_times_update(work_time_id):
    wt = get_or_404(WorkTime, work_time_id, "Temps de travaux introuvable.")
    _apply(wt, json_body())
    db.session.commit()
    return jsonify(item=work_time_payload(wt), notices=[notice("Temps de travaux mis à jour.")])


@bp.route("/work-times/<int:work_time_id>", methods=["DELETE"])
def work_times_delete(work_time_id):
    wt = get_or_404(WorkTime, work_time_id, "Temps de travaux introuvable.")
    db.session.delete(wt)
    db.session.commit()
    return jsonify(notices=[notice("Temps de travaux supprimé.")])


@bp.route("/work-times/import", methods=["POST"])
def work_times_import():
    """Fichier CSV (séparateur ;) ou XLSX : une ligne par temps."""
    file = request.files.get("file")
    if not file or not file.filename:
        raise invalid("Choisissez un fichier CSV ou XLSX.", "file")
    try:
        result = import_work_times(file.stream, file.filename)
    except Exception as e:  # noqa: BLE001 — fichier illisible : message à l'écran
        current_app.logger.exception("Import temps de travaux échoué")
        raise invalid(f"Fichier illisible : {e}", "file") from None
    message = (f"{result['imported']} temps importé(s), {result['skipped']} ignoré(s), "
               f"{len(result['errors'])} erreur(s).")
    return jsonify(result=result, notices=[notice(message, "warning" if result["errors"] else "success")])
