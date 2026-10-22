from datetime import datetime

from app.extensions import db

PURCHASE_SOURCES = ["qonto", "manual"]


class Purchase(db.Model):
    """Facture d'achat (ou avoir) : reçue dans Qonto, ou saisie dans l'application."""

    __tablename__ = "purchases"

    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(10), nullable=False, default="qonto", server_default="qonto")
    qonto_id = db.Column(db.String(36), unique=True)
    entity_id = db.Column(
        db.Integer, db.ForeignKey("entities.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Instantané du fournisseur tel que Qonto le donne (rattachement, création d'entité).
    supplier_name = db.Column(db.String(200))
    qonto_supplier_id = db.Column(db.String(36))
    supplier_vat = db.Column(db.String(30))
    supplier_iban = db.Column(db.String(34))
    supplier_siret = db.Column(db.String(14))
    invoice_number = db.Column(db.String(100))
    issue_date = db.Column(db.Date, index=True)
    due_date = db.Column(db.Date)
    payment_date = db.Column(db.Date)
    currency = db.Column(db.String(3), nullable=False, default="EUR", server_default="EUR")
    # Montants en centimes, positifs ; un avoir est signalé par is_credit_note.
    total_cents = db.Column(db.Integer, nullable=False, default=0)
    untaxed_cents = db.Column(db.Integer)
    tax_cents = db.Column(db.Integer)
    payable_cents = db.Column(db.Integer)
    is_credit_note = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    is_einvoice = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    qonto_status = db.Column(db.String(20), index=True)
    # Rejetée, écartée ou document non financier : masquée, jamais comptabilisée.
    is_hidden = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false(),
                          index=True)
    attachment_id = db.Column(db.String(36))
    related_qonto_ids = db.Column(db.Text)  # JSON : factures liées d'un avoir
    # Pièce d'une facture saisie : chemin relatif au dossier de l'instance.
    attachment_path = db.Column(db.String(300))
    attachment_name = db.Column(db.String(200))
    attachment_mime = db.Column(db.String(50))
    attachment_size = db.Column(db.Integer)
    # Envoi à Qonto d'une facture saisie : clé réutilisée au renvoi ; état NULL / sent / failed.
    idempotency_key = db.Column(db.String(36))
    qonto_upload_status = db.Column(db.String(10))
    qonto_upload_error = db.Column(db.Text)
    # Lignes modifiées par le trésorier : la synchronisation ne les régénère plus.
    lines_edited = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    journal_entry_id = db.Column(
        db.Integer, db.ForeignKey("journal_entries.id", ondelete="SET NULL"), nullable=True
    )
    # Changement dans Qonto après comptabilisation (montant, date, statut) : à revoir.
    review_reason = db.Column(db.Text)
    source_updated_at = db.Column(db.DateTime)
    raw_payload = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,
                           nullable=False)

    entity = db.relationship("Entity", back_populates="purchases")
    journal_entry = db.relationship("JournalEntry")
    lines = db.relationship(
        "PurchaseLine", back_populates="purchase", cascade="all, delete-orphan",
        order_by="PurchaseLine.position", passive_deletes=True,
    )
    payments = db.relationship(
        "PurchasePayment", back_populates="purchase", cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self):
        return f"<Purchase {self.invoice_number} {self.total_cents}>"


class PurchaseLine(db.Model):
    __tablename__ = "purchase_lines"

    id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(
        db.Integer, db.ForeignKey("purchases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position = db.Column(db.Integer, nullable=False, default=0)
    product_id = db.Column(
        db.Integer, db.ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    account_id = db.Column(
        db.Integer, db.ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    label = db.Column(db.String(300))
    untaxed_cents = db.Column(db.Integer, nullable=False, default=0)
    # Points de base (2000 = 20 %) ; NULL = taux à confirmer.
    vat_rate_bp = db.Column(db.Integer)
    vat_cents = db.Column(db.Integer, nullable=False, default=0)
    total_cents = db.Column(db.Integer, nullable=False, default=0)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)

    purchase = db.relationship("Purchase", back_populates="lines")
    product = db.relationship("Product")
    account = db.relationship("Account")

    def __repr__(self):
        return f"<PurchaseLine {self.purchase_id}#{self.position} {self.total_cents}>"


PAYMENT_ORIGINS = ["qonto", "match", "manual"]


class PurchasePayment(db.Model):
    """Paiement d'une facture : transaction désignée par Qonto (matched_transactions),
    retrouvée automatiquement (match) ou choisie par le trésorier (manual)."""

    __tablename__ = "purchase_payments"

    id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(
        db.Integer, db.ForeignKey("purchases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # matched_transactions[].transaction_id = UUID de la transaction = BankTransaction.fitid ;
    # NULL pour un lien hors Qonto (transaction OFX).
    qonto_transaction_id = db.Column(db.String(36))
    origin = db.Column(db.String(10), nullable=False, default="qonto", server_default="qonto")
    # Résolue quand la transaction est importée.
    bank_transaction_id = db.Column(
        db.Integer, db.ForeignKey("bank_transactions.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    journal_entry_id = db.Column(
        db.Integer, db.ForeignKey("journal_entries.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        db.UniqueConstraint("purchase_id", "qonto_transaction_id",
                            name="uq_purchase_payment_transaction"),
        db.UniqueConstraint("purchase_id", "bank_transaction_id",
                            name="uq_purchase_payment_bank_transaction"),
    )

    purchase = db.relationship("Purchase", back_populates="payments")
    bank_transaction = db.relationship("BankTransaction")
    journal_entry = db.relationship("JournalEntry")

    def __repr__(self):
        return f"<PurchasePayment {self.purchase_id} {self.qonto_transaction_id}>"
