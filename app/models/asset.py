from datetime import datetime

from app.extensions import db

ASSET_METHODS = ("linear", "regressive", "none")
ASSET_STATUSES = ("waiting", "in_use", "depreciated", "sold", "scrapped")
LIVING_KINDS = {"breeding": "Animaux reproducteurs", "service": "Animaux de service", "plantation": "Plantations pérennes",
                "other": "Autres végétaux immobilisés"}
LIVING_ORIGINS = {"purchase": "Achat", "born": "Né sur l'exploitation", "from_stock": "Venu du stock", "planted": "Planté"}


class Asset(db.Model):
    """Immobilisation (lot F5) ; un bien peut avoir des composants (`parent_id`), chacun son plan."""
    __tablename__ = "assets"

    id = db.Column(db.Integer, primary_key=True)
    activity_id = db.Column(db.Integer, db.ForeignKey("activities.id", ondelete="SET NULL"))      # lot AG8.c
    parent_id = db.Column(db.Integer, db.ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    label = db.Column(db.String(200), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False)
    depreciation_account_id = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="SET NULL"))
    expense_account_id = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="SET NULL"))
    waiting_account_id = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="SET NULL"))
    acquired_on = db.Column(db.Date, nullable=False)
    in_service_date = db.Column(db.Date)
    # Lot CG5.d : amortissement en annuité entière à partir du 1er jour de l'exercice de mise en service (plantations :
    # exercice de la première récolte, BOI-BA-BASE-20-30-10-20 § 150).
    full_first_year = db.Column(db.Boolean)
    acquisition_cents = db.Column(db.Integer, nullable=False, default=0)
    residual_cents = db.Column(db.Integer, nullable=False, default=0)
    method = db.Column(db.String(10), nullable=False, default="linear")
    duration_months = db.Column(db.Integer)
    fiscal_coefficient = db.Column(db.Numeric(4, 2))
    prior_depreciation_cents = db.Column(db.Integer, nullable=False, default=0)
    prior_as_of = db.Column(db.Date)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="SET NULL"))
    purchase_line_id = db.Column(db.Integer, db.ForeignKey("purchase_lines.id", ondelete="SET NULL"))
    status = db.Column(db.String(12), nullable=False, default="in_use")
    in_service_entry_id = db.Column(db.Integer, db.ForeignKey("journal_entries.id", ondelete="SET NULL"))
    disposal_date = db.Column(db.Date)
    disposal_price_cents = db.Column(db.Integer)
    disposal_entry_id = db.Column(db.Integer, db.ForeignKey("journal_entries.id", ondelete="SET NULL"))
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id", ondelete="SET NULL"))
    notes = db.Column(db.Text)
    # Biens vivants immobilisés (lot AG5.a) : nature, espèce, catégorie d'âge, effectif (têtes ou plants), origine.
    living_kind = db.Column(db.String(10))
    species = db.Column(db.String(80))
    age_class = db.Column(db.String(80))
    units = db.Column(db.Integer)
    origin = db.Column(db.String(12))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    parent = db.relationship("Asset", remote_side=[id], back_populates="components")
    components = db.relationship("Asset", back_populates="parent", cascade="all, delete-orphan", order_by="Asset.id")
    account = db.relationship("Account", foreign_keys=[account_id])
    depreciation_account = db.relationship("Account", foreign_keys=[depreciation_account_id])
    expense_account = db.relationship("Account", foreign_keys=[expense_account_id])
    waiting_account = db.relationship("Account", foreign_keys=[waiting_account_id])
    project = db.relationship("Project")
    depreciations = db.relationship("AssetDepreciation", back_populates="asset", cascade="all, delete-orphan",
                                    order_by="AssetDepreciation.started_on")

    @property
    def base_cents(self) -> int:
        return max(self.acquisition_cents - (self.residual_cents or 0), 0)


