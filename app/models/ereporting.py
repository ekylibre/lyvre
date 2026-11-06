"""E-reporting B2C (lot AG10.e, claudedocs/design_efacturation_agricole.md § 6) : export des transactions d'une
période (agrégats jour × catégorie × taux), gardé pour signaler les jours non exportés."""
from datetime import datetime

from app.extensions import db


class EreportingExport(db.Model):
    __tablename__ = "ereporting_exports"

    id = db.Column(db.Integer, primary_key=True)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    transactions = db.Column(db.Integer, nullable=False, default=0)
    base_cents = db.Column(db.Integer, nullable=False, default=0)
    tax_cents = db.Column(db.Integer, nullable=False, default=0)
    exported_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    user_id = db.Column(db.Integer)  # utilisateur (base méta), sans clé étrangère
