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


class FecUnavailable(Exception):
    """FEC impossible à fournir : `status` HTTP (404 fichier figé absent, 409 sinon) et motif."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def fec_content(fy: FiscalYear) -> tuple[bytes, str]:
    """(contenu, nom) du FEC : figé à la clôture définitive (empreinte vérifiée), sinon produit à la demande."""
    if fy.is_final and fy.fec_path:
        path = os.path.join(current_app.instance_path, fy.fec_path)
        if not os.path.isfile(path):
            raise FecUnavailable(404, "Le FEC figé à la clôture est introuvable.")
        with open(path, "rb") as fh:
            content = fh.read()
        if hashlib.sha256(content).hexdigest() != fy.fec_sha256:
            current_app.logger.error("FEC %s altéré : empreinte différente", path)
            raise FecUnavailable(409, "Le FEC figé a été modifié depuis la clôture (empreinte différente).")
        return content, os.path.basename(path)
    try:
        fec_file = fec.build(fy)
    except fec.FecError as exc:
        raise FecUnavailable(409, " ".join(exc.errors[:5])) from None
    return fec_file.content, fec_file.filename


@bp.route("/fiscal-years/<int:fy_id>/fec")
@login_required
def download(fy_id):
    fy = db.session.get(FiscalYear, fy_id)
    if fy is None:
        abort(404)
    try:
        content, name = fec_content(fy)
    except FecUnavailable as exc:
        abort(exc.status, str(exc))
    return send_file(io.BytesIO(content), mimetype="text/plain; charset=iso-8859-15", as_attachment=True,
                     download_name=name)


@bp.route("/fiscal-years/<int:fy_id>/accountant-archive.zip")
@login_required
def accountant_archive(fy_id):
    """Archive de l'exercice pour l'expert-comptable (lot RQ4) : FEC (s'il peut être produit), relevés de
    compte des mois de l'exercice, LISEZMOI (contenu, FEC absent, relevés manquants). Tous les rôles."""
    from app.services import bank_statements

    fy = db.session.get(FiscalYear, fy_id)
    if fy is None:
        abort(404)
    try:
        fec_file = fec_content(fy)
    except FecUnavailable as exc:
        fec_file = None
        fec_reason = str(exc)
    content, name = bank_statements.accountant_archive(fy, fec_file, None if fec_file else fec_reason)
    return send_file(io.BytesIO(content), mimetype="application/zip", as_attachment=True, download_name=name)
