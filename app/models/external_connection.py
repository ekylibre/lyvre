from datetime import datetime

from app.extensions import db


class ExternalConnection(db.Model):
    __tablename__ = "external_connections"
    __table_args__ = (db.UniqueConstraint("service", "key"),)

    id = db.Column(db.Integer, primary_key=True)
    service = db.Column(db.String(30), nullable=False, index=True)
    key = db.Column(db.String(50), nullable=False)
    value = db.Column(db.Text, nullable=True)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def __repr__(self):
        return f"<ExternalConnection {self.service}.{self.key}>"