class AssetDepreciation(db.Model):
    """Dotation passée d'un exercice (figée) ; le reste du plan se recalcule à partir d'elles."""
    __tablename__ = "asset_depreciations"
    __table_args__ = (db.UniqueConstraint("asset_id", "fiscal_year_id", name="uq_asset_depreciation_year"),)

    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False)
    started_on = db.Column(db.Date, nullable=False)
    stopped_on = db.Column(db.Date, nullable=False)
    days = db.Column(db.Integer, nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False)
    entry_id = db.Column(db.Integer, db.ForeignKey("journal_entries.id", ondelete="SET NULL"))

    asset = db.relationship("Asset", back_populates="depreciations")
    fiscal_year = db.relationship("FiscalYear")


class LivingWipCost(db.Model):
    """Coûts de croissance d'un bien vivant en cours (234x) portés en en-cours à la clôture d'un exercice (lot AG5.b) :
    D 234x / C 7222, écriture gérée `LIVING_WIP`, non extournée ; la valeur d'origine de la fiche en cours en tient
    compte quand l'écriture est passée."""
    __tablename__ = "living_wip_costs"
    __table_args__ = (db.UniqueConstraint("asset_id", "fiscal_year_id", name="uq_living_wip_costs_asset_fy"),)

    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False)
    basis = db.Column(db.String(300))
    entry_id = db.Column(db.Integer, db.ForeignKey("journal_entries.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    asset = db.relationship("Asset")


LIVING_EXIT_KINDS = {"sale": "Cession", "death": "Mort", "casualty": "Sinistre", "sanitary_slaughter": "Abattage sanitaire",
                     "scrap": "Mise au rebut"}


class AssetLivingExit(db.Model):
    """Sortie d'un bien vivant (lot AG5.c) : type, effectif, prix ou indemnité (D 462 / C 7571), valeur nette sortie."""
    __tablename__ = "asset_living_exits"

    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    on = db.Column(db.Date, nullable=False)
    kind = db.Column(db.String(20), nullable=False)
    units = db.Column(db.Integer)
    price_cents = db.Column(db.Integer)
    indemnity_cents = db.Column(db.Integer)
    book_value_cents = db.Column(db.Integer, nullable=False, default=0)
    entry_id = db.Column(db.Integer, db.ForeignKey("journal_entries.id", ondelete="SET NULL"))
    indemnity_entry_id = db.Column(db.Integer, db.ForeignKey("journal_entries.id", ondelete="SET NULL"))
    note = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    asset = db.relationship("Asset")
    reinvestment = db.relationship("LivingReinvestment", back_populates="exit", uselist=False, cascade="all, delete-orphan")


class LivingReinvestment(db.Model):
    """Abattage sanitaire (lot AG5.c) : indemnité, valeur nette des animaux abattus, reconstitution du cheptel dans les
    2 ans ; lu par AG6 pour l'exonération et la réintégration de la part non réinvestie (art. 75-0 D, à vérifier)."""
    __tablename__ = "living_reinvestments"

    id = db.Column(db.Integer, primary_key=True)
    exit_id = db.Column(db.Integer, db.ForeignKey("asset_living_exits.id", ondelete="CASCADE"), nullable=False, unique=True)
    indemnity_cents = db.Column(db.Integer, nullable=False)
    book_value_cents = db.Column(db.Integer, nullable=False)
    deadline = db.Column(db.Date, nullable=False)
    reinvested_cents = db.Column(db.Integer, nullable=False, default=0)
    reinvested_on = db.Column(db.Date)
    note = db.Column(db.String(300))

    exit = db.relationship("AssetLivingExit", back_populates="reinvestment")


class AssetImpairment(db.Model):
    """Dépréciation d'un bien vivant à la clôture d'un exercice (lot AG5.c) : montant cumulé voulu au bilan (294) et
    motif ; l'écriture gérée `LIVING_IMPAIRMENT` passe la différence avec la clôture précédente (68164 / 78164)."""
    __tablename__ = "asset_impairments"
    __table_args__ = (db.UniqueConstraint("asset_id", "fiscal_year_id", name="uq_asset_impairments_asset_fy"),)

    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(300))
    entry_id = db.Column(db.Integer, db.ForeignKey("journal_entries.id", ondelete="SET NULL"))

    asset = db.relationship("Asset")
