from datetime import datetime
from app.extensions import db


PAYMENT_STATUSES = [
    ("authorized", "Autorisé"),
    ("to_capture", "À capturer"),
    ("captured", "Capturé"),
    ("paid", "Payé"),
    ("refused", "Refusé"),
    ("expired", "Expiré"),
    ("canceled", "Annulé"),
    ("disputed", "En litige"),
    ("failed", "Échec"),
]


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    stancer_id = db.Column(db.String(64), unique=True, nullable=False)
    payout_id = db.Column(
        db.Integer,
        db.ForeignKey("payouts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    amount_cents = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(3), nullable=False, default="EUR")
    status = db.Column(db.String(20))
    method = db.Column(db.String(20))
    description = db.Column(db.String(500))
    order_id = db.Column(db.String(64))
    unique_id = db.Column(db.String(64))
    customer_email = db.Column(db.String(200))
    customer_name = db.Column(db.String(200))
    date_payment = db.Column(db.DateTime)
    raw_payload = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    imported_at = db.Column(db.DateTime, default=datetime.utcnow)

    payout = db.relationship("Payout", backref=db.backref("payments", lazy="dynamic"))

    def __repr__(self):
        return f"<Payment {self.stancer_id} {self.amount_cents}>"
