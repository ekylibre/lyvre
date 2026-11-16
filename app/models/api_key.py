"""Clé d'API d'une instance, rattachée à un utilisateur (lot AK1, claudedocs/design_api_mcp_aiffel.md § 3.1).

Méta-base : la clé est vérifiée avant le choix de l'instance. Seule l'empreinte SHA-256 du secret est gardée ;
la clé complète `lyv_<public_id>_<secret>` n'est montrée qu'une fois, à la création.
"""
import json
from datetime import datetime

from app.extensions import db

STATE_ACTIVE, STATE_EXPIRED, STATE_REVOKED = "active", "expired", "revoked"


class ApiKey(db.Model):
    __tablename__ = "api_keys"
    __bind_key__ = "meta"

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(10), unique=True, nullable=False, index=True)
    secret_hash = db.Column(db.String(64), nullable=False)
    instance_id = db.Column(db.Integer, db.ForeignKey("instances.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    read_domains = db.Column(db.Text, nullable=False, default="[]")
    write_domains = db.Column(db.Text, nullable=False, default="[]")
    rate_per_minute = db.Column(db.Integer, nullable=False, default=60)
    creations_per_day = db.Column(db.Integer, nullable=False, default=200)
    expires_at = db.Column(db.DateTime, nullable=False)
    revoked_at = db.Column(db.DateTime)
    revoked_by_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    created_by_id = db.Column(db.Integer)
    last_used_at = db.Column(db.DateTime)

    user = db.relationship("User", backref=db.backref("api_keys", cascade="all, delete-orphan"))
    instance = db.relationship("Instance", backref=db.backref("api_keys", cascade="all, delete-orphan"))

    @property
    def reads(self) -> list[str]:
        return json.loads(self.read_domains or "[]")

    @property
    def writes(self) -> list[str]:
        return json.loads(self.write_domains or "[]")

    def state(self, now: datetime | None = None) -> str:
        if self.revoked_at is not None:
            return STATE_REVOKED
        if self.expires_at <= (now or datetime.utcnow()):
            return STATE_EXPIRED
        return STATE_ACTIVE

    @property
    def prefix(self) -> str:
        return f"lyv_{self.public_id}_…"

    def __repr__(self):
        return f"<ApiKey {self.public_id} {self.name!r}>"
