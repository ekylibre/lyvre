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
# Devis (lot S3) : émis, accepté, refusé, facturé ; « expiré » se lit (émis, date de validité passée).
QUOTE_STATUS_LABELS = {
    "draft": "Brouillon", "issued": "Envoyé", "accepted": "Accepté", "refused": "Refusé", "expired": "Expiré",
    "invoiced": "Facturé",
}
QUOTE_VALIDITY_DAYS = 30
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
    vat_regime = db.Column(db.String(8))  # lot T2 : régime TVA du document ; nul = celui du client
    quote_id = db.Column(db.Integer, db.ForeignKey("sales.id", ondelete="SET NULL"))
    invoice_id = db.Column(db.Integer, db.ForeignKey("sales.id", ondelete="RESTRICT"))
    credit_reason = db.Column(db.Text)
    recurrence_id = db.Column(db.Integer, db.ForeignKey("recurrences.id", ondelete="SET NULL"))
    lease_id = db.Column(db.Integer, db.ForeignKey("leases.id", ondelete="SET NULL"))
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
    payments = db.relationship("SalePayment", back_populates="sale", cascade="all, delete-orphan",
                               order_by="SalePayment.paid_on")

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


PAYMENT_METHODS = {"transfer": "Virement", "check": "Chèque", "cash": "Espèces", "card": "Carte", "other": "Autre"}


class SalePayment(db.Model):
    """Encaissement d'une facture (lot S2) : transaction bancaire rapprochée (`origin = bank`) ou
    saisie (`manual` : chèque, espèces…), écriture banque ou caisse / 411 ; plusieurs factures d'un
    même client peuvent partager une transaction et son écriture. `vat_released_cents` : TVA virée
    de 44574 à 44571 (TVA à l'encaissement)."""
    __tablename__ = "sale_payments"

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id", ondelete="CASCADE"), nullable=False, index=True)
    amount_cents = db.Column(db.Integer, nullable=False)
    paid_on = db.Column(db.Date, nullable=False)
    origin = db.Column(db.String(8), nullable=False, default="bank")    # bank | manual
    method = db.Column(db.String(12))
    bank_transaction_id = db.Column(db.Integer, db.ForeignKey("bank_transactions.id", ondelete="SET NULL"), index=True)
    bank_account_id = db.Column(db.Integer, db.ForeignKey("bank_accounts.id", ondelete="SET NULL"))
    journal_entry_id = db.Column(db.Integer, db.ForeignKey("journal_entries.id", ondelete="SET NULL"))
    vat_released_cents = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    qonto_marked = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    sale = db.relationship("Sale", back_populates="payments")
    bank_transaction = db.relationship("BankTransaction")
    bank_account = db.relationship("BankAccount")
    journal_entry = db.relationship("JournalEntry")


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
    """Réglages de facturation de l'instance (une ligne, Configuration › Facturation). Les mentions
    légales du vendeur sont dans `organization` (lot G2)."""
    __tablename__ = "billing_settings"

    id = db.Column(db.Integer, primary_key=True)
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
    reminder_subject = db.Column(db.String(255))
    reminder_body = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


FREQUENCIES = {"monthly": "Mensuelle", "quarterly": "Trimestrielle", "yearly": "Annuelle"}


class Recurrence(db.Model):
    """Facture récurrente (lot S5) : modèle (`Sale`, `kind = template`) et échéancier. Les échéances
    dues sont préparées en brouillon (`sale_occurrences` : une seule fois par période)."""
    __tablename__ = "recurrences"

    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey("sales.id", ondelete="CASCADE"), nullable=False)
    label = db.Column(db.String(200), nullable=False)
    frequency = db.Column(db.String(10), nullable=False, default="monthly")
    due_day = db.Column(db.Integer, nullable=False, default=1)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)
    in_advance = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    next_date = db.Column(db.Date, nullable=False)
    qonto_emit = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    active = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    template = db.relationship("Sale", foreign_keys=[template_id], cascade="all, delete-orphan", single_parent=True)


class SaleOccurrence(db.Model):
    __tablename__ = "sale_occurrences"
    __table_args__ = (db.UniqueConstraint("recurrence_id", "period_start", name="uq_sale_occurrences_period"),)

    id = db.Column(db.Integer, primary_key=True)
    recurrence_id = db.Column(db.Integer, db.ForeignKey("recurrences.id", ondelete="CASCADE"), nullable=False)
    period_start = db.Column(db.Date, nullable=False)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id", ondelete="SET NULL"))


