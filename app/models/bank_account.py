from datetime import datetime
from app.extensions import db


class BankAccount(db.Model):
    __tablename__ = "bank_accounts"

    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(100), nullable=False)
    iban = db.Column(db.String(34))
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    account = db.relationship("Account", back_populates="bank_accounts")
    transactions = db.relationship("BankTransaction", back_populates="bank_account", lazy="dynamic")

    def __repr__(self):
        return f"<BankAccount {self.label}>"
