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
    CHARTS,
    DEFAULT_CHART,
    ProvisioningError,
    build_sqlite_url,
    database_file_for_url,
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
        chart = request.form.get("chart") or DEFAULT_CHART

        try:
            slug = validate_slug(raw_slug)
        except ProvisioningError as e:
            flash(str(e), "danger")
            return render_template("instances/form.html", form=request.form, charts=CHARTS)

        if not label:
            flash("Le libellé est obligatoire.", "danger")
            return render_template("instances/form.html", form=request.form, charts=CHARTS)

        if db.session.query(Instance).filter(Instance.slug == slug).first():
            flash(f"L'instance « {slug} » existe déjà.", "danger")
            return render_template("instances/form.html", form=request.form, charts=CHARTS)

        if provisioning_mode == "auto":
            database_url = build_sqlite_url(slug)
            try:
                provision_sqlite_database(database_url, chart=chart)
            except ProvisioningError as e:
                flash(f"Échec du provisioning : {e}", "danger")
                return render_template("instances/form.html", form=request.form, charts=CHARTS)
        else:
            if not custom_url:
                flash("URL de base de données obligatoire en mode manuel.", "danger")
                return render_template("instances/form.html", form=request.form, charts=CHARTS)
            database_url = custom_url

        inst = Instance(
            slug=slug,
            label=label,
            database_url=database_url,
            chart=chart if chart in CHARTS else DEFAULT_CHART,
            is_active=True,
        )
        db.session.add(inst)
        db.session.commit()
        flash(f"Instance « {label} » créée.", "success")
        return redirect(url_for("instances.index"))

    return render_template("instances/form.html", form={}, charts=CHARTS)


@bp.route("/import", methods=["GET", "POST"])
@login_required
@admin_required
def import_upload():
    """Upload a .zip archive or .db / .backup file: restore the matching instance, or create a new one."""
    if request.method == "POST":
        uploaded = request.files.get("backup_file")
        if uploaded is None or not uploaded.filename:
            flash("Sélectionnez un fichier à importer.", "danger")
            return render_template("instances/import.html", form=request.form)

        provided_slug = (request.form.get("slug") or "").strip().lower()
        slug = provided_slug or (instance_backup.extract_slug_from_filename(uploaded.filename) or "")
        label = (request.form.get("label") or "").strip()

        if not slug:
            flash(
                "Impossible de déduire le slug depuis le nom du fichier — saisissez-en un.",
                "danger",
            )
            return render_template("instances/import.html", form=request.form)

        existing = db.session.query(Instance).filter(Instance.slug == slug).first()

        if existing is not None:
            # Slug already known → treat upload as a restoration of that instance.
            if not instance_backup.is_sqlite_instance(existing):
                flash(
                    "L'instance existante n'est pas SQLite — restauration impossible.",
                    "danger",
                )
                return render_template("instances/import.html", form=request.form)
            try:
                pre_backup, _ = instance_backup.restore_from_upload(existing, uploaded)
            except instance_backup.BackupError as e:
                flash(str(e), "danger")
                return render_template("instances/import.html", form=request.form)
            flash(
                f"Instance « {existing.label} » restaurée depuis l'upload. "
                f"Sauvegarde de sécurité : {pre_backup.name}",
                "success",
            )
            return redirect(url_for("instances.detail", instance_id=existing.id))

        # Brand-new instance — validate slug, choose URL, create row.
        try:
            slug = validate_slug(slug)
        except ProvisioningError as e:
            flash(str(e), "danger")
            return render_template("instances/import.html", form=request.form)

        if not label:
            label = slug.replace("-", " ").title()

        database_url = build_sqlite_url(slug)
        target_path = database_file_for_url(database_url)
        if target_path is None:
            flash("Impossible de calculer le chemin cible.", "danger")
            return render_template("instances/import.html", form=request.form)
        if target_path.exists() and target_path.stat().st_size > 0:
            flash(
                f"Le fichier {target_path.name} existe déjà sans instance enregistrée — "
                "déplacez-le ou supprimez-le manuellement avant l'import.",
                "danger",
            )
            return render_template("instances/import.html", form=request.form)

        try:
            instance_backup.stage_upload_to_path(uploaded, target_path, slug)
        except instance_backup.BackupError as e:
            flash(str(e), "danger")
            return render_template("instances/import.html", form=request.form)

        inst = Instance(slug=slug, label=label, database_url=database_url, is_active=True)
        db.session.add(inst)
        db.session.commit()
        flash(
            f"Instance « {label} » créée depuis l'upload (slug : {slug}).",
            "success",
        )
        return redirect(url_for("instances.detail", instance_id=inst.id))

    return render_template("instances/import.html", form={})


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
        mimetype="application/zip" if filename.endswith(".zip") else "application/octet-stream",
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
