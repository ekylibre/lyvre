from datetime import datetime
from app.extensions import db


class FiscalYear(db.Model):
    __tablename__ = "fiscal_years"

    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(50), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    closed = db.Column(db.Boolean, default=False, nullable=False)
    # Assujetti à la TVA : TVA des achats en 44566 ; sinon incluse dans la charge.
    vat_liable = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    entries = db.relationship("JournalEntry", back_populates="fiscal_year", lazy="dynamic")

    def __repr__(self):
        return f"<FiscalYear {self.label}>"
