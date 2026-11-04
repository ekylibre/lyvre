from datetime import datetime

from app.extensions import db


class TaxProfile(db.Model):
    """Régime fiscal daté de la structure (lot AG1.a, claudedocs/design_compta_agricole.md § 3.2) : impôt
    (IR / IS), régime des bénéfices agricoles (micro, réel simplifié, réel normal), régime de TVA (AG2).
    Une période par ligne ; pas de chevauchement pour un même `kind` (contrôlé par app/services/tax_profile)."""
    __tablename__ = "tax_profiles"

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(20), nullable=False, index=True)    # income_tax | ba_regime | vat_regime
    value = db.Column(db.String(30), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)                                    # nul : en cours
    origin = db.Column(db.String(10), nullable=False, default="law", server_default="law")  # law | option
    note = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class TaxOption(db.Model):
    """Option fiscale datée (§ 3.3) : durée, reconduction tacite, renonciation. La date limite de
    renonciation se calcule (paramètres réglementaires `option.<code>.*`), elle n'est pas stockée."""
    __tablename__ = "tax_options"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), nullable=False, index=True)
    start_date = db.Column(db.Date, nullable=False)
    duration_years = db.Column(db.Integer)                           # nul : sans terme
    tacit_renewal = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    renounced_on = db.Column(db.Date)
    note = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
