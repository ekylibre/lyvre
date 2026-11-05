"""Listes de contrôle guidées (lot AG9b.e, AG9.6) : listes en cours ou à venir, étapes cochées à la main."""
from datetime import date

from flask import jsonify, request
from flask_login import current_user

from app.extensions import db
from app.services import checklists
from app.services.checklists import ChecklistError

from . import ApiError, bp, json_body, notice


def _require():
    if not checklists.enabled():
        raise ApiError("not_found", "Listes de contrôle réservées aux exploitations agricoles.", 404)


@bp.route("/checklists")
def checklists_list():
    _require()
    raw = request.args.get("on")
    try:
        on = date.fromisoformat(raw) if raw else None
    except ValueError:
        raise ApiError("validation_error", "Date attendue (AAAA-MM-JJ).", 422) from None
    return jsonify(item=checklists.listing(on))


@bp.route("/checklists/<checklist_id>/<period>/steps/<step_id>", methods=["PUT"])
def checklists_mark(checklist_id, period, step_id):
    _require()
    done = json_body().get("done") is True
    try:
        checklists.mark(checklist_id, period, step_id, done, getattr(current_user, "id", None))
        db.session.commit()
    except ChecklistError as exc:
        db.session.rollback()
        raise ApiError("not_found" if exc.status == 404 else "validation_error", exc.message, exc.status) from None
    return jsonify(notices=[notice("Étape cochée." if done else "Étape décochée.")])
