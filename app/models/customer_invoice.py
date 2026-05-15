from datetime import datetime
from app.extensions import db


CUSTOMER_INVOICE_STATES = [
    ("draft", "Brouillon"),
    ("posted", "Comptabilisée"),
    ("cancel", "Annulée"),
]

CUSTOMER_INVOICE_PAYMENT_STATES = [
    ("not_paid", "Non payée"),
    ("in_payment", "En cours de paiement"),
    ("partial", "Partiellement payée"),
    ("paid", "Payée"),
    ("reversed", "Annulée par avoir"),
    ("invoicing_legacy", "Hérité"),
]


class CustomerInvoice(db.Model):
    """Facture client Odoo (account.move avec move_type='out_invoice')."""
    __tablename__ = "customer_invoices"

    id = db.Column(db.Integer, primary_key=True)
    odoo_id = db.Column(db.Integer, unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), index=True)
    ref = db.Column(db.String(200))
    state = db.Column(db.String(20), index=True)
    payment_state = db.Column(db.String(20), index=True)
    partner_id = db.Column(db.Integer)
    partner_name = db.Column(db.String(200))
    partner_email = db.Column(db.String(200), index=True)
    entity_id = db.Column(
        db.Integer,
        db.ForeignKey("entities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    invoice_date = db.Column(db.Date, index=True)
    invoice_date_due = db.Column(db.Date)
    currency = db.Column(db.String(3), nullable=False, default="EUR")
    amount_untaxed_cents = db.Column(db.Integer, nullable=False, default=0)
    amount_tax_cents = db.Column(db.Integer, nullable=False, default=0)
    amount_total_cents = db.Column(db.Integer, nullable=False, default=0)
    amount_residual_cents = db.Column(db.Integer, nullable=False, default=0)
    invoice_origin = db.Column(db.String(200))
    journal_name = db.Column(db.String(100))
    narration = db.Column(db.Text)
    raw_payload = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    imported_at = db.Column(db.DateTime, default=datetime.utcnow)

    entity = db.relationship("Entity", foreign_keys=[entity_id])

    lines = db.relationship(
        "CustomerInvoiceLine",
        backref="invoice",
        lazy="dynamic",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self):
        return f"<CustomerInvoice {self.odoo_id} {self.name}>"
