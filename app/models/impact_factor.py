from datetime import datetime
from app.extensions import db


class ImpactFactor(db.Model):
    """Facteur de conversion ventes → impact environnemental (source ADEME).

    Éditable par un admin, traçable (libellé + URL de source) pour la crédibilité
    auprès des financeurs. Valeur en ``Numeric(18, 6)`` pour les petits ratios.
    """
    __tablename__ = "impact_factors"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(60), unique=True, nullable=False)
    value = db.Column(db.Numeric(18, 6), nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    source_label = db.Column(db.String(200))
    source_url = db.Column(db.String(500))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # Pas de FK : la table `users` est sur le bind `meta`, pas dans la base tenant.
    updated_by_user_id = db.Column(db.Integer, nullable=True)

    def __repr__(self):
        return f"<ImpactFactor {self.key}={self.value}>"
