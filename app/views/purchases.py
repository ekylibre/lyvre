"""Pièces des factures d'achat servies par Flask (les écrans sont dans la SPA, l'API dans
app/api/purchases.py) : pièce rangée d'une facture et pièce déposée en cours de saisie."""
from flask import Blueprint, abort, request, send_file
from flask_login import login_required

from app.models import Purchase
from app.services import attachments
from app.services.attachments import AttachmentError

bp = Blueprint("purchases", __name__, url_prefix="/purchases")


@bp.route("/<int:purchase_id>/attachment")
@login_required
def attachment(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)
    path = attachments.path_of(purchase)
    if path is None:
        abort(404)
    return send_file(path, mimetype=purchase.attachment_mime,
                     as_attachment=bool(request.args.get("download")),
                     download_name=purchase.attachment_name or path.name)


@bp.route("/staged/<token>")
@login_required
def staged(token):
    try:
        path, meta = attachments.staged(token)
    except AttachmentError:
        abort(404)
    return send_file(path, mimetype=meta["mime"], download_name=meta["name"])
