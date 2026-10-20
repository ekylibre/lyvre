from datetime import datetime

from app.extensions import db


class IgnoredCounterparty(db.Model):
    """Contrepartie bancaire à ne plus proposer comme fournisseur (nom normalisé)."""

    __tablename__ = "ignored_counterparties"

    id = db.Column(db.Integer, primary_key=True)
    name_key = db.Column(db.String(200), unique=True, nullable=False)
    label = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<IgnoredCounterparty {self.label}>"
