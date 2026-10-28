from datetime import datetime
from app.extensions import db

SOURCES = ["MANUAL", "OFX_IMPORT", "QONTO_IMPORT", "ODOO_IMPORT", "PURCHASE"]

# Écritures générées par la clôture (lot A) : jamais proposées au rapprochement bancaire.
SOURCE_OPENING = "OPENING"          # à-nouveaux (journal AN)
SOURCE_REVERSAL = "REVERSAL"        # extourne d'une écriture d'inventaire
SOURCE_ALLOCATION = "ALLOCATION"    # affectation du résultat
SOURCE_CLOSING = "CLOSING"          # écritures de clôture
SOURCE_INVENTORY = "INVENTORY"      # écritures d'inventaire (charges à payer, CCA, PCA…)
SOURCE_DEDICATED_FUND = "DEDICATED_FUND"  # dotation / utilisation de fonds dédiés
SOURCE_DEPRECIATION = "DEPRECIATION"      # dotations aux amortissements de l'exercice (lot F5)
CLOSING_SOURCES = (SOURCE_OPENING, SOURCE_REVERSAL, SOURCE_ALLOCATION, SOURCE_CLOSING)
# Écritures produites par l'assistant de clôture : modifiées ou supprimées seulement par lui.
SOURCE_VAT_RETURN = "VAT_RETURN"          # liquidation d'une déclaration de TVA (lot T3)
MANAGED_SOURCES = (*CLOSING_SOURCES, SOURCE_INVENTORY, SOURCE_DEDICATED_FUND, SOURCE_DEPRECIATION, SOURCE_VAT_RETURN)
# Écriture d'une facture ou d'un avoir de vente émis : ni modifiée ni supprimée (on passe un avoir).
SOURCE_SALE = "SALE"
SALE_LOCKED_MESSAGE = "Écriture d'une facture de vente émise : elle se corrige par un avoir (Ventes)."
# Contrepassation d'une écriture (lot F1) : écriture inverse liée par `reverses_entry_id`.
SOURCE_CANCELLATION = "CANCELLATION"
# Écriture d'écart de lettrage (lot F3), créée et retirée avec son lettrage.
SOURCE_LETTERING = "LETTERING"
# Reprise d'historique (lot F6) : FEC (historique complet) et tableur.
SOURCE_FEC_IMPORT = "FEC_IMPORT"
SOURCE_SHEET_IMPORT = "SHEET_IMPORT"
INVENTORY_KINDS = ("accrued_expense", "accrued_income", "prepaid_expense", "deferred_income")


class JournalEntry(db.Model):
    __tablename__ = "journal_entries"

    id = db.Column(db.Integer, primary_key=True)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey("fiscal_years.id"), nullable=False)
    journal_id = db.Column(db.Integer, db.ForeignKey("journals.id"), nullable=False)
    entry_date = db.Column(db.Date, nullable=False)
    reference = db.Column(db.String(50))
    description = db.Column(db.String(500))
    is_balanced = db.Column(db.Boolean, default=False, nullable=False)
    source = db.Column(db.String(20), default="MANUAL", nullable=False)
    source_ref = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Validation (lot F1) : numéro continu par journal et par exercice, attribué par lot à la suite des
    # numéros existants (jamais renuméroté) ; une écriture validée ne se modifie plus (ledger_guard).
    validation_number = db.Column(db.Integer)
    validated_at = db.Column(db.DateTime)
    validation_batch_id = db.Column(db.Integer, db.ForeignKey("validation_batches.id", ondelete="SET NULL"))
    reverses_entry_id = db.Column(db.Integer, db.ForeignKey("journal_entries.id", ondelete="SET NULL"))
    inventory_kind = db.Column(db.String(20))

    fiscal_year = db.relationship("FiscalYear", back_populates="entries")
    journal = db.relationship("Journal", back_populates="entries")
    lines = db.relationship(
        "JournalLine", back_populates="entry", cascade="all, delete-orphan", lazy="joined"
    )
    odoo_lines = db.relationship("OdooImportLine", back_populates="journal_entry")

    @property
    def is_validated(self):
        return self.validation_number is not None

    @property
    def total_debit(self):
        return sum(l.debit_cents for l in self.lines)

    @property
    def total_credit(self):
        return sum(l.credit_cents for l in self.lines)

    def __repr__(self):
        return f"<JournalEntry {self.reference} {self.entry_date}>"
