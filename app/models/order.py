from datetime import datetime
from app.extensions import db


POS_ORDER_STATES = [
    ("draft", "Brouillon"),
    ("paid", "Payée"),
    ("done", "Comptabilisée"),
    ("invoiced", "Facturée"),
    ("cancel", "Annulée"),
]


class Order(db.Model):
    """Commande du point de vente Odoo (pos.order)."""
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    odoo_id = db.Column(db.Integer, unique=True, nullable=False, index=True)
    name = db.Column(db.String(200))
    pos_reference = db.Column(db.String(200), index=True)
    state = db.Column(db.String(20))
    session_id = db.Column(db.Integer)
    session_name = db.Column(db.String(200))
    partner_id = db.Column(db.Integer)
    partner_name = db.Column(db.String(200))
    user_id = db.Column(db.Integer)
    user_name = db.Column(db.String(200))
    company_id = db.Column(db.Integer)
    date_order = db.Column(db.DateTime, index=True)
    amount_total_cents = db.Column(db.Integer, nullable=False, default=0)
    amount_tax_cents = db.Column(db.Integer, nullable=False, default=0)
    amount_paid_cents = db.Column(db.Integer, nullable=False, default=0)
    amount_return_cents = db.Column(db.Integer, nullable=False, default=0)
    currency = db.Column(db.String(3), nullable=False, default="EUR")
    note = db.Column(db.Text)
    raw_payload = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    imported_at = db.Column(db.DateTime, default=datetime.utcnow)

    lines = db.relationship(
        "OrderLine",
        backref="order",
        lazy="dynamic",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    payments = db.relationship(
        "OrderPayment",
        backref="order",
        lazy="dynamic",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self):
        return f"<Order {self.odoo_id} {self.name}>"
