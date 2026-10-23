from datetime import datetime

from app.extensions import db


class Organization(db.Model):
    """Identité de la structure (une ligne par base d'instance) : FEC, reçus, états."""
    __tablename__ = "organization"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    siren = db.Column(db.String(9))
    rna = db.Column(db.String(10))                 # W + 9 chiffres (associations)
    address_line1 = db.Column(db.String(200))
    address_line2 = db.Column(db.String(200))
    postal_code = db.Column(db.String(10))
    city = db.Column(db.String(100))
    country = db.Column(db.String(60), nullable=False, default="France", server_default="France")
    purpose = db.Column(db.Text)                   # objet de la structure
    signatory_name = db.Column(db.String(200))
    signatory_title = db.Column(db.String(100))
    signature_path = db.Column(db.String(300))     # lot B (reçus)
    # Module « Associés » : taux d'intérêt des comptes courants par défaut (l'option est sur l'instance).
    associate_interest_rate_bp = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
