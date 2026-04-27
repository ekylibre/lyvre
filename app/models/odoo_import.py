from datetime import datetime
from app.extensions import db


class OdooImportLine(db.Model):
    __tablename__ = "odoo_import_lines"

    id = db.Column(db.Integer, primary_key=True)
    import_batch = db.Column(db.String(50), nullable=False, index=True)
    invoice_number = db.Column(db.String(100))
    invoice_date = db.Column(db.Date)
    partner_name = db.Column(db.String(200))
    product_name = db.Column(db.String(200))
    amount_ht_cents = db.Column(db.Integer, default=0)
    tax_amount_cents = db.Column(db.Integer, default=0)
    amount_ttc_cents = db.Column(db.Integer, default=0)
    account_code = db.Column(db.String(20))
    journal_entry_id = db.Column(db.Integer, db.ForeignKey("journal_entries.id"), nullable=True)
    imported_at = db.Column(db.DateTime, default=datetime.utcnow)

    journal_entry = db.relationship("JournalEntry", back_populates="odoo_lines")

    def __repr__(self):
        return f"<OdooImportLine {self.invoice_number}>"
