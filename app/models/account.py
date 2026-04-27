from datetime import datetime
from app.extensions import db

ACCOUNT_TYPES = [
    ("ASSET", "Actif"),
    ("LIABILITY", "Passif"),
    ("EQUITY", "Capitaux propres"),
    ("EXPENSE", "Charge"),
    ("REVENUE", "Produit"),
    ("TIERS", "Compte de tiers"),
    ("OFFBALANCE", "Hors bilan"),
    ("OTHER", "Autre"),
]


class Account(db.Model):
    __tablename__ = "accounts"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    label = db.Column(db.String(255), nullable=False)
    account_type = db.Column(db.String(20), nullable=False, default="OTHER")
    is_header = db.Column(db.Boolean, default=False, nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    parent = db.relationship("Account", remote_side=[id], backref="children")
    journal_lines = db.relationship("JournalLine", back_populates="account", lazy="dynamic")
    bank_accounts = db.relationship("BankAccount", back_populates="account")

    @property
    def is_leaf(self):
        return not self.children

    def balance(self, start_date=None, end_date=None):
        """Returns (debit_cents, credit_cents) for this account within the date range."""
        from app.models.journal_entry import JournalEntry
        from app.models.journal_line import JournalLine

        q = db.session.query(
            db.func.coalesce(db.func.sum(JournalLine.debit_cents), 0),
            db.func.coalesce(db.func.sum(JournalLine.credit_cents), 0),
        ).join(JournalEntry).filter(JournalLine.account_id == self.id)

        if start_date:
            q = q.filter(JournalEntry.entry_date >= start_date)
        if end_date:
            q = q.filter(JournalEntry.entry_date <= end_date)

        return q.one()

    def __repr__(self):
        return f"<Account {self.code} {self.label}>"
