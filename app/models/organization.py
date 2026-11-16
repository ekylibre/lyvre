from datetime import datetime

from app.extensions import db


class Organization(db.Model):
    """Identité et mentions légales de la structure (une ligne par base d'instance) : FEC, reçus,
    factures, baux, états."""
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
    legal_form = db.Column(db.String(100))         # « Société civile immobilière » (baux)
    rcs_city = db.Column(db.String(100))           # greffe du RCS (« Saintes »)
    # Mentions légales (lot G2 : seule source, reprises de Facturation) et activité (Sirene).
    share_capital_cents = db.Column(db.Integer)
    vat_number = db.Column(db.String(20))          # TVA intracommunautaire
    naf_code = db.Column(db.String(8))             # « 6820B », sans point, comme Sirene
    naf_nomenclature = db.Column(db.String(12))    # NAFRev2, NAF2025
    signature_path = db.Column(db.String(300))     # lot B (reçus)
    # Module « Associés » : taux d'intérêt des comptes courants par défaut (l'option est sur l'instance).
    associate_interest_rate_bp = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    # Lot F3 : écart de lettrage soldé en charge / produit divers jusqu'à ce montant.
    lettering_gap_cents = db.Column(db.Integer, nullable=False, default=100, server_default="100")
    # Lot F5 : amortissements comptabilisés (None : oui pour une association, non pour une SCI à l'IR).
    depreciation_enabled = db.Column(db.Boolean)
    # Lot T1 : jeune entreprise innovante depuis cette date (sociétés ; liasse et crédits d'impôt).
    jei_since = db.Column(db.Date)
    # Lot AG1.a : forme juridique codée (EI, EARL, GAEC, SCEA…, app/services/tax_profile.LEGAL_FORMS), qui
    # choisit le modèle de bilan et porte les contrôles de régime ; date de création (micro-BA, art. 69 D).
    legal_form_code = db.Column(db.String(10))
    created_on = db.Column(db.Date)
    # Lot AG9a : profil des démarches d'une exploitation (JSON, schéma dans app/services/agri_profile.py).
    agri_profile = db.Column(db.Text)
    # Lot T3 : jour d'échéance de la CA3 (fixé par le SIE, du 15 au 24 du mois suivant) ; nul : 24.
    vat_due_day = db.Column(db.Integer)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
