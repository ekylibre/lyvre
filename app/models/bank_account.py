from datetime import datetime
from app.extensions import db


class BankAccount(db.Model):
    __tablename__ = "bank_accounts"

    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(100), nullable=False)
    iban = db.Column(db.String(34))
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    # Lien Qonto : compte Qonto synchronisé, date de début, curseur de la dernière synchro réussie (UTC).
    qonto_account_id = db.Column(db.String(36), unique=True, nullable=True)
    qonto_sync_from = db.Column(db.Date, nullable=True)
    qonto_synced_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    account = db.relationship("Account", back_populates="bank_accounts")
    transactions = db.relationship("BankTransaction", back_populates="bank_account", lazy="dynamic")

    def __repr__(self):
        return f"<BankAccount {self.label}>"
