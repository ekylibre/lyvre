from datetime import datetime
from app.extensions import db


class Journal(db.Model):
    __tablename__ = "journals"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False)
    label = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    entries = db.relationship("JournalEntry", back_populates="journal", lazy="dynamic")

    def __repr__(self):
        return f"<Journal {self.code}>"
