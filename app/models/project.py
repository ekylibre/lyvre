from datetime import datetime

from app.extensions import db


class Project(db.Model):
    """Projet ou activité : axe analytique unique (OA11), porté par les lignes d'écriture, les
    lignes de facture d'achat et les règles de catégorisation."""
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    description = db.Column(db.Text)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    manager = db.Column(db.String(120))           # responsable (texte libre)
    archived = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Project {self.name}>"
