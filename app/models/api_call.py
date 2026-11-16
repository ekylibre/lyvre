"""Journal des appels par clé d'API (lots AK3 et AK4, claudedocs/design_api_mcp_aiffel.md § 3.2).

Base de l'instance : il suit la structure (sauvegarde, restauration). `key_id` renvoie à `api_keys` (méta-base),
sans clé étrangère. Sert aussi à l'idempotence des créations (`idempotency_key`) et au plafond quotidien.
"""
from datetime import datetime

from app.extensions import db


class ApiCall(db.Model):
    __tablename__ = "api_calls"
    __table_args__ = (db.UniqueConstraint("key_id", "idempotency_key", name="uq_api_calls_idempotency"),)

    id = db.Column(db.Integer, primary_key=True)
    key_id = db.Column(db.Integer, nullable=False, index=True)
    at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    channel = db.Column(db.String(4), nullable=False)          # mcp | rest
    target = db.Column(db.String(80), nullable=False)          # outil ou endpoint
    domain = db.Column(db.String(20))
    access = db.Column(db.String(5))                           # read | write
    status = db.Column(db.Integer, nullable=False, default=200)
    error = db.Column(db.String(300))
    object_type = db.Column(db.String(20))                     # purchase | entity | journal_entry
    object_id = db.Column(db.Integer)
    idempotency_key = db.Column(db.String(80))
    duration_ms = db.Column(db.Integer)
