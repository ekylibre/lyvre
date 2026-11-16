"""Résultat fiscal BA d'un exercice (lot AG6.a, claudedocs/design_fiscalite_ba.md § 3).

Le tableau de passage se calcule tant que l'exercice est ouvert ; il est figé (`snapshot_json`) au premier calcul
après la clôture. Les lignes saisies (CSG non déductible, autres réintégrations et déductions) sont gardées ici ; les
lignes proposées par Lyvre (stocks, abattage sanitaire, puis JA et DEP) se calculent.
"""
from datetime import datetime

from app.extensions import db

TAX_LINE_KINDS = {"csg": "Part de la CSG non déductible", "add": "Autre réintégration", "deduct": "Autre déduction"}


class TaxResult(db.Model):
    __tablename__ = "tax_results"

    id = db.Column(db.Integer, primary_key=True)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False, unique=True)
    snapshot_json = db.Column(db.Text)
    frozen_at = db.Column(db.DateTime)


class TaxResultLine(db.Model):
    """Ligne de passage saisie : montant positif, sens donné par le type (réintégration ou déduction)."""
    __tablename__ = "tax_result_lines"

    id = db.Column(db.Integer, primary_key=True)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = db.Column(db.String(10), nullable=False)
    label = db.Column(db.String(200), nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


DEP_KINDS = {"dep": "DEP", "dpi": "DPI (ancienne)", "dpa": "DPA (ancienne)"}
DEP_MOVEMENTS = {"use": "Utilisation", "reintegration": "Réintégration"}
DEP_HAZARDS = {"health": "Maladie animale ou végétale, incident environnemental", "climate": "Aléa climatique",
               "calamity": "Calamité agricole", "economic": "Aléa économique"}


class DepEntry(db.Model):
    """Déduction pour épargne de précaution d'un exercice (lot AG6.c), ou ancienne DPI / DPA reprise avec son exercice
    d'origine (`origin_year` quand l'exercice n'est pas dans Lyvre)."""
    __tablename__ = "dep_entries"

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(4), nullable=False, default="dep")
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey("fiscal_years.id", ondelete="CASCADE"), unique=True)
    origin_year = db.Column(db.Integer)
    amount_cents = db.Column(db.Integer, nullable=False)
    note = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    fiscal_year = db.relationship("FiscalYear")
    movements = db.relationship("DepMovement", back_populates="entry", cascade="all, delete-orphan",
                                order_by="DepMovement.on, DepMovement.id")


class DepMovement(db.Model):
    """Utilisation (réintégrée dans l'exercice, part exonérée en cas d'aléa) ou réintégration d'une DEP."""
    __tablename__ = "dep_movements"

    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(db.Integer, db.ForeignKey("dep_entries.id", ondelete="CASCADE"), nullable=False, index=True)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = db.Column(db.String(14), nullable=False)
    on = db.Column(db.Date, nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False)
    hazard = db.Column(db.String(10))
    exempt_cents = db.Column(db.Integer, nullable=False, default=0)
    reason = db.Column(db.String(300))

    entry = db.relationship("DepEntry", back_populates="movements")


class DepSubstitute(db.Model):
    """Substitut d'épargne de l'exercice (stocks de fourrage consommés, stocks à rotation lente), saisi."""
    __tablename__ = "dep_substitutes"

    id = db.Column(db.Integer, primary_key=True)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False, index=True)
    label = db.Column(db.String(200), nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False)


COW_CATEGORIES = {"dairy": "Vaches laitières", "suckler": "Vaches allaitantes"}
COW_RELEASE_KINDS = {"exit": "Sorties de vaches", "sixth_year": "6e exercice : réintégration",
                     "exempt": "6e exercice : exonération définitive", "waived": "Sortie sans reprise (dérogation)"}


