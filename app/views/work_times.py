from datetime import datetime

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, current_app,
)
from flask_login import login_required

from app.extensions import db
from app.models import Entity, TaskType, WorkTime
from app.services.work_time_import import import_work_times
from app.utils.list_filters import (
    parse_sort, parse_month, apply_date_sort, apply_month_filter,
    sort_and_filter_context,
)

bp = Blueprint("work_times", __name__, url_prefix="/work-times")


# --- helpers --------------------------------------------------------------


def _parse_rate_to_cents(raw):
    """Convertit un taux saisi en euros (« 25 » ou « 25,50 ») en centimes."""
    value = (raw or "").strip().replace(",", ".")
    if not value:
        return 0
    return int(round(float(value) * 100))


def _parse_hours(raw):
    """Parse un nombre d'heures (« 2,5 » ou « 2.5 ») en float, ou None."""
    value = (raw or "").strip().replace(",", ".")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_date(raw):
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _benevoles():
    return (
        Entity.query.filter_by(is_benevole=True).order_by(Entity.name).all()
    )


def _active_task_types():
    return (
        TaskType.query.filter_by(is_active=True).order_by(TaskType.name).all()
    )


# --- consultation des temps ----------------------------------------------


@bp.route("/")
@login_required
def index():
    sort = parse_sort(request.args.get("sort"))
    month_arg = request.args.get("month")
    month_tuple = parse_month(month_arg)
    entity_id = request.args.get("entity_id", type=int)
    task_type_id = request.args.get("task_type_id", type=int)

    query = WorkTime.query
    if entity_id:
        query = query.filter(WorkTime.entity_id == entity_id)
    if task_type_id:
        query = query.filter(WorkTime.task_type_id == task_type_id)
    query = apply_month_filter(query, WorkTime.work_date, month_tuple)
    query = apply_date_sort(query, WorkTime.work_date, sort)
    work_times = query.all()

    total_hours = sum(float(wt.hours) for wt in work_times)
    total_valuation_cents = sum(wt.valuation_cents for wt in work_times)

    return render_template(
        "work_times/index.html",
        work_times=work_times,
        benevoles=_benevoles(),
        task_types=TaskType.query.order_by(TaskType.name).all(),
        selected_entity_id=entity_id,
        selected_task_type_id=task_type_id,
        total_hours=total_hours,
        total_valuation_cents=total_valuation_cents,
        **sort_and_filter_context(sort, month_arg),
    )


# --- saisie / édition / suppression d'un temps ----------------------------


def _save_work_time(work_time, is_new):
    """Lit le formulaire, valide, et persiste.

    Retourne un dict ``{champ: message}`` d'erreurs (vide si enregistré).
    """
    entity_id = request.form.get("entity_id", type=int)
    task_type_id = request.form.get("task_type_id", type=int)
    work_date = _parse_date(request.form.get("work_date"))
    hours = _parse_hours(request.form.get("hours"))
    notes = (request.form.get("notes") or "").strip() or None

    errors = {}
    if not entity_id or db.session.get(Entity, entity_id) is None:
        errors["entity_id"] = "Bénévole obligatoire."
    if not task_type_id or db.session.get(TaskType, task_type_id) is None:
        errors["task_type_id"] = "Type de tâche obligatoire."
    if work_date is None:
        errors["work_date"] = "Date obligatoire (format AAAA-MM-JJ)."
    if hours is None or hours <= 0:
        errors["hours"] = "Le nombre d'heures doit être supérieur à 0."
    if errors:
        return errors

    work_time.entity_id = entity_id
    work_time.task_type_id = task_type_id
    work_time.work_date = work_date
    work_time.hours = hours
    work_time.notes = notes
    if is_new:
        db.session.add(work_time)
    db.session.commit()
    return {}


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    if request.method == "POST":
        work_time = WorkTime()
        errors = _save_work_time(work_time, is_new=True)
        if not errors:
            flash("Temps de travaux enregistré.", "success")
            return redirect(url_for("work_times.index"))
        return render_template(
            "work_times/form.html", work_time=None, form=request.form, errors=errors,
            benevoles=_benevoles(), task_types=_active_task_types(),
        ), 422

    return render_template(
        "work_times/form.html", work_time=None, form={},
        benevoles=_benevoles(), task_types=_active_task_types(),
    )


