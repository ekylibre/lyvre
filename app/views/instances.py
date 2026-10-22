"""Instances : téléchargement d'une sauvegarde servi par Flask (écrans : SPA, API :
app/api/instances.py)."""
from flask import Blueprint, abort, send_file
from flask_login import login_required

from app.decorators import admin_required
from app.extensions import db
from app.models import Instance
from app.services import instance_backup
from app.services.instance_backup import BackupError

bp = Blueprint("instances", __name__, url_prefix="/instances")


@bp.route("/<int:instance_id>/backups/<filename>/download")
@login_required
@admin_required
def download_backup(instance_id, filename):
    inst = db.session.get(Instance, instance_id)
    if inst is None:
        abort(404)
    try:
        path = instance_backup.backup_path(inst, filename)
    except BackupError:
        abort(404)
    return send_file(
        path,
        as_attachment=True,
        download_name=filename,
        mimetype="application/zip" if filename.endswith(".zip") else "application/octet-stream",
    )