class Lease(db.Model):
    """Bail simple (lot S5) : locataire, lot, loyer hors charges, provisions sur charges, échéance,
    dépôt de garantie ; porte la facture récurrente de loyer (avis d'échéance) et les quittances."""
    __tablename__ = "leases"

    id = db.Column(db.Integer, primary_key=True)
    entity_id = db.Column(db.Integer, db.ForeignKey("entities.id", ondelete="RESTRICT"), nullable=False)
    unit_label = db.Column(db.String(200), nullable=False)
    address_line1 = db.Column(db.String(200))
    address_line2 = db.Column(db.String(200))
    postal_code = db.Column(db.String(10))
    city = db.Column(db.String(100))
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)
    rent_cents = db.Column(db.Integer, nullable=False)
    charges_cents = db.Column(db.Integer, nullable=False, default=0)
    due_day = db.Column(db.Integer, nullable=False, default=1)
    deposit_cents = db.Column(db.Integer, nullable=False, default=0)
    deposit_entry_id = db.Column(db.Integer, db.ForeignKey("journal_entries.id", ondelete="SET NULL"))
    rent_account_id = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="SET NULL"))
    charges_account_id = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="SET NULL"))
    recurrence_id = db.Column(db.Integer, db.ForeignKey("recurrences.id", ondelete="SET NULL"))
    notes = db.Column(db.Text)
    active = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    # Assistant de rédaction (lot L1) : brouillon jusqu'à la validation (pas de facture récurrente).
    status = db.Column(db.String(10), nullable=False, default="active", server_default="active")  # draft | active
    kind = db.Column(db.String(12))                 # derogatory | commercial | residential | rural
    premises_label = db.Column(db.String(200))      # lieu-dit, désignation des biens
    signed_on_place = db.Column(db.String(100))     # « Fait à … »
    # Révision du loyer (appliquée au lot L5).
    index_code = db.Column(db.String(10))           # ILC | ILAT | IRL | FERMAGES
    index_reference_period = db.Column(db.String(10))
    index_reference_value = db.Column(db.Numeric(8, 2))
    revision_months = db.Column(db.Integer)         # 12 | 36
    next_revision_date = db.Column(db.Date)
    revise_deposit = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    # Texte du bail (lot L2) : généré depuis le modèle à la validation, figé, retouchable.
    document_html = db.Column(db.Text)
    document_generated_at = db.Column(db.DateTime)
    document_edited = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    entity = db.relationship("Entity")
    recurrence = db.relationship("Recurrence")
    items = db.relationship("LeaseItem", order_by="LeaseItem.position", cascade="all, delete-orphan",
                            back_populates="lease")
    rent_account = db.relationship("Account", foreign_keys=[rent_account_id])
    charges_account = db.relationship("Account", foreign_keys=[charges_account_id])
    deposit_entry = db.relationship("JournalEntry")


class LeaseItem(db.Model):
    """Ligne d'un bail (élément loué A, B…) : surface, prix annuel par unité, références cadastrales,
    géométrie (carte, lot L3). Le loyer du bail est la somme des montants annuels."""
    __tablename__ = "lease_items"

    id = db.Column(db.Integer, primary_key=True)
    lease_id = db.Column(db.Integer, db.ForeignKey("leases.id", ondelete="CASCADE"), nullable=False, index=True)
    position = db.Column(db.Integer, nullable=False, default=0)
    letter = db.Column(db.String(3))
    label = db.Column(db.String(200), nullable=False)
    nature = db.Column(db.String(10), nullable=False, default="flat")       # building | land | flat
    area_m2 = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    built_m2 = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    billing_unit = db.Column(db.String(4), nullable=False, default="flat")  # m2 | ha | flat
    unit_price_cents = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    annual_cents = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    cadastral_refs = db.Column(db.JSON)
    geometry = db.Column(db.JSON)
    source = db.Column(db.String(10), nullable=False, default="manual", server_default="manual")
    partial = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())

    lease = db.relationship("Lease", back_populates="items")


class LeaseTemplate(db.Model):
    """Modèle de bail d'un type (lot L2) : HTML avec champs Jinja, modifiable dans les paramètres ;
    créé depuis le modèle livré (`templates/leases/defaults/<kind>.html`) au premier usage."""
    __tablename__ = "lease_templates"

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(12), nullable=False, unique=True)
    title = db.Column(db.String(200), nullable=False)
    body_html = db.Column(db.Text, nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1, server_default="1")
    reviewed = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())  # enregistré une fois
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    updated_by_id = db.Column(db.Integer)  # utilisateur (base méta), sans clé étrangère


