from datetime import datetime
from app.extensions import db


PAYOUT_STATUSES = [
    ("pending", "En attente"),
    ("to_pay", "À verser"),
    ("in_progress", "En cours"),
    ("paid", "Versé"),
    ("done", "Versé"),
    ("failed", "Échec"),
]


class Payout(db.Model):
    __tablename__ = "payouts"

    id = db.Column(db.Integer, primary_key=True)
    stancer_id = db.Column(db.String(64), unique=True, nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(3), nullable=False, default="EUR")
    status = db.Column(db.String(20), nullable=False, default="pending")
    date_payout = db.Column(db.Date)
    date_bank = db.Column(db.Date)
    statement_description = db.Column(db.String(200))
    fees_cents = db.Column(db.Integer, default=0)
    description = db.Column(db.String(500))
    raw_payload = db.Column(db.Text)
    bank_transaction_id = db.Column(
        db.Integer,
        db.ForeignKey("bank_transactions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    imported_at = db.Column(db.DateTime, default=datetime.utcnow)

    bank_transaction = db.relationship("BankTransaction", foreign_keys=[bank_transaction_id])

    def __repr__(self):
        return f"<Payout {self.stancer_id} {self.amount_cents}>"
