"""Abonnements d'achat (lot S6, claudedocs/design_ventes.md § 2.3) : contrats récurrents
(internet, téléphone, assurance, banque…) et leurs échéances attendues, auxquelles se rattachent
la facture d'achat réelle et le prélèvement bancaire. Aucune écriture propre."""
from datetime import datetime

from app.extensions import db

CATEGORIES = {"internet": "Internet", "phone": "Téléphone", "insurance": "Assurance", "bank": "Banque",
              "energy": "Énergie", "software": "Logiciel", "rent": "Loyer", "other": "Autre"}
PERIOD_STATUSES = {"expected": "Attendue", "invoiced": "Facture reçue", "paid": "Payée", "missing": "Manquante",
                   "skipped": "Ignorée"}


class Subscription(db.Model):
    __tablename__ = "subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    entity_id = db.Column(db.Integer, db.ForeignKey("entities.id", ondelete="RESTRICT"), nullable=False)
    label = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(20), nullable=False, default="other", server_default="other")
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="SET NULL"))
    amount_cents = db.Column(db.Integer, nullable=False)          # TTC attendu par échéance
    amount_fixed = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    frequency = db.Column(db.String(10), nullable=False, default="monthly", server_default="monthly")
    due_day = db.Column(db.Integer, nullable=False, default=1, server_default="1")
    bank_account_id = db.Column(db.Integer, db.ForeignKey("bank_accounts.id", ondelete="SET NULL"))
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)
    renewal_date = db.Column(db.Date)                              # reconduction tacite
    notice_days = db.Column(db.Integer)                            # préavis de résiliation
    notes = db.Column(db.Text)
    active = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    entity = db.relationship("Entity")
    product = db.relationship("Product")
    bank_account = db.relationship("BankAccount")
    periods = db.relationship("SubscriptionPeriod", back_populates="subscription", cascade="all, delete-orphan",
                              order_by="SubscriptionPeriod.due_date.desc()")


class SubscriptionPeriod(db.Model):
    """Échéance attendue (« facture attendue ») : facture réelle et prélèvement rattachés."""
    __tablename__ = "subscription_periods"
    __table_args__ = (db.UniqueConstraint("subscription_id", "due_date", name="uq_subscription_periods_due"),)

    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    expected_cents = db.Column(db.Integer, nullable=False)
    purchase_id = db.Column(db.Integer, db.ForeignKey("purchases.id", ondelete="SET NULL"))
    bank_transaction_id = db.Column(db.Integer, db.ForeignKey("bank_transactions.id", ondelete="SET NULL"))
    status = db.Column(db.String(10), nullable=False, default="expected", server_default="expected", index=True)

    subscription = db.relationship("Subscription", back_populates="periods")
    purchase = db.relationship("Purchase")
    bank_transaction = db.relationship("BankTransaction")
