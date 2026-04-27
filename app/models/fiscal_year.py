from datetime import datetime
from app.extensions import db


class FiscalYear(db.Model):
    __tablename__ = "fiscal_years"

    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(50), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    closed = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    entries = db.relationship("JournalEntry", back_populates="fiscal_year", lazy="dynamic")

    def __repr__(self):
        return f"<FiscalYear {self.label}>"
