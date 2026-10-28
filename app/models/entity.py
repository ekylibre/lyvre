from datetime import datetime

from sqlalchemy.orm import validates

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
    # Fournisseur : produit proposé sur les lignes de ses factures d'achat.
    default_product_id = db.Column(
        db.Integer, db.ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    # Identifiants du fournisseur côté Qonto / facture (rattachement des factures d'achat).
    qonto_supplier_id = db.Column(db.String(36), index=True)
    vat_number = db.Column(db.String(30), index=True)
    # Lot T2 : régime TVA (fr | eu | world) : autoliquidation des achats, ventes sans TVA française.
    vat_regime = db.Column(db.String(8), nullable=False, default="fr", server_default="fr")
    siret = db.Column(db.String(14), index=True)
    # SIREN : 9 premiers chiffres du SIRET (tenu à jour avec lui), ou seul (unité légale sans
    # établissement connu). Rapprochement des fournisseurs et mise à jour depuis Sirene (lot G).
    siren = db.Column(db.String(9), index=True)
    naf_code = db.Column(db.String(8))           # « 6820B », sans point, comme Sirene
    naf_nomenclature = db.Column(db.String(12))  # NAFRev2, NAF2025
    iban = db.Column(db.String(34))
    # Adresse et nature (lot B, reçus fiscaux) : exigées à l'émission d'un reçu, pas à la saisie.
    address_line1 = db.Column(db.String(200))
    address_line2 = db.Column(db.String(200))
    postal_code = db.Column(db.String(10))
    city = db.Column(db.String(100))
    country = db.Column(db.String(60))
    person_kind = db.Column(db.String(12))       # individual | company
    # Ventes : compte client 411NNN (créé à la première facture) ; emails en copie des envois.
    customer_account_code = db.Column(db.String(20))
    billing_emails = db.Column(db.Text)
    qonto_client_id = db.Column(db.String(36), index=True)  # client Qonto (ventes, lot S4)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @validates("siret")
    def _derive_siren(self, _key, value):
        """Tout chemin qui écrit un SIRET (fiche, achats, Qonto, reprise) en dérive le SIREN."""
        if value and len(value) == 14 and value.isdigit():
            self.siren = value[:9]
        return value

    transactions = db.relationship("BankTransaction", back_populates="entity", lazy="dynamic")
    purchases = db.relationship("Purchase", back_populates="entity", lazy="dynamic")
    default_product = db.relationship("Product")
    work_times = db.relationship(
        "WorkTime",
        back_populates="entity",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    def __repr__(self):
        return f"<Entity {self.name}>"
