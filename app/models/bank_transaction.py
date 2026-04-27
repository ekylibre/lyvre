from datetime import datetime
from app.extensions import db


class BankTransaction(db.Model):
    __tablename__ = "bank_transactions"

    id = db.Column(db.Integer, primary_key=True)
    bank_account_id = db.Column(db.Integer, db.ForeignKey("bank_accounts.id"), nullable=False)
    fitid = db.Column(db.String(100), nullable=False)
    transaction_date = db.Column(db.Date, nullable=False)
    value_date = db.Column(db.Date)
    amount_cents = db.Column(db.Integer, nullable=False)
    label = db.Column(db.String(500))
    raw_type = db.Column(db.String(20))
    reconciled = db.Column(db.Boolean, default=False, nullable=False)
    journal_line_id = db.Column(db.Integer, db.ForeignKey("journal_lines.id"), nullable=True)
    entity_id = db.Column(db.Integer, db.ForeignKey("entities.id"), nullable=True)
    category = db.Column(db.String(100))
    imported_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("bank_account_id", "fitid", name="uq_bank_transaction_fitid"),
    )

    bank_account = db.relationship("BankAccount", back_populates="transactions")
    journal_line = db.relationship("JournalLine", back_populates="bank_transaction")
    entity = db.relationship("Entity", back_populates="transactions")

    def __repr__(self):
        return f"<BankTransaction {self.fitid} {self.amount_cents}>"