@bp.route("/<int:work_time_id>/edit", methods=["GET", "POST"])
@login_required
def edit(work_time_id):
    work_time = WorkTime.query.get_or_404(work_time_id)
    if request.method == "POST":
        errors = _save_work_time(work_time, is_new=False)
        if not errors:
            flash("Temps de travaux mis à jour.", "success")
            return redirect(url_for("work_times.index"))
        return render_template(
            "work_times/form.html", work_time=work_time, form=request.form, errors=errors,
            benevoles=_benevoles(), task_types=_active_task_types(),
        ), 422

    return render_template(
        "work_times/form.html", work_time=work_time, form=None,
        benevoles=_benevoles(), task_types=_active_task_types(),
    )


@bp.route("/<int:work_time_id>/delete", methods=["POST"])
@login_required
def delete(work_time_id):
    work_time = WorkTime.query.get_or_404(work_time_id)
    db.session.delete(work_time)
    db.session.commit()
    flash("Temps de travaux supprimé.", "success")
    return redirect(url_for("work_times.index"))


# --- import en masse ------------------------------------------------------


@bp.route("/import", methods=["GET", "POST"])
@login_required
def import_view():
    result = None
    if request.method == "POST":
        file = request.files.get("file")
        if not file or not file.filename:
            flash("Veuillez choisir un fichier CSV ou XLSX.", "danger")
        else:
            try:
                result = import_work_times(file.stream, file.filename)
                msg = (
                    f"{result['imported']} temps importé(s), "
                    f"{result['skipped']} ignoré(s), "
                    f"{len(result['errors'])} erreur(s)."
                )
                flash(msg, "success" if not result["errors"] else "warning")
            except Exception as e:
                current_app.logger.exception("Import temps de travaux échoué")
                flash(f"Erreur lors de l'import : {e}", "danger")

    return render_template("work_times/import.html", result=result)


# --- paramétrage des types de tâches --------------------------------------


@bp.route("/task-types")
@login_required
def task_types():
    types = TaskType.query.order_by(TaskType.name).all()
    return render_template("work_times/task_types.html", types=types)


@bp.route("/task-types/new", methods=["GET", "POST"])
@login_required
def task_type_new():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        errors = {}
        if not name:
            errors["name"] = "Le nom est obligatoire."
        elif TaskType.query.filter(db.func.lower(TaskType.name) == name.lower()).first():
            errors["name"] = f"Un type nommé « {name} » existe déjà."
        else:
            tt = TaskType(
                name=name,
                hourly_rate_cents=_parse_rate_to_cents(request.form.get("hourly_rate")),
                is_active=bool(request.form.get("is_active")),
            )
            db.session.add(tt)
            db.session.commit()
            flash(f"Type de tâche « {name} » créé.", "success")
            return redirect(url_for("work_times.task_types"))
        return render_template(
            "work_times/task_type_form.html", task_type=None, form=request.form, errors=errors,
        ), 422

    return render_template(
        "work_times/task_type_form.html", task_type=None,
        form={"is_active": True},
    )


@bp.route("/task-types/<int:task_type_id>/edit", methods=["GET", "POST"])
@login_required
def task_type_edit(task_type_id):
    tt = TaskType.query.get_or_404(task_type_id)
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        existing = TaskType.query.filter(
            db.func.lower(TaskType.name) == name.lower(), TaskType.id != tt.id
        ).first()
        errors = {}
        if not name:
            errors["name"] = "Le nom est obligatoire."
        elif existing:
            errors["name"] = f"Un autre type nommé « {name} » existe déjà."
        else:
            tt.name = name
            tt.hourly_rate_cents = _parse_rate_to_cents(request.form.get("hourly_rate"))
            tt.is_active = bool(request.form.get("is_active"))
            db.session.commit()
            flash(f"Type de tâche « {name} » mis à jour.", "success")
            return redirect(url_for("work_times.task_types"))
        return render_template(
            "work_times/task_type_form.html", task_type=tt, form=request.form, errors=errors,
        ), 422

    return render_template(
        "work_times/task_type_form.html", task_type=tt, form=None,
    )


@bp.route("/task-types/<int:task_type_id>/delete", methods=["POST"])
@login_required
def task_type_delete(task_type_id):
    tt = TaskType.query.get_or_404(task_type_id)
    count = tt.work_times.count()
    if count > 0:
        flash(
            f"Impossible de supprimer « {tt.name} » : {count} temps de travaux "
            "y sont rattachés.",
            "danger",
        )
        return redirect(url_for("work_times.task_types"))
    db.session.delete(tt)
    db.session.commit()
    flash(f"Type de tâche « {tt.name} » supprimé.", "success")
    return redirect(url_for("work_times.task_types"))
