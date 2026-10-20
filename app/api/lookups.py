"""Autocompletion for the entry form: accounts and entities."""
import unicodedata

from flask import jsonify, request
from flask_login import login_required

from app.models import Account, Entity

from . import bp

MAX_LIMIT = 50


def _fold(text):
    """Lowercase without accents, for accent-insensitive matching."""
    normalized = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in normalized if not unicodedata.combining(c)).lower()


def _limit():
    return max(1, min(request.args.get("limit", 20, type=int), MAX_LIMIT))


def _matches(query, *texts):
    """Every word of the query appears in one of the texts."""
    haystack = " ".join(_fold(t) for t in texts)
    return all(word in haystack for word in _fold(query).split())


@bp.route("/accounts")
@login_required
def accounts():
    """Postable accounts (no headers): code prefix first, then label words."""
    q = (request.args.get("q") or "").strip()
    rows = Account.query.filter_by(is_header=False).order_by(Account.code).all()
    if q:
        by_code = [a for a in rows if a.code.startswith(q)]
        seen = {a.id for a in by_code}
        by_label = [a for a in rows if a.id not in seen and _matches(q, a.label)]
        rows = by_code + by_label
    return jsonify(results=[
        {"id": a.id, "code": a.code, "label": a.label} for a in rows[:_limit()]
    ])


@bp.route("/entities")
@login_required
def entities():
    q = (request.args.get("q") or "").strip()
    rows = Entity.query.order_by(Entity.name).all()
    if q:
        rows = [e for e in rows if _matches(q, e.name, e.email or "")]
    return jsonify(results=[
        {"id": e.id, "name": e.name, "type": e.entity_type, "email": e.email,
         "account_code": e.account_code}
        for e in rows[:_limit()]
    ])
