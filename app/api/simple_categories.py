"""Catégories de recettes et de dépenses (comptabilité simplifiée, lot D.2)."""
from contextlib import contextmanager

from flask import jsonify

from app.extensions import db
from app.models import Account, SimpleCategory
from app.services import simple_categories

from . import ApiError, bp, get_or_404, json_body, notice


@contextmanager
def _errors():
    try:
        yield
    except simple_categories.CategoryError as exc:
        db.session.rollback()
        raise ApiError("validation_error", exc.message, exc.status, {exc.field: exc.message} if exc.field else None) from None


def _accounts(prefix):
    return [{"value": str(a.id), "label": f"{a.code} — {a.label}"}
            for a in Account.query.filter(Account.code.like(f"{prefix}%"), Account.is_header.is_(False)).order_by(Account.code)]


@bp.route("/simple-categories")
def simple_categories_list():
    """Catégories (créées depuis le plan au premier accès), nombre d'utilisations, comptes proposés."""
    counts = simple_categories.usage_counts()
    items = [simple_categories.payload(c, counts.get(c.id, 0)) for c in simple_categories.listing()]
    return jsonify(items=items, meta={"income_accounts": _accounts("7"), "expense_accounts": _accounts("6")})


@bp.route("/simple-categories", methods=["POST"])
def simple_categories_create():
    """`{label, kind (income|expense), account_id, active}`."""
    with _errors():
        category = simple_categories.save(None, json_body())
    return jsonify(item=simple_categories.payload(category), notices=[notice(f"Catégorie « {category.label} » créée.")]), 201


@bp.route("/simple-categories/<int:category_id>", methods=["PUT"])
def simple_categories_update(category_id):
    category = get_or_404(SimpleCategory, category_id, "Catégorie introuvable.")
    with _errors():
        simple_categories.save(category, json_body())
    return jsonify(item=simple_categories.payload(category), notices=[notice(f"Catégorie « {category.label} » enregistrée.")])


@bp.route("/simple-categories/<int:category_id>/move", methods=["POST"])
def simple_categories_move(category_id):
    """`{direction: up|down}` dans sa liste (recettes ou dépenses)."""
    category = get_or_404(SimpleCategory, category_id, "Catégorie introuvable.")
    simple_categories.move(category, json_body().get("direction"))
    return jsonify(ok=True)
