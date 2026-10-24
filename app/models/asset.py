from datetime import datetime

from app.extensions import db

ASSET_METHODS = ("linear", "regressive", "none")
ASSET_STATUSES = ("waiting", "in_use", "depreciated", "sold", "scrapped")


class Asset(db.Model):
    """Immobilisation (lot F5) ; un bien peut avoir des composants (`parent_id`), chacun son plan."""
    __tablename__ = "assets"

    id = db.Column(db.Integer, primary_key=True)
    parent_id = db.Column(db.Integer, db.ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    label = db.Column(db.String(200), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False)
    depreciation_account_id = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="SET NULL"))
    expense_account_id = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="SET NULL"))
    waiting_account_id = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="SET NULL"))
    acquired_on = db.Column(db.Date, nullable=False)
    in_service_date = db.Column(db.Date)
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