class CowProvision(db.Model):
    """Provision pour hausse de la valeur des stocks de vaches (art. 73 A, lot AG6.d) d'un exercice de constitution :
    montant, effectif et valeur du stock de vaches à la clôture (bases des reprises et de l'exonération)."""
    __tablename__ = "cow_provisions"

    id = db.Column(db.Integer, primary_key=True)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False, unique=True)
    amount_cents = db.Column(db.Integer, nullable=False)
    heads = db.Column(db.Integer, nullable=False)
    value_cents = db.Column(db.Integer, nullable=False)
    detail_json = db.Column(db.Text)

    fiscal_year = db.relationship("FiscalYear")
    releases = db.relationship("CowProvisionRelease", back_populates="provision", cascade="all, delete-orphan",
                               order_by="CowProvisionRelease.id")


class CowProvisionRelease(db.Model):
    """Reprise (ou dérogation motivée) d'une provision 73 A à la clôture d'un exercice suivant."""
    __tablename__ = "cow_provision_releases"

    id = db.Column(db.Integer, primary_key=True)
    provision_id = db.Column(db.Integer, db.ForeignKey("cow_provisions.id", ondelete="CASCADE"), nullable=False, index=True)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = db.Column(db.String(12), nullable=False)
    heads = db.Column(db.Integer)
    amount_cents = db.Column(db.Integer, nullable=False, default=0)
    reason = db.Column(db.String(300))

    provision = db.relationship("CowProvision", back_populates="releases")


# ------------------------------------------------------------------ régimes BA (lot AG6.e)

ACCOUNT_INCOME_CLASSES = {"accessory": "Recette accessoire BIC / BNC (art. 75)",
                          "custom_work": "Recette à façon (× 3 pour les seuils, art. 69)"}
SPREAD_KINDS = {"profit": "Bénéfice exceptionnel (art. 75-0 A, 1-a)", "slaughter": "Indemnité d'abattage (art. 75-0 A, 1-b)"}


class BaHistoryYear(db.Model):
    """Données d'une année civile antérieure à Lyvre : recettes agricoles et accessoires (moyennes, art. 69 et 75),
    bénéfice agricole de l'exercice clos dans l'année (75-0 A, historique 75-0 B). Une valeur saisie l'emporte."""
    __tablename__ = "ba_history_years"

    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False, unique=True)
    agricultural_receipts_cents = db.Column(db.BigInteger)
    accessory_receipts_cents = db.Column(db.BigInteger)
    fiscal_result_cents = db.Column(db.BigInteger)
    note = db.Column(db.String(300))


class IncomeSpread(db.Model):
    """Étalement d'un revenu exceptionnel par septièmes (art. 75-0 A) : exercice de réalisation et montant étalé."""
    __tablename__ = "income_spreads"

    id = db.Column(db.Integer, primary_key=True)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = db.Column(db.String(10), nullable=False)
    amount_cents = db.Column(db.BigInteger, nullable=False)
    reason = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    fiscal_year = db.relationship("FiscalYear")


# ------------------------------------------------------------------ plus-values et crédits d'impôt (lot AG6.g)

TAX_CREDIT_KINDS = {"organic": "Crédit d'impôt agriculture biologique", "hve": "Crédit d'impôt certification HVE",
                    "replacement": "Crédit d'impôt remplacement pour congés"}


class CapitalGainChoice(db.Model):
    """Choix de l'exercice pour les plus-values : exonération 151 septies retenue, début d'activité (condition des 5 ans),
    cession à un jeune agriculteur (seuils relevés)."""
    __tablename__ = "capital_gain_choices"

    id = db.Column(db.Integer, primary_key=True)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False, unique=True)
    apply_151_septies = db.Column(db.Boolean, nullable=False, default=False)
    activity_since = db.Column(db.Date)
    young_farmer_buyer = db.Column(db.Boolean, nullable=False, default=False)


class TaxCredit(db.Model):
    """Crédit d'impôt de l'exercice : données saisies (recettes bio, certification, dépenses et jours de remplacement)."""
    __tablename__ = "tax_credits"

    id = db.Column(db.Integer, primary_key=True)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = db.Column(db.String(12), nullable=False)
    data_json = db.Column(db.Text)
    note = db.Column(db.String(300))

    __table_args__ = (db.UniqueConstraint("fiscal_year_id", "kind", name="uq_tax_credits_fiscal_year_kind"),)
