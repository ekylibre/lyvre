from datetime import datetime

from app.extensions import db


class IntegrationState(db.Model):
    """Per-service switch and last operational check of an external integration.

    A missing row means: enabled, never checked.
    """

    __tablename__ = "integration_states"

    id = db.Column(db.Integer, primary_key=True)
    service = db.Column(db.String(30), nullable=False, unique=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    checked_at = db.Column(db.DateTime, nullable=True)
    check_ok = db.Column(db.Boolean, nullable=True)
    check_message = db.Column(db.Text, nullable=True)
    check_duration_ms = db.Column(db.Integer, nullable=True)
    # SHA-256 of the configuration the last check ran against.
    checked_fingerprint = db.Column(db.String(64), nullable=True)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def __repr__(self):
        return f"<IntegrationState {self.service} enabled={self.enabled}>"