class LeaseSignature(db.Model):
    """Envoi d'un bail à la signature électronique (lot L4, Documenso) : PDF envoyé, statut, PDF
    signé et journal d'audit rangés à la fin."""
    __tablename__ = "lease_signatures"

    id = db.Column(db.Integer, primary_key=True)
    lease_id = db.Column(db.Integer, db.ForeignKey("leases.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = db.Column(db.String(20), nullable=False, default="documenso")
    submission_id = db.Column(db.String(64))
    status = db.Column(db.String(12), nullable=False, default="sent")  # sent | completed | declined | expired | cancelled
    sent_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    completed_at = db.Column(db.DateTime)
    checked_at = db.Column(db.DateTime)
    sent_pdf_path = db.Column(db.String(300))
    signed_pdf_path = db.Column(db.String(300))
    audit_pdf_path = db.Column(db.String(300))
    error = db.Column(db.Text)
    created_by_id = db.Column(db.Integer)  # utilisateur (base méta), sans clé étrangère

    lease = db.relationship("Lease", backref=db.backref("signatures", order_by="LeaseSignature.id",
                                                        cascade="all, delete-orphan"))
    signers = db.relationship("LeaseSigner", order_by="LeaseSigner.position", cascade="all, delete-orphan",
                              back_populates="signature")


class LeaseSigner(db.Model):
    """Signataire d'un envoi : gérants (côté bailleur) puis preneur, dans cet ordre."""
    __tablename__ = "lease_signers"

    id = db.Column(db.Integer, primary_key=True)
    signature_id = db.Column(db.Integer, db.ForeignKey("lease_signatures.id", ondelete="CASCADE"), nullable=False,
                             index=True)
    position = db.Column(db.Integer, nullable=False, default=0)
    role = db.Column(db.String(60), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(200), nullable=False)
    associate_id = db.Column(db.Integer)
    entity_id = db.Column(db.Integer)
    submitter_id = db.Column(db.String(64))
    status = db.Column(db.String(12), nullable=False, default="awaiting")  # awaiting | sent | opened | completed | declined
    signed_at = db.Column(db.DateTime)
    declined_at = db.Column(db.DateTime)

    signature = db.relationship("LeaseSignature", back_populates="signers")


class RentIndex(db.Model):
    """Valeur publiée d'un indice de révision des loyers (lot L5) : ILC, ILAT, IRL (INSEE, trimestriels,
    période « 2026-Q2 ») ou indice national des fermages (arrêté annuel, période « 2026 »)."""
    __tablename__ = "rent_indices"
    __table_args__ = (db.UniqueConstraint("code", "period", name="uq_rent_indices_code_period"),)

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), nullable=False)
    period = db.Column(db.String(10), nullable=False)
    value = db.Column(db.Numeric(8, 2), nullable=False)
    source = db.Column(db.String(10), nullable=False, default="manual")  # insee | manual
    fetched_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class LeaseRevision(db.Model):
    """Révision du loyer d'un bail (lot L5) : en attente de l'indice, puis appliquée (prix des lignes,
    facture récurrente, dépôt de garantie si prévu)."""
    __tablename__ = "lease_revisions"
    __table_args__ = (db.UniqueConstraint("lease_id", "due_date", name="uq_lease_revisions_due"),)

    id = db.Column(db.Integer, primary_key=True)
    lease_id = db.Column(db.Integer, db.ForeignKey("leases.id", ondelete="CASCADE"), nullable=False, index=True)
    due_date = db.Column(db.Date, nullable=False)
    index_code = db.Column(db.String(10), nullable=False)
    old_period = db.Column(db.String(10))
    old_value = db.Column(db.Numeric(8, 2))
    new_period = db.Column(db.String(10), nullable=False)
    new_value = db.Column(db.Numeric(8, 2))
    old_annual_cents = db.Column(db.Integer)
    new_annual_cents = db.Column(db.Integer)
    old_deposit_cents = db.Column(db.Integer)
    new_deposit_cents = db.Column(db.Integer)
    status = db.Column(db.String(10), nullable=False, default="pending")  # pending | applied
    note = db.Column(db.String(300))
    applied_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    lease = db.relationship("Lease", backref=db.backref("revisions", order_by="LeaseRevision.due_date",
                                                        cascade="all, delete-orphan"))


class RentReceipt(db.Model):
    """Quittance (loyer de la période entièrement payé) ou reçu (paiement partiel)."""
    __tablename__ = "rent_receipts"

    id = db.Column(db.Integer, primary_key=True)
    lease_id = db.Column(db.Integer, db.ForeignKey("leases.id", ondelete="CASCADE"), nullable=False)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id", ondelete="CASCADE"), nullable=False)
    kind = db.Column(db.String(10), nullable=False)          # quittance | recu
    period_start = db.Column(db.Date)
    period_end = db.Column(db.Date)
    rent_cents = db.Column(db.Integer, nullable=False)
    charges_cents = db.Column(db.Integer, nullable=False)
    paid_cents = db.Column(db.Integer, nullable=False)
    paid_on = db.Column(db.Date)
    pdf_path = db.Column(db.String(300))
    sent_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    lease = db.relationship("Lease")
    sale = db.relationship("Sale")
