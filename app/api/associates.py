"""Associés d'une société (module « Associés », lot A1) : liste à une date, fiche, création,
modification et suppression. Lecture pour tous les membres ; écriture par l'administrateur de
l'instance (claudedocs/design_associes.md §5). Option désactivée : 404 `feature_disabled`.
"""
from datetime import date

from flask import jsonify, request

from app.access import instance_admin_required
from app.models import Associate, Entity
from app.services import associates
from app.services.associates import AssociateError

from . import ApiError, bp, get_or_404, invalid, json_body, notice


def _require_enabled():
    if not associates.enabled():
        raise ApiError("feature_disabled", "Module Associés désactivé pour cette instance "
                       "(Configuration › Structure).", status=404)


def _at() -> date | None:
    raw = request.args.get("at")
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise invalid("Date de situation invalide (AAAA-MM-JJ).", "at") from None


def _error(exc: AssociateError) -> ApiError:
    return invalid(str(exc), exc.field)


def _item(associate: Associate, at: date | None = None) -> dict:
    held = associates.holdings(at)
    return associates.summary(associate, held, associates.capital_parts(held), at)


@bp.route("/associates")
def associates_list():
    _require_enabled()
    at = _at()
    data = associates.listing(at)
    taken = {a["entity_id"] for a in data["items"]}
    return jsonify(items=data["items"], meta={
        "at": (at or date.today()).isoformat(), "total_parts": data["total_parts"],
        "balances_total_cents": data["balances_total_cents"],
        "next_account_code": _next_code(),
        "entities": [{"value": str(e.id), "label": e.name}
                     for e in Entity.query.order_by(Entity.name) if e.id not in taken],
    })


def _next_code() -> str | None:
    try:
        return associates.next_account_code()
    except AssociateError:
        return None


@bp.route("/associates", methods=["POST"])
@instance_admin_required
def associates_create():
    _require_enabled()
    try:
        associate = associates.create(json_body())
    except AssociateError as exc:
        raise _error(exc) from None
    return jsonify(item=_item(associate), notices=[notice(
        f"{associate.name} ajouté aux associés (compte courant {associate.account.code}).")]), 201


@bp.route("/associates/<int:associate_id>")
def associates_detail(associate_id):
    _require_enabled()
    associate = get_or_404(Associate, associate_id, "Associé introuvable.")
    return jsonify(item=_item(associate, _at()), meta={
        "can_delete": not associates.delete_blockers(associate),
        "account_locked": associates.has_entries(associate.account),
    })


@bp.route("/associates/<int:associate_id>", methods=["PATCH"])
@instance_admin_required
def associates_update(associate_id):
    _require_enabled()
    associate = get_or_404(Associate, associate_id, "Associé introuvable.")
    try:
        associates.update(associate, json_body())
    except AssociateError as exc:
        raise _error(exc) from None
    return jsonify(item=_item(associate), notices=[notice(f"Associé {associate.name} enregistré.")])


@bp.route("/associates/<int:associate_id>", methods=["DELETE"])
@instance_admin_required
def associates_delete(associate_id):
    _require_enabled()
    associate = get_or_404(Associate, associate_id, "Associé introuvable.")
    name = associate.name
    try:
        associates.delete(associate)
    except AssociateError as exc:
        raise ApiError("conflict", str(exc), status=409) from None
    return jsonify(notices=[notice(f"{name} retiré des associés (l'entité et son compte sont conservés).")])
