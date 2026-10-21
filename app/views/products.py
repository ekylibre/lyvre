from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.extensions import db
from app.models import Account, Product
from app.models.product import PRODUCT_KINDS
from app.services.catalog import CatalogError, format_rate, usage_count, validate_product_data

bp = Blueprint("products", __name__, url_prefix="/products")


def _accounts(prefix):
    return (Account.query.filter(Account.code.like(f"{prefix}%"), Account.is_header.is_(False))
            .order_by(Account.code).all())


def _form_state(product: Product | None) -> dict:
    if product is None:
        return {"kind": "purchase"}
    return {
        "name": product.name,
        "reference": product.reference or "",
        "kind": product.kind,
        "purchase_account_code": product.purchase_account.code if product.purchase_account else "",
        "sale_account_code": product.sale_account.code if product.sale_account else "",
        "vat_rate": format_rate(product.vat_rate_bp).replace(" %", ""),
    }


def _render_form(product, form):
    return render_template(
        "products/form.html", product=product, form=form, kinds=PRODUCT_KINDS,
        purchase_accounts=_accounts("6"), sale_accounts=_accounts("7"),
    )


@bp.route("/")
@login_required
def index():
    show_archived = request.args.get("archived") == "1"
    query = Product.query
    if not show_archived:
        query = query.filter(Product.active.is_(True))
    products = query.order_by(Product.name).all()
    return render_template("products/index.html", products=products, kinds=dict(PRODUCT_KINDS),
                           show_archived=show_archived,
                           usages={p.id: usage_count(p) for p in products})


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    if request.method == "POST":
        try:
            data = validate_product_data(request.form)
        except CatalogError as e:
            flash(str(e), "danger")
            return _render_form(None, request.form)
        product = Product(**data)
        db.session.add(product)
        db.session.commit()
        flash(f"Produit « {product.name} » créé.", "success")
        return redirect(url_for("products.index"))
    return _render_form(None, _form_state(None))


@bp.route("/<int:product_id>/edit", methods=["GET", "POST"])
@login_required
def edit(product_id):
    product = Product.query.get_or_404(product_id)
    if request.method == "POST":
        try:
            data = validate_product_data(request.form, product_id=product.id)
        except CatalogError as e:
            flash(str(e), "danger")
            return _render_form(product, request.form)
        for key, value in data.items():
            setattr(product, key, value)
        db.session.commit()
        flash(f"Produit « {product.name} » mis à jour.", "success")
        return redirect(url_for("products.index"))
    return _render_form(product, _form_state(product))


@bp.route("/<int:product_id>/archive", methods=["POST"])
@login_required
def archive(product_id):
    product = Product.query.get_or_404(product_id)
    product.active = not product.active
    db.session.commit()
    flash(f"Produit « {product.name} » {'réactivé' if product.active else 'archivé'}.", "success")
    return redirect(url_for("products.index"))


@bp.route("/<int:product_id>/delete", methods=["POST"])
@login_required
def delete(product_id):
    product = Product.query.get_or_404(product_id)
    used = usage_count(product)
    if used:
        flash(f"Impossible de supprimer « {product.name} » : utilisé {used} fois. "
              "Archivez-le plutôt.", "danger")
        return redirect(url_for("products.index"))
    db.session.delete(product)
    db.session.commit()
    flash(f"Produit « {product.name} » supprimé.", "success")
    return redirect(url_for("products.index"))
