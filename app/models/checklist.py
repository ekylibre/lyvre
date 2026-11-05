"""Listes de contrôle guidées (lot AG9b.e, AG9.6) : étapes cochées à la main, par liste et par période."""
from __future__ import annotations

from datetime import datetime

from app.extensions import db


class ChecklistMark(db.Model):
    __tablename__ = "checklist_marks"

    id = db.Column(db.Integer, primary_key=True)
    checklist_id = db.Column(db.String(20), nullable=False)
    period = db.Column(db.String(20), nullable=False)             # libellé de l'exercice ou année
    step_id = db.Column(db.String(30), nullable=False)
    done_on = db.Column(db.Date, nullable=False)
    user_id = db.Column(db.Integer)                               # utilisateur de la méta-base
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (db.UniqueConstraint("checklist_id", "period", "step_id", name="uq_checklist_marks_step"),)
