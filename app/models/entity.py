from datetime import datetime
from app.extensions import db

ENTITY_TYPES = [
    ("CLIENT", "Client"),
    ("FOURNISSEUR", "Fournisseur"),
    ("SALARIE", "Salarié"),
    ("ADHERENT", "Adhérent"),
    ("ORGANISME", "Organisme public / social"),
    ("AUTRE", "Autre"),
]


class Entity(db.Model):
    __tablename__ = "entities"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)
    entity_type = db.Column(db.String(20), nullable=False, default="AUTRE")
    account_code = db.Column(db.String(20))
    email = db.Column(db.String(200), index=True)
    is_member = db.Column(db.Boolean, nullable=False, default=False)
    is_benevole = db.Column(
        db.Boolean, nullable=False, default=False, server_default="false"
    )
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    transactions = db.relationship("BankTransaction", back_populates="entity", lazy="dynamic")
    work_times = db.relationship(
        "WorkTime",
        back_populates="entity",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    def __repr__(self):
        return f"<Entity {self.name}>"
