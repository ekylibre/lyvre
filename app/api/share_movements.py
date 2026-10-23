"""Registre des parts (module « Associés », lot A2) : mouvements, situation et capital à une date,
prévisualisation, pièce jointe. Lecture pour tous les membres ; saisie par l'administrateur de
l'instance (claudedocs/design_associes.md §5).

Création et modification acceptent du JSON, ou un formulaire multipart (`payload` : le JSON,
`attachment` : la pièce, PDF / JPEG / PNG).
"""
import json
from datetime import date

from flask import abort, jsonify, request, send_file
from flask_login import current_user

from app.access import instance_admin_required
from app.models import Associate, Entity
from app.models.associate import ShareMovement
from app.services import associates, attachments, share_register
from app.services.attachments import AttachmentError
from app.services.share_register import RegisterError

from . import ApiError, bp, get_or_404, invalid, json_body, notice
from .associates import _at, _require_enabled


def _error(exc: RegisterError) -> ApiError:
    return ApiError("validation_error", str(exc), status=422, fields=exc.fields or None)


def _form():
    """(données, jeton de la pièce ou None) d'une requête JSON ou multipart."""
    if request.files or request.form:
        try:
            data = json.loads(request.form.get("payload") or "{}")
        except ValueError:
            raise invalid("Formulaire illisible.") from None
        upload = request.files.get("attachment")
        token = None
        if upload is not None and upload.filename:
            try:
                token = attachments.stage(upload)
            except AttachmentError as exc:
                raise invalid(str(exc), "attachment") from None
        return data, token
    return json_body(), None


def _meta(at: date | None) -> dict:
    listing = associates.listing(at)
    held = associates.holdings(at)
    return {
        "at": (at or date.today()).isoformat(),
        "capital": share_register.capital(at, held),
        "situation": listing["items"],
        "kinds": [{"value": k, "label": l} for k, l in share_register.KIND_LABELS.items()],
        "natures": [{"value": k, "label": l} for k, l in share_register.NATURE_LABELS.items()],
        "associates": [{"value": str(a.id), "label": a.name}
                       for a in Associate.query.join(Entity).order_by(Entity.name)],
    }


@bp.route("/share-movements")
def share_movements_list():
    _require_enabled()
    at = _at()
    associate_id = request.args.get("associate_id", type=int)
    items = share_register.movements(associate_id, at)
    return jsonify(items=[share_register.payload(m) for m in items], meta=_meta(at))


@bp.route("/share-movements/preview", methods=["POST"])
@instance_admin_required
def share_movements_preview():
    """Situation juste après le mouvement saisi, sans rien enregistrer ; 422 s'il est refusé."""
    _require_enabled()
    data = json_body()
    exclude = data.get("id")
    try:
        clean = share_register.parse(data)
        share_register.validate(clean, exclude_id=exclude)
    except RegisterError as exc:
        raise _error(exc) from None
    held = share_register.situation_after(clean, exclude_id=exclude)
    total = associates.capital_parts(held)
    names = {a.id: a.name for a in Associate.query.filter(Associate.id.in_(list(held))).all()} if held else {}
    rows = [{"associate_id": a, "name": names.get(a, "?"), "parts": parts,
             "percent": {n: round(100 * v / total, 2) if total else 0.0 for n, v in parts.items()}}
            for a, parts in held.items() if any(parts.values())]
    return jsonify(rows=sorted(rows, key=lambda r: r["name"]), total_parts=total)


@bp.route("/share-movements", methods=["POST"])
@instance_admin_required
def share_movements_create():
    _require_enabled()
    data, token = _form()
    try:
        movement = share_register.create(data, token, user_id=current_user.id)
    except RegisterError as exc:
        raise _error(exc) from None
    return jsonify(item=share_register.payload(movement), notices=[notice(
        f"{movement.movement_date:%d/%m/%Y} — {share_register.KIND_LABELS[movement.kind]} enregistrée au registre.")]), 201


@bp.route("/share-movements/<int:movement_id>", methods=["PATCH", "POST"])  # POST : multipart avec pièce
@instance_admin_required
def share_movements_update(movement_id):
    _require_enabled()
    movement = get_or_404(ShareMovement, movement_id, "Mouvement introuvable.")
    data, token = _form()
    try:
        share_register.update(movement, data, token)
    except RegisterError as exc:
        raise _error(exc) from None
    return jsonify(item=share_register.payload(movement), notices=[notice("Mouvement enregistré.")])


@bp.route("/share-movements/<int:movement_id>", methods=["DELETE"])
@instance_admin_required
def share_movements_delete(movement_id):
    _require_enabled()
    movement = get_or_404(ShareMovement, movement_id, "Mouvement introuvable.")
    try:
        share_register.delete(movement)
    except RegisterError as exc:
        raise ApiError("conflict", str(exc), status=409) from None
    return jsonify(notices=[notice("Mouvement supprimé du registre.")])


@bp.route("/share-movements/<int:movement_id>/attachment")
def share_movements_attachment(movement_id):
    _require_enabled()
    movement = get_or_404(ShareMovement, movement_id, "Mouvement introuvable.")
    path = attachments.path_of(movement)
    if path is None:
        abort(404)
    return send_file(path, mimetype=movement.attachment_mime, download_name=movement.attachment_name or path.name,
                     as_attachment=bool(request.args.get("download")))
