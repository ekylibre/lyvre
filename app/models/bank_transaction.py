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
    raw_type = db.Column(db.String(40))  # type OFX, ou operation_type Qonto
    reconciled = db.Column(db.Boolean, default=False, nullable=False)
    journal_line_id = db.Column(db.Integer, db.ForeignKey("journal_lines.id"), nullable=True)
    entity_id = db.Column(db.Integer, db.ForeignKey("entities.id"), nullable=True)
    category = db.Column(db.String(100))
    imported_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Origine (ofx | qonto) ; pour Qonto, fitid = identifiant (UUID) de la transaction.
    source = db.Column(db.String(10), nullable=False, default="ofx", server_default="ofx")
    counterparty = db.Column(db.String(200))
    note = db.Column(db.Text)
    # Annulée par la banque après règlement : plus rapprochable.
    is_reversed = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    # Justificatifs (NULL quand la source ne les connaît pas, ex. OFX).
    attachment_count = db.Column(db.Integer)
    attachment_required = db.Column(db.Boolean)
    attachment_lost = db.Column(db.Boolean)
    source_updated_at = db.Column(db.DateTime)

    __table_args__ = (
        db.UniqueConstraint("bank_account_id", "fitid", name="uq_bank_transaction_fitid"),
        db.Index("ix_bank_transactions_account_reversed", "bank_account_id", "is_reversed"),
    )

    bank_account = db.relationship("BankAccount", back_populates="transactions")
    journal_line = db.relationship("JournalLine", back_populates="bank_transaction")
    entity = db.relationship("Entity", back_populates="transactions")

    def __repr__(self):
        return f"<BankTransaction {self.fitid} {self.amount_cents}>"
