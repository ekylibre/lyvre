from datetime import datetime

from app.extensions import db


class Instance(db.Model):
    __tablename__ = "instances"
    __bind_key__ = "meta"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(50), unique=True, nullable=False, index=True)
    label = db.Column(db.String(200), nullable=False)
    database_url = db.Column(db.String(500), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Instance {self.slug}>"
