from datetime import datetime
from app.extensions import db

ENTITY_TYPES = [
    ("CLIENT", "Client"),
    ("FOURNISSEUR", "Fournisseur"),
    ("SALARIE", "Salarié"),
    ("ORGANISME", "Organisme public / social"),
    ("AUTRE", "Autre"),
]


class Entity(db.Model):
    __tablename__ = "entities"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)
    entity_type = db.Column(db.String(20), nullable=False, default="AUTRE")
    account_code = db.Column(db.String(20))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    transactions = db.relationship("BankTransaction", back_populates="entity", lazy="dynamic")

    def __repr__(self):
        return f"<Entity {self.name}>"
