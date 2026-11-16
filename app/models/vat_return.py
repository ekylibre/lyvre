import json
from datetime import datetime

from app.extensions import db

VAT_RETURN_STATUSES = {"validated": "Validée", "declared": "Déclarée"}


class VatReturn(db.Model):
    """Déclaration de TVA d'une période (lot T3) : cases figées à la validation, écriture de liquidation,
    puis dépôt sur TeleDEC (« déclarée », période verrouillée). Une période non validée n'a pas de
    ligne : elle se calcule à la volée (`vat_return.compute`)."""
    __tablename__ = "vat_returns"
    __table_args__ = (db.UniqueConstraint("period_start", "form", name="uq_vat_returns_period"),)

    id = db.Column(db.Integer, primary_key=True)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey("fiscal_years.id"), nullable=False)
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    form = db.Column(db.String(10), nullable=False, default="CA3", server_default="CA3")
    status = db.Column(db.String(10), nullable=False, default="validated", server_default="validated")
    # Cases figées (euros) et détail par code (centimes) : {"boxes": {...}, "codes": {...}, "form_year": 2026}.
    boxes_json = db.Column(db.Text, nullable=False)
    credit_carried_cents = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    due_cents = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    credit_cents = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    # Lot AG2.a : remboursement de crédit demandé (case 26 de la CA3, formulaire 3519), déduit du crédit reporté.
    refund_cents = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    liquidation_entry_id = db.Column(db.Integer, db.ForeignKey("journal_entries.id", ondelete="SET NULL"))
    deadline = db.Column(db.Date)
    declared_on = db.Column(db.Date)
    declared_reference = db.Column(db.String(50))
    validated_at = db.Column(db.DateTime, default=datetime.utcnow)
    validated_by_user_id = db.Column(db.Integer)  # utilisateur de la méta-base

    fiscal_year = db.relationship("FiscalYear")
    liquidation_entry = db.relationship("JournalEntry")

    @property
    def detail(self) -> dict:
        return json.loads(self.boxes_json)

    def __repr__(self):
        return f"<VatReturn {self.form} {self.period_start} {self.status}>"
