from datetime import datetime

from app.extensions import db

ROLE_ADMIN = "admin"
ROLE_TREASURER = "treasurer"
ROLE_ACCOUNTANT = "accountant"
ROLES = (ROLE_ADMIN, ROLE_TREASURER, ROLE_ACCOUNTANT)
ROLE_LABELS = {ROLE_ADMIN: "Administrateur", ROLE_TREASURER: "Trésorier", ROLE_ACCOUNTANT: "Expert-comptable"}


class InstanceMembership(db.Model):
    """Accès d'un utilisateur à une instance, avec son rôle (méta-base).

    Un administrateur global (`users.is_admin`) est administrateur de toutes les instances sans
    ligne ici ; les autres utilisateurs n'accèdent qu'aux instances listées.
    """
    __tablename__ = "instance_memberships"
    __bind_key__ = "meta"
    __table_args__ = (db.UniqueConstraint("user_id", "instance_id", name="uq_membership_user_instance"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    instance_id = db.Column(db.Integer, db.ForeignKey("instances.id", ondelete="CASCADE"), nullable=False,
                            index=True)
    role = db.Column(db.String(20), nullable=False, default=ROLE_TREASURER)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    created_by_user_id = db.Column(db.Integer, nullable=True)

    user = db.relationship("User", backref=db.backref("memberships", cascade="all, delete-orphan"))
    instance = db.relationship("Instance", backref=db.backref("memberships", cascade="all, delete-orphan"))

    def __repr__(self):
        return f"<InstanceMembership user={self.user_id} instance={self.instance_id} {self.role}>"
