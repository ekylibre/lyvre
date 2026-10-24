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
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    # Donateur d'une ligne de don choisi explicitement (reçus fiscaux, lot B.2) ; à défaut, le tiers
    # de la transaction bancaire rapprochée ou du compte de tiers de l'écriture.
    entity_id = db.Column(db.Integer, db.ForeignKey("entities.id", ondelete="SET NULL"))
    # Lot F3 : lettrage de la ligne ; ligne d'à-nouveau → ligne d'origine non lettrée (lettrage
    # inter-exercices).
    lettering_id = db.Column(db.Integer, db.ForeignKey("letterings.id", ondelete="SET NULL"), index=True)
    carried_from_line_id = db.Column(db.Integer, db.ForeignKey("journal_lines.id", ondelete="SET NULL"), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    entry = db.relationship("JournalEntry", back_populates="lines")
    account = db.relationship("Account", back_populates="journal_lines")
    project = db.relationship("Project")
    bank_transaction = db.relationship("BankTransaction", back_populates="journal_line", uselist=False)
    lettering = db.relationship("Lettering", back_populates="lines")

    def __repr__(self):
        return f"<JournalLine account={self.account_id} D={self.debit_cents} C={self.credit_cents}>"
