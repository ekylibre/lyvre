from datetime import datetime
from app.extensions import db


class JournalLine(db.Model):
    __tablename__ = "journal_lines"

    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(db.Integer, db.ForeignKey("journal_entries.id", ondelete="CASCADE"), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    label = db.Column(db.String(300))
    debit_cents = db.Column(db.Integer, default=0, nullable=False)
    credit_cents = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    entry = db.relationship("JournalEntry", back_populates="lines")
    account = db.relationship("Account", back_populates="journal_lines")
    bank_transaction = db.relationship("BankTransaction", back_populates="journal_line", uselist=False)

    def __repr__(self):
        return f"<JournalLine account={self.account_id} D={self.debit_cents} C={self.credit_cents}>"
