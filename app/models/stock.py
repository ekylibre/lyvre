"""Inventaire de clôture des exploitations agricoles (lot AG4, claudedocs/design_inventaire_agricole.md § 9.1).

Inventaire intermittent : une liste de lignes de stock par exercice, valorisées à la clôture ; l'écriture de stock
(AG4.d) en est tirée. Les lots d'animaux (AG4.b), les avances aux cultures (AG4.c) et la valeur fiscale (AG4.e)
complètent ces tables dans leurs sous-lots.
"""
from datetime import datetime

from app.extensions import db

STOCK_METHODS = {"actual": "Coût réel", "standard": "Coût standard (barème)", "retail": "Prix de détail moins décote",
                 "flat": "Méthode forfaitaire (réel simplifié)", "crop_advance": "Fiche d'avance aux cultures"}
FLAT_RATES = {"general": "Décote générale", "cattle_wine": "Bovins, viticulture"}
FISCAL_METHODS = {"none": "Valeur comptable", "flat": "Méthode forfaitaire (art. 74 b)",
                  "frozen": "Stock bloqué (art. 72 B bis)", "manual": "Valeur fiscale saisie"}
STOCK_UNITS = {"t": "tonne", "q": "quintal", "kg": "kg", "hl": "hl", "l": "litre", "head": "tête", "ha": "ha",
               "unit": "unité", "m3": "m³"}


class StockSettings(db.Model):
    """Réglages de l'inventaire d'un exercice : décotes du prix de détail par catégorie, date du comptage."""
    __tablename__ = "stock_settings"

    id = db.Column(db.Integer, primary_key=True)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False,
                               unique=True)
    discounts_json = db.Column(db.Text, nullable=False, default="{}")       # {catégorie: décote en points de base}
    counted_on = db.Column(db.Date)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class StockStandard(db.Model):
    """Barème de coût standard de l'exploitation (PCG 618-13, 1°) : valeur par unité, datée et sourcée."""
    __tablename__ = "stock_standards"
    __table_args__ = (db.UniqueConstraint("key", "year", name="uq_stock_standards_key_year"),)

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(60), nullable=False)
    label = db.Column(db.String(200), nullable=False)
    unit = db.Column(db.String(10), nullable=False)
    value_cents = db.Column(db.Integer, nullable=False)                   # par unité
    year = db.Column(db.Integer, nullable=False)
    source = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class StockLine(db.Model):
    """Ligne de l'inventaire d'un exercice : compte de stock et de variation, quantité, méthode, valeur."""
    __tablename__ = "stock_lines"

    id = db.Column(db.Integer, primary_key=True)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False,
                               index=True)
    category = db.Column(db.String(20), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False)
    variation_account_id = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False)
    label = db.Column(db.String(200), nullable=False)
    production = db.Column(db.String(120))
    quantity = db.Column(db.Numeric(14, 3), nullable=False, default=0)
    unit = db.Column(db.String(10), nullable=False, default="unit")
    method = db.Column(db.String(10), nullable=False, default="actual")
    standard_id = db.Column(db.Integer, db.ForeignKey("stock_standards.id", ondelete="SET NULL"))
    market_price_cents = db.Column(db.Integer)                             # cours du jour par unité
    price_source = db.Column(db.String(200))
    price_reference = db.Column(db.String(40))                            # data/agri_price_references.yml
    flat_rate = db.Column(db.String(12))                                  # general | cattle_wine
    unit_value_cents = db.Column(db.Integer)                              # saisie (coût réel) ou calculée
    value_cents = db.Column(db.Integer)                                   # valeur comptable de la ligne
    depreciation_cents = db.Column(db.Integer)
    depreciation_reason = db.Column(db.String(300))
    lot_id = db.Column(db.Integer, db.ForeignKey("stock_lots.id", ondelete="SET NULL"), index=True)   # AG4.b
    crop_advance_id = db.Column(db.Integer, db.ForeignKey("crop_advances.id", ondelete="SET NULL"), index=True)  # AG4.c
    heads = db.Column(db.Integer)                                         # effectif compté du lot
    gap_reason = db.Column(db.String(300))                                # motif d'un écart avec l'effectif théorique
    fiscal_method = db.Column(db.String(8), nullable=False, default="none", server_default="none")   # AG4.e
    fiscal_value_cents = db.Column(db.Integer)                            # valeur fiscale saisie (méthode « manual »)
    fiscal_reason = db.Column(db.String(300))
    notes = db.Column(db.Text)
    position = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    account = db.relationship("Account", foreign_keys=[account_id])
    variation_account = db.relationship("Account", foreign_keys=[variation_account_id])
    standard = db.relationship("StockStandard")
    lot = db.relationship("StockLot")
    crop_advance = db.relationship("CropAdvance", foreign_keys=[crop_advance_id])


