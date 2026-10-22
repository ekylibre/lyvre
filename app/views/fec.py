"""Téléchargement du FEC d'un exercice (tous les rôles, expert-comptable compris).

Exercice clôturé définitivement : le fichier figé à la clôture (empreinte vérifiée). Sinon, FEC
généré à la demande (exercice au moins en clôture provisoire). Contrôles détaillés :
`GET /api/v1/fiscal-years/<id>/fec/check`.
"""
import hashlib
import io
import os

from flask import Blueprint, abort, current_app, send_file
from flask_login import login_required

from app.extensions import db
from app.models import FiscalYear
from app.services import fec

bp = Blueprint("fec", __name__)


@bp.route("/fiscal-years/<int:fy_id>/fec")
@login_required
def download(fy_id):
    fy = db.session.get(FiscalYear, fy_id)
    if fy is None:
        abort(404)
    if fy.is_final and fy.fec_path:
        path = os.path.join(current_app.instance_path, fy.fec_path)
        if not os.path.isfile(path):
            abort(404)
        with open(path, "rb") as fh:
            content = fh.read()
        if hashlib.sha256(content).hexdigest() != fy.fec_sha256:
            current_app.logger.error("FEC %s altéré : empreinte différente", path)
            abort(409, "Le FEC figé a été modifié depuis la clôture (empreinte différente).")
        name = os.path.basename(path)
    else:
        try:
            fec_file = fec.build(fy)
        except fec.FecError as exc:
            abort(409, " ".join(exc.errors[:5]))
        content, name = fec_file.content, fec_file.filename
    return send_file(io.BytesIO(content), mimetype="text/plain; charset=iso-8859-15", as_attachment=True,
                     download_name=name)
