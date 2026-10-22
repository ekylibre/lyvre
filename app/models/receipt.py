from datetime import datetime

from app.extensions import db

ELIGIBILITY = {
    "general_interest": "Organisme d'intérêt général (art. 200-1-b et 238 bis-1-a du CGI)",
    "public_utility": "Association ou fondation reconnue d'utilité publique",
    "other": "Autre cas prévu par le CGI",
}
CGI_ARTICLES = {
    "200": "Article 200 du CGI (dons des particuliers, impôt sur le revenu)",
    "238bis": "Article 238 bis du CGI (dons des entreprises)",
    "978": "Article 978 du CGI (impôt sur la fortune immobilière)",
}
DEFAULT_DONATION_PREFIXES = ["7541"]


class ReceiptSettings(db.Model):
    """Paramètres des reçus fiscaux de l'instance (une ligne). L'outil n'évalue pas l'éligibilité :
    l'administrateur la déclare et reconnaît sa responsabilité à l'activation."""
    __tablename__ = "receipt_settings"

    id = db.Column(db.Integer, primary_key=True)
    enabled = db.Column(db.Boolean, nullable=False, default=False)
    eligibility = db.Column(db.String(20))
    eligibility_detail = db.Column(db.Text)
    rescrit_ref = db.Column(db.String(100))
    cgi_articles_json = db.Column(db.Text)            # ["200", "238bis"]
    donation_prefixes_json = db.Column(db.Text)       # ["7541"]
    default_mode = db.Column(db.String(10), nullable=False, default="annual")  # annual | single
    acknowledged_at = db.Column(db.DateTime)
    acknowledged_by_user_id = db.Column(db.Integer)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
