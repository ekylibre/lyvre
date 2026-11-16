"""Catalogue des produits et services (comptes d'achat / de vente, TVA par défaut)."""
from flask import jsonify, request

from app.extensions import db
from app.models import Account, Product
from app.models.product import PRODUCT_KINDS
from app.services.catalog import CatalogError, format_rate, usage_count, validate_product_data

from . import ApiError, bp, get_or_404, invalid, json_body, notice


def _account_ref(a: Account | None):
    return {"id": a.id, "code": a.code, "label": a.label} if a else None


def product_payload(p: Product, usages: int | None = None) -> dict:
    return {
        "id": p.id, "name": p.name, "reference": p.reference, "kind": p.kind, "active": p.active,
        "purchase_account": _account_ref(p.purchase_account),
        "sale_account": _account_ref(p.sale_account),
        "vat_rate_bp": p.vat_rate_bp,
        "vat_rate": format_rate(p.vat_rate_bp).replace(" %", ""),
        "sale_price": "" if p.sale_price_cents is None else f"{p.sale_price_cents / 100:.2f}".replace(".", ","),
        "unit": p.unit or "", "description": p.description or "", "nature": p.nature,
        "usages": usage_count(p) if usages is None else usages,
    }


def _form(data: dict) -> dict:
    """Champs JSON → formulaire attendu par catalog.validate_product_data."""
    return {key: "" if data.get(key) is None else str(data.get(key))
            for key in ("name", "reference", "kind", "purchase_account_code",
                        "sale_account_code", "vat_rate", "sale_price", "unit", "description", "nature")}


def _accounts(prefix):
    return [{"code": a.code, "label": a.label} for a in
            Account.query.filter(Account.code.like(f"{prefix}%"), Account.is_header.is_(False))
            .order_by(Account.code)]


@bp.route("/products")
def products_list():
    query = Product.query
    if request.args.get("archived") != "1":
        query = query.filter(Product.active.is_(True))
    products = query.order_by(Product.name).all()
    return jsonify(
        items=[product_payload(p) for p in products],
        meta={"kinds": [{"value": v, "label": l} for v, l in PRODUCT_KINDS],
              "purchase_accounts": _accounts("6"), "sale_accounts": _accounts("7")},
    )


@bp.route("/products/agri-catalog", methods=["POST"])
def products_agri_catalog():
    """Exploitation agricole (lot AG1.e) : ajoute au catalogue les catégories d'articles agricoles absentes."""
    from app.access import current_role, permissions
    from app.services import agri_catalog
    from app.tenant import current_chart

    if current_chart() != "agri":
        raise ApiError("not_found", "Catalogue réservé aux exploitations agricoles.", 404)
    if not permissions(current_role())["write"]:
        raise ApiError("forbidden", "Lecture seule.", 403)
    result = agri_catalog.seed_catalog()
    return jsonify(result=result, notices=[notice(
        f"{result['created']} article(s) agricole(s) ajouté(s) au catalogue ; taux de TVA à vérifier.")])


@bp.route("/products", methods=["POST"])
def products_create():
    try:
        data = validate_product_data(_form(json_body()))
    except CatalogError as e:
        raise invalid(str(e)) from None
    product = Product(**data)
    db.session.add(product)
    db.session.commit()
    return jsonify(item=product_payload(product),
                   notices=[notice(f"Produit « {product.name} » créé.")]), 201


@bp.route("/products/<int:product_id>", methods=["PATCH"])
def products_update(product_id):
    product = get_or_404(Product, product_id, "Produit introuvable.")
    data = json_body()
    if set(data) == {"active"}:  # archiver / réactiver
        product.active = bool(data["active"])
        db.session.commit()
        state = "réactivé" if product.active else "archivé"
        return jsonify(item=product_payload(product), notices=[notice(f"Produit « {product.name} » {state}.")])
    try:
        fields = validate_product_data(_form(data), product_id=product.id)
    except CatalogError as e:
        raise invalid(str(e)) from None
    for key, value in fields.items():
        setattr(product, key, value)
    db.session.commit()
    return jsonify(item=product_payload(product),
                   notices=[notice(f"Produit « {product.name} » mis à jour.")])


@bp.route("/products/<int:product_id>", methods=["DELETE"])
def products_delete(product_id):
    product = get_or_404(Product, product_id, "Produit introuvable.")
    used = usage_count(product)
    if used:
        raise ApiError("conflict", f"Impossible de supprimer « {product.name} » : utilisé {used} fois. "
                       "Archivez-le plutôt.", status=409)
    db.session.delete(product)
    db.session.commit()
    return jsonify(notices=[notice(f"Produit « {product.name} » supprimé.")])
