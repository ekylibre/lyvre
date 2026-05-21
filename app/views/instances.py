from flask import (
    Blueprint, abort, current_app, flash, redirect, render_template,
    request, send_file, url_for,
)
from flask_login import login_required

from app.decorators import admin_required
from app.extensions import db
from app.models import Instance
from app.services import instance_backup
from app.services.instance_backup import BackupError
from app.services.instance_provisioning import (
    ProvisioningError,
    build_sqlite_url,
    provision_sqlite_database,
    validate_slug,
)
from app.tenant import clear_engine_cache

bp = Blueprint("instances", __name__, url_prefix="/instances")


@bp.route("/")
@login_required
@admin_required
def index():
    instances = db.session.query(Instance).order_by(Instance.label).all()
    return render_template("instances/index.html", instances=instances)


@bp.route("/new", methods=["GET", "POST"])
@login_required
@admin_required
def new():
    if request.method == "POST":
        raw_slug = request.form.get("slug") or ""
        label = (request.form.get("label") or "").strip()
        provisioning_mode = request.form.get("provisioning_mode") or "auto"
        custom_url = (request.form.get("database_url") or "").strip()

        try:
            slug = validate_slug(raw_slug)
        except ProvisioningError as e:
            flash(str(e), "danger")
            return render_template("instances/form.html", form=request.form)

        if not label:
            flash("Le libellé est obligatoire.", "danger")
            return render_template("instances/form.html", form=request.form)

        if db.session.query(Instance).filter(Instance.slug == slug).first():
            flash(f"L'instance « {slug} » existe déjà.", "danger")
            return render_template("instances/form.html", form=request.form)

        if provisioning_mode == "auto":
            database_url = build_sqlite_url(slug)
            try:
                provision_sqlite_database(database_url)
            except ProvisioningError as e:
                flash(f"Échec du provisioning : {e}", "danger")
                return render_template("instances/form.html", form=request.form)
        else:
            if not custom_url:
                flash("URL de base de données obligatoire en mode manuel.", "danger")
                return render_template("instances/form.html", form=request.form)
            database_url = custom_url

        inst = Instance(
            slug=slug,
            label=label,
            database_url=database_url,
            is_active=True,
        )
        db.session.add(inst)
        db.session.commit()
        flash(f"Instance « {label} » créée.", "success")
        return redirect(url_for("instances.index"))

    return render_template("instances/form.html", form={})


@bp.route("/<int:instance_id>")
@login_required
@admin_required
def detail(instance_id):
    inst = db.session.get(Instance, instance_id)
    if inst is None:
        abort(404)
    sqlite_instance = instance_backup.is_sqlite_instance(inst)
    backups = instance_backup.list_backups(inst) if sqlite_instance else []
    return render_template(
        "instances/detail.html",
        instance=inst,
        backups=backups,
        sqlite_instance=sqlite_instance,
    )


@bp.route("/<int:instance_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit(instance_id):
    inst = db.session.get(Instance, instance_id)
    if inst is None:
        abort(404)

    if request.method == "POST":
        label = (request.form.get("label") or "").strip()
        is_active = bool(request.form.get("is_active"))
        if not label:
            flash("Le libellé est obligatoire.", "danger")
            return render_template("instances/form.html", instance=inst, form=request.form)

        inst.label = label
        inst.is_active = is_active
        db.session.commit()
        clear_engine_cache(inst.id)
        flash(f"Instance « {label} » mise à jour.", "success")
        return redirect(url_for("instances.index"))

    return render_template("instances/form.html", instance=inst, form={})


@bp.route("/<int:instance_id>/backup", methods=["POST"])
@login_required
@admin_required
def create_backup(instance_id):
    inst = db.session.get(Instance, instance_id)
    if inst is None:
        abort(404)
    try:
        path = instance_backup.create_backup(inst)
    except BackupError as e:
        flash(str(e), "danger")
        return redirect(url_for("instances.detail", instance_id=inst.id))
    flash(f"Sauvegarde créée : {path.name}", "success")
    return redirect(url_for("instances.detail", instance_id=inst.id))


@bp.route("/<int:instance_id>/backups/<filename>/download")
@login_required
@admin_required
def download_backup(instance_id, filename):
    inst = db.session.get(Instance, instance_id)
    if inst is None:
        abort(404)
    try:
        path = instance_backup.backup_path(inst, filename)
    except BackupError as e:
        flash(str(e), "danger")
        return redirect(url_for("instances.detail", instance_id=inst.id))
    return send_file(
        path,
        as_attachment=True,
        download_name=filename,
        mimetype="application/octet-stream",
    )


@bp.route("/<int:instance_id>/backups/<filename>/delete", methods=["POST"])
@login_required
@admin_required
def delete_backup(instance_id, filename):
    inst = db.session.get(Instance, instance_id)
    if inst is None:
        abort(404)
    try:
        instance_backup.delete_backup(inst, filename)
    except BackupError as e:
        flash(str(e), "danger")
        return redirect(url_for("instances.detail", instance_id=inst.id))
    flash(f"Sauvegarde supprimée : {filename}", "success")
    return redirect(url_for("instances.detail", instance_id=inst.id))


@bp.route("/<int:instance_id>/restore", methods=["GET", "POST"])
@login_required
@admin_required
def restore(instance_id):
    inst = db.session.get(Instance, instance_id)
    if inst is None:
        abort(404)
    if not instance_backup.is_sqlite_instance(inst):
        flash("Restauration disponible uniquement pour les instances SQLite.", "danger")
        return redirect(url_for("instances.detail", instance_id=inst.id))

    if request.method == "POST":
        uploaded = request.files.get("backup_file")
        if uploaded is None or not uploaded.filename:
            flash("Sélectionnez un fichier à restaurer.", "danger")
            return render_template("instances/restore.html", instance=inst)
        try:
            pre_backup, _ = instance_backup.restore_from_upload(inst, uploaded)
        except BackupError as e:
            flash(str(e), "danger")
            return render_template("instances/restore.html", instance=inst)
        flash(
            f"Restauration appliquée. Sauvegarde de sécurité créée : {pre_backup.name}",
            "success",
        )
        return redirect(url_for("instances.detail", instance_id=inst.id))

    return render_template("instances/restore.html", instance=inst)
