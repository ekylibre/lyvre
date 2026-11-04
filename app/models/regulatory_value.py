import json
from datetime import datetime

from app.extensions import db


class RegulatoryValue(db.Model):
    """Surcharge d'un paramètre réglementaire daté (méta-base, commune à toutes les instances ; lot AG1.a,
    claudedocs/design_compta_agricole.md § 4.2). Les valeurs de référence sont dans data/regulatory/*.json ;
    une surcharge couvrant la date l'emporte (app/services/reg_params)."""
    __tablename__ = "regulatory_values"
    __bind_key__ = "meta"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(120), nullable=False, index=True)
    value_json = db.Column(db.Text, nullable=False)
    valid_from = db.Column(db.Date, nullable=False)
    valid_to = db.Column(db.Date)
    source = db.Column(db.String(500))
    source_label = db.Column(db.String(200))
    verified_on = db.Column(db.Date)
    reliability = db.Column(db.String(1), nullable=False, default="A", server_default="A")  # V | R | A | I
    note = db.Column(db.String(500))
    created_by_user_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def value(self):
        return json.loads(self.value_json)

    @value.setter
    def value(self, value):
        self.value_json = json.dumps(value, ensure_ascii=False)
