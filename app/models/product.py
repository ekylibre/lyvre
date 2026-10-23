from datetime import datetime

from app.extensions import db

PRODUCT_KINDS = [
    ("purchase", "Achat"),
    ("sale", "Vente"),
    ("both", "Achat et vente"),
]


class Product(db.Model):
    """Produit ou service du catalogue : porte les comptes d'achat / de vente et la TVA."""

    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)
    reference = db.Column(db.String(50))
    kind = db.Column(db.String(10), nullable=False, default="purchase")
    purchase_account_id = db.Column(
        db.Integer, db.ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    sale_account_id = db.Column(
        db.Integer, db.ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    # Taux de TVA en points de base (2000 = 20 %) ; NULL = pas de taux par défaut.
    vat_rate_bp = db.Column(db.Integer)
    # Ventes : description et unité reprises sur la ligne, prix unitaire HT de vente, nature
    # (biens / services : exigibilité de la TVA).
    description = db.Column(db.Text)
    unit = db.Column(db.String(20))
    sale_price_cents = db.Column(db.Integer)
    nature = db.Column(db.String(8), nullable=False, default="services", server_default="services")
    active = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    purchase_account = db.relationship("Account", foreign_keys=[purchase_account_id])
    sale_account = db.relationship("Account", foreign_keys=[sale_account_id])

    def __repr__(self):
        return f"<Product {self.name}>"
