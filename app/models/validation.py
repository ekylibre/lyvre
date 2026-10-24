from datetime import datetime

from app.extensions import db

BATCH_KINDS = ("manual", "until", "closing", "auto", "lock", "import", "migration")


class ValidationBatch(db.Model):
    """Lot de validation : écritures numérotées ensemble ; seul le dernier lot d'un exercice
    s'annule (la numérotation reste continue)."""
    __tablename__ = "validation_batches"

    id = db.Column(db.Integer, primary_key=True)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False,
                               index=True)
    kind = db.Column(db.String(12), nullable=False)
    until_date = db.Column(db.Date)
    entries = db.Column(db.Integer, nullable=False, default=0)
    user_id = db.Column(db.Integer)
    at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    undone_at = db.Column(db.DateTime)
    undone_by = db.Column(db.Integer)
    undo_reason = db.Column(db.Text)


class EntryEvent(db.Model):
    """Historique d'une écriture : état complet après chaque création, modification, suppression,
    validation, dévalidation ou contrepassation (pas de clé étrangère : survit à la suppression)."""
    __tablename__ = "entry_events"

    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(db.Integer, index=True)
    fiscal_year_id = db.Column(db.Integer, index=True)
    reference = db.Column(db.String(50))
    action = db.Column(db.String(12), nullable=False)
    snapshot_json = db.Column(db.Text)
    user_id = db.Column(db.Integer)
    origin = db.Column(db.String(60))
    at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
