from datetime import datetime

from app.extensions import db

CLOSING_STEPS = ("checks", "inventory", "dedicated_funds", "result", "fec", "close", "opening", "allocation")
STEP_STATES = ("todo", "done", "skipped")


class ClosingStep(db.Model):
    """Décision de l'utilisateur sur une étape de l'assistant de clôture d'un exercice."""
    __tablename__ = "closing_steps"
    __table_args__ = (db.UniqueConstraint("fiscal_year_id", "step", name="uq_closing_step"),)

    id = db.Column(db.Integer, primary_key=True)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False,
                               index=True)
    step = db.Column(db.String(20), nullable=False)
    state = db.Column(db.String(10), nullable=False, default="todo")
    note = db.Column(db.Text)                      # motif obligatoire si « skipped »
    user_id = db.Column(db.Integer)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ClosingEvent(db.Model):
    """Journal d'audit de la clôture (actions, auteur, détail)."""
    __tablename__ = "closing_events"

    id = db.Column(db.Integer, primary_key=True)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False,
                               index=True)
    step = db.Column(db.String(20))
    action = db.Column(db.String(40), nullable=False)
    user_id = db.Column(db.Integer)
    at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    details_json = db.Column(db.Text)
