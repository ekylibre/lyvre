from datetime import datetime

from app.extensions import db


class AccountMapping(db.Model):
    """Correspondance mémorisée d'un compte d'un autre logiciel (lot F6) : `source_code` = code du
    fichier, ou `aux:<compte>:<auxiliaire>` pour un compte de tiers auxiliaire du FEC."""
    __tablename__ = "account_mappings"

    id = db.Column(db.Integer, primary_key=True)
    source_code = db.Column(db.String(80), nullable=False, unique=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)

    account = db.relationship("Account")


class ImportProfile(db.Model):
    """Correspondance de colonnes mémorisée pour l'import d'écritures depuis un tableur (lot F6)."""
    __tablename__ = "import_profiles"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    kind = db.Column(db.String(8), nullable=False)          # csv, xlsx
    columns_json = db.Column(db.Text, nullable=False)       # champ → en-tête de colonne
    options_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
