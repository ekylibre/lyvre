from datetime import datetime

from app.extensions import db

# Nature de la ressource affectée → comptes (règlement ANC 2018-06) : dotation au débit de 689x et
# crédit de 19x ; utilisation au débit de 19x et crédit de 789x.
FUND_KINDS = {
    "subsidy": {"label": "Subvention d'exploitation", "accounts": ("6894", "194", "7894")},
    "contribution": {"label": "Contribution financière d'un autre organisme", "accounts": ("6895", "195", "7895")},
    "public_generosity": {"label": "Ressource liée à la générosité du public", "accounts": ("6896", "196", "7896")},
}
MOVEMENT_KINDS = ("allocation", "use")


class DedicatedFund(db.Model):
    """Ressource affectée à un objet précis (subvention, don…), dont la part non utilisée à la
    clôture est reportée en fonds dédiés."""
    __tablename__ = "dedicated_funds"

    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(200), nullable=False)
    kind = db.Column(db.String(20), nullable=False)
    resource_account_id = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="SET NULL"))
    entity_id = db.Column(db.Integer, db.ForeignKey("entities.id", ondelete="SET NULL"))  # financeur
    origin_fiscal_year_id = db.Column(db.Integer, db.ForeignKey("fiscal_years.id"), nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False)   # montant de la ressource reçue
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    resource_account = db.relationship("Account")
    origin_fiscal_year = db.relationship("FiscalYear")
    movements = db.relationship("DedicatedFundMovement", backref="fund", cascade="all, delete-orphan",
                                order_by="DedicatedFundMovement.id")


class DedicatedFundMovement(db.Model):
    """Dotation (`allocation`) ou utilisation (`use`) d'un fonds dédié sur un exercice."""
    __tablename__ = "dedicated_fund_movements"

    id = db.Column(db.Integer, primary_key=True)
    fund_id = db.Column(db.Integer, db.ForeignKey("dedicated_funds.id", ondelete="CASCADE"), nullable=False,
                        index=True)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False,
                               index=True)
    kind = db.Column(db.String(12), nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False)
    entry_id = db.Column(db.Integer, db.ForeignKey("journal_entries.id", ondelete="SET NULL"))

    entry = db.relationship("JournalEntry")
    fiscal_year = db.relationship("FiscalYear")
