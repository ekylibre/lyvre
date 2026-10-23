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


FORMS = {
    "manual": "Déclaration de don manuel",
    "private_deed": "Acte sous seing privé",
    "authentic": "Acte authentique",
    "other": "Autres",
}
NATURES = {"cash": "Numéraire", "securities": "Titres de sociétés cotés", "in_kind": "Autres (don en nature)"}
PAYMENT_METHODS = {
    "cash": "Remise d'espèces", "check": "Chèque", "transfer": "Virement, prélèvement, carte bancaire", "none": "",
}


class ReceiptCounter(db.Model):
    """Dernier numéro de reçu émis pour une année civile (numérotation continue, jamais réutilisée)."""
    __tablename__ = "receipt_counters"

    year = db.Column(db.Integer, primary_key=True, autoincrement=False)
    last_number = db.Column(db.Integer, nullable=False, default=0)


class DonationReceipt(db.Model):
    """Reçu fiscal émis : numéro `AAAA-NNNNN`, donateur figé à l'émission, PDF figé (SHA-256).
    Jamais supprimé ; une annulation le passe en `cancelled` avec un motif (lot B.3)."""
    __tablename__ = "donation_receipts"

    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(12), unique=True, nullable=False)
    year = db.Column(db.Integer, nullable=False, index=True)
    entity_id = db.Column(db.Integer, db.ForeignKey("entities.id"), nullable=False, index=True)
    person_kind = db.Column(db.String(12), nullable=False)        # individual | company
    mode = db.Column(db.String(10), nullable=False)               # annual | single
    total_cents = db.Column(db.Integer, nullable=False)
    donor_json = db.Column(db.Text, nullable=False)               # nom, adresse, SIREN au jour de l'émission
    status = db.Column(db.String(10), nullable=False, default="issued")   # issued | cancelled
    cancel_reason = db.Column(db.Text)
    replaced_by_id = db.Column(db.Integer, db.ForeignKey("donation_receipts.id"))
    pdf_path = db.Column(db.String(300))
    pdf_sha256 = db.Column(db.String(64))
    issued_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    issued_by_user_id = db.Column(db.Integer)
    sent_at = db.Column(db.DateTime)
    sent_to = db.Column(db.String(200))

    entity = db.relationship("Entity")
    items = db.relationship("DonationReceiptItem", backref="receipt", cascade="all, delete-orphan",
                            order_by="DonationReceiptItem.date")


class DonationReceiptItem(db.Model):
    """Don repris sur un reçu : ligne d'écriture de don ou don en nature."""
    __tablename__ = "donation_receipt_items"

    id = db.Column(db.Integer, primary_key=True)
    receipt_id = db.Column(db.Integer, db.ForeignKey("donation_receipts.id", ondelete="CASCADE"), nullable=False,
                           index=True)
    journal_line_id = db.Column(db.Integer, db.ForeignKey("journal_lines.id", ondelete="SET NULL"), index=True)
    in_kind_id = db.Column(db.Integer, db.ForeignKey("in_kind_donations.id", ondelete="SET NULL"), index=True)
    date = db.Column(db.Date, nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False)
    nature = db.Column(db.String(12), nullable=False, default="cash")
    form = db.Column(db.String(14), nullable=False, default="manual")
    payment_method = db.Column(db.String(10), nullable=False, default="transfer")


class InKindDonation(db.Model):
    """Don en nature (bien, prestation) valorisé, saisi à part pour figurer sur le reçu."""
    __tablename__ = "in_kind_donations"

    id = db.Column(db.Integer, primary_key=True)
    entity_id = db.Column(db.Integer, db.ForeignKey("entities.id"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False)
    description = db.Column(db.String(300), nullable=False)
    valuation_cents = db.Column(db.Integer, nullable=False)
    valuation_method = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    entity = db.relationship("Entity")
