from datetime import datetime

from app.extensions import db


class MicroReceiptsYear(db.Model):
    """Recettes retenues au micro-BA d'une année civile antérieure à Lyvre (lot AG1.d) : la moyenne triennale du
    micro-BA (CGI art. 64 bis) a besoin de N-1 et N-2. Une année tenue dans Lyvre se calcule sur ses écritures ; la
    saisie l'emporte si elle existe."""
    __tablename__ = "micro_receipts_years"

    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False, unique=True)
    receipts_cents = db.Column(db.Integer, nullable=False)
    note = db.Column(db.String(300))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
