from datetime import datetime

from app.extensions import db


# Mirrors app.models.entity.ENTITY_TYPES — kept here as a free-form string
# to avoid a hard FK on a tiny enum-like list.
RULE_ENTITY_TYPES = [
    "CLIENT",
    "FOURNISSEUR",
    "SALARIE",
    "ADHERENT",
    "ORGANISME",
    "AUTRE",
]


class Rule(db.Model):
    __tablename__ = "rules"

    id = db.Column(db.Integer, primary_key=True)
    analytic_target = db.Column(db.String(24))                       # lot AG8.c : « activity:ID » ou « key:ID »
    position = db.Column(db.Integer, nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)

    # Match conditions (at least one is required, enforced in the validator).
    label_contains = db.Column(db.String(500), nullable=True)
    label_regex = db.Column(db.String(500), nullable=True)
    amount_min_cents = db.Column(db.Integer, nullable=True)
    amount_max_cents = db.Column(db.Integer, nullable=True)
    raw_type = db.Column(db.String(20), nullable=True)

    # Effects applied when the rule matches.
    entity_name = db.Column(db.String(200), nullable=True)
    entity_type = db.Column(db.String(20), nullable=True)
    category = db.Column(db.String(200), nullable=True)
    account_code = db.Column(db.String(20), nullable=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)

    is_active = db.Column(db.Boolean, nullable=False, default=True)
    project = db.relationship("Project")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self):
        return f"<Rule {self.position}:{self.name}>"
