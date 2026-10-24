from datetime import datetime

from app.extensions import db

LETTERING_ORIGINS = ("document", "auto", "manual", "import", "reversal")


class Lettering(db.Model):
    """Lettrage (lot F3) : lignes d'un même compte de tiers qui se soldent (complet, code en
    majuscules) ou pas encore (partiel, minuscules)."""
    __tablename__ = "letterings"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    code = db.Column(db.String(6), nullable=False)
    partial = db.Column(db.Boolean, nullable=False, default=False)
    balance_cents = db.Column(db.Integer, nullable=False, default=0)
    lettered_on = db.Column(db.Date)
    origin = db.Column(db.String(12), nullable=False, default="manual")
    document_type = db.Column(db.String(12))
    document_id = db.Column(db.Integer)
    gap_entry_id = db.Column(db.Integer, db.ForeignKey("journal_entries.id", ondelete="SET NULL"))
    user_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    account = db.relationship("Account")
    lines = db.relationship("JournalLine", back_populates="lettering")


class AccountRole(db.Model):
    """Compte choisi pour un rôle (écart de lettrage, dotations…) ; défauts par référentiel dans
    `data/account_roles.json`."""
    __tablename__ = "account_roles"

    role = db.Column(db.String(40), primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)

    account = db.relationship("Account")
