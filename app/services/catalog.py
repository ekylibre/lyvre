"""Catalogue produits / services : comptes d'achat et de vente, taux de TVA.

Les taux sont stockés en points de base (2000 = 20 %, 550 = 5,5 %) pour éviter
les flottants ; Qonto les donne en chaînes (« 20 », « 5.5 », « 22.00 »).
"""
from decimal import Decimal, InvalidOperation

from app.extensions import db
from app.models import Account, Entity, Product, PurchaseLine
from app.models.product import PRODUCT_KINDS

DEFAULT_PURCHASE_PRODUCT = "Achats divers"
# Compte du produit par défaut : le premier présent dans le plan (asso : 6068, SCI : 628).
DEFAULT_PURCHASE_ACCOUNTS = ("6068", "628", "606")

KIND_LABELS = dict(PRODUCT_KINDS)


class CatalogError(ValueError):
    pass


def parse_rate_bp(value) -> int | None:
    """« 20 » → 2000, « 5,5 » / « 5.5 » → 550, vide → None ; ValueError si invalide."""
    if value is None:
        return None
    text = str(value).strip().replace(",", ".").rstrip("%").strip()
    if not text:
        return None
    try:
        rate = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"Taux de TVA invalide : « {value} ».") from None
    if rate < 0 or rate > 100:
        raise ValueError(f"Taux de TVA hors limites : « {value} ».")
    bp = rate * 100
    if bp != bp.to_integral_value():
        raise ValueError(f"Taux de TVA trop précis : « {value} ».")
    return int(bp)


def format_rate(bp) -> str:
    """2000 → « 20 % », 550 → « 5,5 % », None → « »."""
    if bp is None:
        return ""
    text = f"{Decimal(bp) / 100:f}".rstrip("0").rstrip(".") if bp % 100 else str(bp // 100)
    return f"{text.replace('.', ',')} %"


def default_purchase_product() -> Product:
    """Produit « Achats divers », créé à la demande (sans commit)."""
    product = Product.query.filter_by(name=DEFAULT_PURCHASE_PRODUCT).first()
    if product is not None:
        return product
    account = None
    for code in DEFAULT_PURCHASE_ACCOUNTS:
        account = Account.query.filter_by(code=code, is_header=False).first()
        if account is not None:
            break
    product = Product(name=DEFAULT_PURCHASE_PRODUCT, kind="purchase",
                      purchase_account_id=account.id if account else None)
    db.session.add(product)
    db.session.flush()
    return product


def ensure_default_purchase_product() -> Product:
    """« Achats divers » enregistré : la ligne proposée par défaut désigne un produit de la liste."""
    product = default_purchase_product()
    if product.id is None:
        db.session.commit()
    return product


def remember_supplier_product(entity: Entity | None, lines) -> None:
    """Le produit choisi sur une facture devient le produit par défaut du fournisseur qui n'en a
    pas encore (hors « Achats divers ») ; les factures suivantes le proposent. Sans commit."""
    if entity is None or entity.default_product_id is not None:
        return
    generic = Product.query.filter_by(name=DEFAULT_PURCHASE_PRODUCT).first()
    chosen = next((line.product_id for line in lines if line.product_id
                   and (generic is None or line.product_id != generic.id)), None)
    if chosen is not None:
        entity.default_product_id = chosen


def product_for(entity: Entity | None) -> Product:
    """Produit des lignes d'achat d'un fournisseur : son produit par défaut s'il est actif."""
    if entity is not None and entity.default_product is not None and entity.default_product.active:
        return entity.default_product
    return default_purchase_product()


def sale_products():
    """Produits actifs utilisables à la vente, par nom."""
    return (Product.query.filter(Product.active.is_(True), Product.kind.in_(("sale", "both")))
            .order_by(Product.name).all())


def purchase_products():
    """Produits actifs utilisables à l'achat, par nom."""
    return (Product.query.filter(Product.active.is_(True), Product.kind.in_(("purchase", "both")))
            .order_by(Product.name).all())


def usage_count(product: Product) -> int:
    """Lignes de facture (achat et vente) et fiches fournisseur qui utilisent le produit."""
    from app.models import SaleLine

    lines = PurchaseLine.query.filter_by(product_id=product.id).count()
    lines += SaleLine.query.filter_by(product_id=product.id).count()
    entities = Entity.query.filter_by(default_product_id=product.id).count()
    return lines + entities


def _account(code, prefix, label):
    code = (code or "").strip()
    if not code:
        return None
    account = Account.query.filter_by(code=code).first()
    if account is None:
        raise CatalogError(f"{label} : compte « {code} » introuvable dans le plan comptable.")
    if account.is_header:
        raise CatalogError(f"{label} : « {code} » est un compte d'en-tête, non utilisable.")
    if not code.startswith(prefix):
        raise CatalogError(f"{label} : le compte doit commencer par {prefix} (« {code} »).")
    return account


def validate_product_data(form, product_id=None) -> dict:
    """Champs d'un produit à partir d'un formulaire ; CatalogError si invalide."""
    name = (form.get("name") or "").strip()
    if not name:
        raise CatalogError("Le libellé est obligatoire.")
    duplicate = Product.query.filter(Product.name == name)
    if product_id is not None:
        duplicate = duplicate.filter(Product.id != product_id)
    if duplicate.first():
        raise CatalogError(f"Un produit nommé « {name} » existe déjà.")
    kind = form.get("kind") or "purchase"
    if kind not in KIND_LABELS:
        raise CatalogError(f"Sens inconnu : « {kind} ».")

    purchase_account = _account(form.get("purchase_account_code"), "6", "Compte d'achat")
    sale_account = _account(form.get("sale_account_code"), "7", "Compte de vente")
    if kind in ("purchase", "both") and purchase_account is None:
        raise CatalogError("Un produit d'achat doit avoir un compte d'achat (6…).")
    if kind in ("sale", "both") and sale_account is None:
        raise CatalogError("Un produit de vente doit avoir un compte de vente (7…).")
    try:
        vat_rate_bp = parse_rate_bp(form.get("vat_rate"))
    except ValueError as e:
        raise CatalogError(str(e)) from None

    # Vente : prix unitaire HT, unité, description reprise sur la facture, nature (TVA).
    price_text = (form.get("sale_price") or "").strip().replace(" ", "").replace(",", ".")
    try:
        sale_price = Decimal(price_text) if price_text else None
    except InvalidOperation:
        raise CatalogError(f"Prix de vente invalide : « {form.get('sale_price')} ».") from None
    if sale_price is not None and sale_price < 0:
        raise CatalogError("Le prix de vente ne peut pas être négatif.")
    nature = form.get("nature") or "services"
    if nature not in ("goods", "services"):
        raise CatalogError(f"Nature inconnue : « {nature} ».")

    return {
        "name": name[:200],
        "reference": (form.get("reference") or "").strip()[:50] or None,
        "kind": kind,
        "purchase_account_id": purchase_account.id if kind != "sale" else None,
        "sale_account_id": sale_account.id if kind != "purchase" else None,
        "vat_rate_bp": vat_rate_bp,
        "sale_price_cents": int((sale_price * 100).quantize(Decimal("1"))) if sale_price is not None and kind != "purchase" else None,
        "unit": (form.get("unit") or "").strip()[:20] or None,
        "description": (form.get("description") or "").strip() or None,
        "nature": nature,
    }