class StockCountFile(db.Model):
    """Feuille de comptage jointe à l'inventaire d'un exercice (colonnes `attachment_*`, service `attachments`)."""
    __tablename__ = "stock_count_files"

    id = db.Column(db.Integer, primary_key=True)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False,
                               index=True)
    attachment_path = db.Column(db.String(300))
    attachment_name = db.Column(db.String(200))
    attachment_mime = db.Column(db.String(60))
    attachment_size = db.Column(db.Integer)
    note = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


LOT_MOVEMENTS = {"opening": "Effectif d'ouverture", "birth": "Naissance", "purchase": "Achat", "transfer_in": "Entrée d'un autre lot",
                 "sale": "Vente", "death": "Mort", "transfer_out": "Passage dans un autre lot",
                 "to_fixed_assets": "Sortie vers les immobilisations"}
LOT_IN = ("birth", "purchase", "transfer_in")
LOT_OUT = ("sale", "death", "transfer_out", "to_fixed_assets")
LOT_DESTINATIONS = {"sale": "Vente", "fattening": "Engraissement", "breeding": "Renouvellement", "other": "Autre"}


class StockLot(db.Model):
    """Lot d'animaux en stock (lot AG4.b, design § 5.5) : même espèce, même catégorie d'âge, même destination
    (PCG 618-10, 3°). Suivi en nombre de têtes, sans écriture : l'inventaire reste intermittent."""
    __tablename__ = "stock_lots"

    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(200), nullable=False)
    species = db.Column(db.String(80), nullable=False)
    age_class = db.Column(db.String(80))
    destination = db.Column(db.String(12), nullable=False, default="sale")
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False)
    average_weight_kg = db.Column(db.Numeric(10, 2))
    active = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    account = db.relationship("Account")
    movements = db.relationship("StockLotMovement", back_populates="lot", cascade="all, delete-orphan",
                                foreign_keys="StockLotMovement.lot_id", order_by="StockLotMovement.on, StockLotMovement.id")


class StockLotMovement(db.Model):
    """Mouvement daté d'un lot, en têtes (positif). Un passage d'un lot à un autre est une paire transfer_out /
    transfer_in reliée par `pair_id`."""
    __tablename__ = "stock_lot_movements"

    id = db.Column(db.Integer, primary_key=True)
    lot_id = db.Column(db.Integer, db.ForeignKey("stock_lots.id", ondelete="CASCADE"), nullable=False, index=True)
    on = db.Column(db.Date, nullable=False)
    kind = db.Column(db.String(16), nullable=False)
    heads = db.Column(db.Integer, nullable=False)
    purchase_line_id = db.Column(db.Integer, db.ForeignKey("purchase_lines.id", ondelete="SET NULL"))
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id", ondelete="SET NULL"))
    counterpart_lot_id = db.Column(db.Integer, db.ForeignKey("stock_lots.id", ondelete="SET NULL"))
    pair_id = db.Column(db.Integer)
    asset_id = db.Column(db.Integer, db.ForeignKey("assets.id", ondelete="SET NULL"))   # AG5.b : fiche immobilisée créée
    note = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    lot = db.relationship("StockLot", back_populates="movements", foreign_keys=[lot_id])
    counterpart_lot = db.relationship("StockLot", foreign_keys=[counterpart_lot_id])
    asset = db.relationship("Asset")


