from datetime import datetime
from app.extensions import db


class OrderLine(db.Model):
    """Ligne de commande POS (pos.order.line)."""
    __tablename__ = "order_lines"

    id = db.Column(db.Integer, primary_key=True)
    odoo_id = db.Column(db.Integer, unique=True, nullable=False, index=True)
    order_id = db.Column(
        db.Integer,
        db.ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id = db.Column(db.Integer)
    product_name = db.Column(db.String(300))
    full_product_name = db.Column(db.String(500))
    qty = db.Column(db.Float, nullable=False, default=0.0)
    price_unit_cents = db.Column(db.Integer, nullable=False, default=0)
    discount = db.Column(db.Float, nullable=False, default=0.0)
    price_subtotal_cents = db.Column(db.Integer, nullable=False, default=0)
    price_subtotal_incl_cents = db.Column(db.Integer, nullable=False, default=0)
    tax_ids = db.Column(db.String(200))
    note = db.Column(db.Text)
    raw_payload = db.Column(db.Text)
    imported_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<OrderLine {self.odoo_id} {self.product_name}>"
