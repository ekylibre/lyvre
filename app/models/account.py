from datetime import datetime

from sqlalchemy import event

from app.extensions import db

# Lot F3 : comptes de tiers lettrables par défaut (TVA 445 exclue) ; modifiable par compte.
LETTRABLE_PREFIXES = ("40", "41", "42", "43", "441", "45", "467", "468")

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
    lettrable = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
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


def default_lettrable(code: str) -> bool:
    return any(code.startswith(prefix) for prefix in LETTRABLE_PREFIXES)


@event.listens_for(Account, "before_insert")
def _lettrable_by_prefix(mapper, connection, account):
    """Un compte de tiers créé (401NNN, 411NNN, 4551…) est lettrable sans réglage."""
    if not account.lettrable and not account.is_header and default_lettrable(account.code or ""):
        account.lettrable = True
