"""Module Ventes (claudedocs/design_ventes.md) : devis, factures, avoirs (table `sales`, `kind`),
lignes, compteurs des séries de l'application, envois par email. Lot S1 : factures et avoirs."""
import json
from datetime import datetime

from app.extensions import db

KINDS = ("quote", "invoice", "credit_note", "template")
# Séries de numéros de l'application (V7) : D-2026-0001, F-2026-0001, AV-2026-0001.
SERIES = {"quote": "D", "invoice": "F", "credit_note": "AV"}
STATUS_LABELS = {
    "draft": "Brouillon", "issued": "Émise", "partially_paid": "Payée en partie", "paid": "Payée",
    "canceled": "Annulée",
}
OPERATION_TYPES = {"goods": "Livraison de biens", "services": "Prestation de services", "both": "Biens et services"}
# Mode de TVA figé à l'émission : non assujetti (art. 293 B), exigible à l'encaissement, d'après les débits.
VAT_MODES = ("none", "receipts", "debits")


class Sale(db.Model):
    __tablename__ = "sales"
    __table_args__ = (db.UniqueConstraint("kind", "number", name="uq_sales_kind_number"),)

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(12), nullable=False, default="invoice")
    status = db.Column(db.String(16), nullable=False, default="draft")
    source = db.Column(db.String(8), nullable=False, default="app", server_default="app")
    qonto_emit = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    number = db.Column(db.String(40))
    series_year = db.Column(db.Integer)
    series_seq = db.Column(db.Integer)
    entity_id = db.Column(db.Integer, db.ForeignKey("entities.id", ondelete="RESTRICT"), nullable=False, index=True)
    client_snapshot = db.Column(db.Text)
    issue_date = db.Column(db.Date)
    due_date = db.Column(db.Date, index=True)
    validity_date = db.Column(db.Date)
    service_start = db.Column(db.Date)
    service_end = db.Column(db.Date)
    operation_type = db.Column(db.String(8), nullable=False, default="services", server_default="services")
    purchase_order = db.Column(db.String(100))
    untaxed_cents = db.Column(db.Integer, nullable=False, default=0)
    tax_cents = db.Column(db.Integer, nullable=False, default=0)
    total_cents = db.Column(db.Integer, nullable=False, default=0)
    paid_cents = db.Column(db.Integer, nullable=False, default=0)
    terms = db.Column(db.Text)
    header = db.Column(db.Text)
    footer = db.Column(db.Text)
    vat_mode = db.Column(db.String(10))
    quote_id = db.Column(db.Integer, db.ForeignKey("sales.id", ondelete="SET NULL"))
    invoice_id = db.Column(db.Integer, db.ForeignKey("sales.id", ondelete="RESTRICT"))
    credit_reason = db.Column(db.Text)
    journal_entry_id = db.Column(db.Integer, db.ForeignKey("journal_entries.id", ondelete="SET NULL"))
    pdf_path = db.Column(db.String(300))
    qonto_id = db.Column(db.String(36), unique=True)
    qonto_status = db.Column(db.String(20))
    qonto_attachment_id = db.Column(db.String(36))
    qonto_error = db.Column(db.Text)
    issued_at = db.Column(db.DateTime)
    sent_at = db.Column(db.DateTime)
    last_reminder_at = db.Column(db.DateTime)
    reminder_count = db.Column(db.Integer, nullable=False, default=0)
    raw_payload = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    entity = db.relationship("Entity")
    journal_entry = db.relationship("JournalEntry")
    invoice = db.relationship("Sale", remote_side=[id], foreign_keys=[invoice_id])
    lines = db.relationship("SaleLine", back_populates="sale", cascade="all, delete-orphan",
                            order_by="SaleLine.position")
    emails = db.relationship("SaleEmail", back_populates="sale", cascade="all, delete-orphan",
                             order_by="SaleEmail.sent_at.desc()")

    @property
    def client(self) -> dict:
        """Client tel qu'à l'émission (fiche du tiers pour un brouillon)."""
        if self.client_snapshot:
            return json.loads(self.client_snapshot)
        from app.services.sale_entry import client_snapshot
        return client_snapshot(self.entity)

    def __repr__(self):
        return f"<Sale {self.kind} {self.number or self.id}>"


class SaleLine(db.Model):
    __tablename__ = "sale_lines"

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id", ondelete="CASCADE"), nullable=False, index=True)
    position = db.Column(db.Integer, nullable=False, default=0)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="SET NULL"))
    label = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text)
    quantity_milli = db.Column(db.Integer, nullable=False, default=1000)
    unit = db.Column(db.String(20))
    unit_price_cents = db.Column(db.Integer, nullable=False, default=0)
    discount_bp = db.Column(db.Integer, nullable=False, default=0)
    untaxed_cents = db.Column(db.Integer, nullable=False, default=0)
    vat_rate_bp = db.Column(db.Integer, nullable=False, default=0)
    vat_cents = db.Column(db.Integer, nullable=False, default=0)
    total_cents = db.Column(db.Integer, nullable=False, default=0)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="SET NULL"))
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="SET NULL"))
    nature = db.Column(db.String(8), nullable=False, default="services", server_default="services")

    sale = db.relationship("Sale", back_populates="lines")
    product = db.relationship("Product")
    account = db.relationship("Account")


class SaleCounter(db.Model):
    """Dernier numéro attribué d'une série pour une année civile (continu, jamais réutilisé)."""
    __tablename__ = "sale_counters"

    series = db.Column(db.String(4), primary_key=True)
    year = db.Column(db.Integer, primary_key=True, autoincrement=False)
    last_number = db.Column(db.Integer, nullable=False, default=0)


class SaleEmail(db.Model):
    __tablename__ = "sale_emails"

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id", ondelete="CASCADE"), nullable=False, index=True)
    purpose = db.Column(db.String(10), nullable=False, default="send")   # send | reminder
    channel = db.Column(db.String(6), nullable=False, default="smtp")    # smtp | qonto
    recipients = db.Column(db.Text, nullable=False)
    subject = db.Column(db.String(255))
    status = db.Column(db.String(8), nullable=False)                      # sent | failed
    error = db.Column(db.Text)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    sale = db.relationship("Sale", back_populates="emails")


class BillingSettings(db.Model):
    """Mentions et réglages de facturation de l'instance (une ligne, Configuration › Facturation)."""
    __tablename__ = "billing_settings"

    id = db.Column(db.Integer, primary_key=True)
    legal_form = db.Column(db.String(100))
    share_capital_cents = db.Column(db.Integer)
    rcs = db.Column(db.String(100))
    vat_number = db.Column(db.String(20))
    iban = db.Column(db.String(34))
    bic = db.Column(db.String(11))
    payment_terms_days = db.Column(db.Integer, nullable=False, default=30, server_default="30")
    late_penalty_text = db.Column(db.Text)
    recovery_fee = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    discount_text = db.Column(db.Text)
    footer = db.Column(db.Text)
    logo_path = db.Column(db.String(300))
    send_subject = db.Column(db.String(255))
    send_body = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