CROP_COMPONENTS = {"supplies": "Approvisionnements", "machinery": "Mécanisation", "labour": "Main-d'œuvre"}
CROP_METHODS = {"standard_f": "Coût standard F (approvisionnements, mécanisation, main-d'œuvre)",
                "standard_m1": "Coût standard M1 (mécanisation, main-d'œuvre) + approvisionnements au réel",
                "standard_m2": "Coût standard M2 (mécanisation) + approvisionnements au réel",
                "actual": "Coût réel (art. 72 A)"}
CROP_RUBRICS = {"seeds": "Semences et plants", "fertilizers": "Engrais et amendements", "treatments": "Produits de traitement",
                "labour": "Main-d'œuvre des façons culturales, de l'amendement et des semis",
                "machinery": "Frais de matériel (carburants, entretien, réparations, amortissements, travaux par des tiers)"}
CROP_SUPPLY_RUBRICS = ("seeds", "fertilizers", "treatments")


class CropStandard(db.Model):
    """Barème de coût standard d'une production (lot AG4.c, méthode du guide CEGARA) : coût par ha et par mois
    d'opérations, en trois composantes. Aucune valeur livrée par Lyvre : saisi ou importé par l'exploitation."""
    __tablename__ = "crop_standards"
    __table_args__ = (db.UniqueConstraint("production", "year", name="uq_crop_standards_production_year"),)

    id = db.Column(db.Integer, primary_key=True)
    production = db.Column(db.String(120), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    source = db.Column(db.String(300))
    labour_assumption = db.Column(db.String(200))      # « 100 % main-d'œuvre salariée » dans le guide
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    rows = db.relationship("CropStandardRow", back_populates="standard", cascade="all, delete-orphan",
                           order_by="CropStandardRow.month, CropStandardRow.component")


class CropStandardRow(db.Model):
    """Montant par ha d'une composante pour un mois calendaire (1 à 12)."""
    __tablename__ = "crop_standard_rows"
    __table_args__ = (db.UniqueConstraint("standard_id", "component", "month", name="uq_crop_standard_rows"),)

    id = db.Column(db.Integer, primary_key=True)
    standard_id = db.Column(db.Integer, db.ForeignKey("crop_standards.id", ondelete="CASCADE"), nullable=False, index=True)
    component = db.Column(db.String(10), nullable=False)
    month = db.Column(db.Integer, nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False)

    standard = db.relationship("CropStandard", back_populates="rows")


class CropAdvance(db.Model):
    """Culture en terre à la clôture d'un exercice (PCG 618-14) : alimente sa ligne d'inventaire 31141 / 31151."""
    __tablename__ = "crop_advances"

    id = db.Column(db.Integer, primary_key=True)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False, index=True)
    production = db.Column(db.String(120), nullable=False)
    surface_ha = db.Column(db.Numeric(10, 4), nullable=False)
    planted_on = db.Column(db.Date, nullable=False)
    campaign = db.Column(db.Integer)
    cycle = db.Column(db.String(5), nullable=False, default="short")       # short (31151) | long (31141)
    plots = db.Column(db.String(300))
    method = db.Column(db.String(12), nullable=False, default="actual")
    crop_standard_id = db.Column(db.Integer, db.ForeignKey("crop_standards.id", ondelete="SET NULL"))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    standard = db.relationship("CropStandard")
    costs = db.relationship("CropAdvanceCost", back_populates="advance", cascade="all, delete-orphan",
                            order_by="CropAdvanceCost.rubric, CropAdvanceCost.id")


class CropAdvanceCost(db.Model):
    """Charge de la liste fermée de l'art. 72 A rattachée à une avance : ligne d'écriture de l'exercice (quote-part)
    ou saisie."""
    __tablename__ = "crop_advance_costs"

    id = db.Column(db.Integer, primary_key=True)
    crop_advance_id = db.Column(db.Integer, db.ForeignKey("crop_advances.id", ondelete="CASCADE"), nullable=False, index=True)
    rubric = db.Column(db.String(12), nullable=False)
    journal_line_id = db.Column(db.Integer, db.ForeignKey("journal_lines.id", ondelete="SET NULL"))
    label = db.Column(db.String(300), nullable=False)
    base_cents = db.Column(db.Integer, nullable=False)
    share_bp = db.Column(db.Integer, nullable=False, default=10000)
    amount_cents = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    advance = db.relationship("CropAdvance", back_populates="costs")
