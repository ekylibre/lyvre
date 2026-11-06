"""Connecteur Ekylibre (lot AG11.a) : instantané local des données lues (cultures, interventions, matières), daté.
Les traitements (activités, clés, comptage) lisent l'instantané, jamais l'API (design_connecteur_ekylibre.md § 2)."""
from datetime import datetime

from app.extensions import db


class EkylibreSnapshot(db.Model):
    __tablename__ = "ekylibre_snapshots"

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(20), nullable=False, unique=True)   # productions | interventions | matters
    synced_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    count = db.Column(db.Integer, nullable=False, default=0)
    payload = db.Column(db.JSON, nullable=False)                   # objets neutres (ekylibre_client), sérialisés
