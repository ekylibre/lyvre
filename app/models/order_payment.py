from datetime import datetime
from app.extensions import db


class OrderPayment(db.Model):
    """Paiement d'une commande POS (pos.payment)."""
    __tablename__ = "order_payments"

    id = db.Column(db.Integer, primary_key=True)
    odoo_id = db.Column(db.Integer, unique=True, nullable=False, index=True)
    order_id = db.Column(
        db.Integer,
        db.ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(200))
    payment_method_id = db.Column(db.Integer)
    payment_method_name = db.Column(db.String(200))
    amount_cents = db.Column(db.Integer, nullable=False, default=0)
    currency = db.Column(db.String(3), nullable=False, default="EUR")
    payment_date = db.Column(db.DateTime, index=True)
    card_type = db.Column(db.String(60))
    transaction_id = db.Column(db.String(200))
    raw_payload = db.Column(db.Text)
    imported_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<OrderPayment {self.odoo_id} {self.amount_cents}>"
