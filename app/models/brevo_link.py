from datetime import datetime

from app.extensions import db

BREVO_LINKED = "linked"
BREVO_CONFLICT = "conflict"
BREVO_REMOVED = "removed"


class BrevoLink(db.Model):
    """Lien durable entre un adhérent et son contact Brevo (lot B2) : une fois lié, l'adhérent n'est
    plus jamais recherché par e-mail ni recréé. Le lien survit à la suppression du tiers
    (`entity_id` nul) le temps de retirer le contact de la liste."""
    __tablename__ = "brevo_links"

    id = db.Column(db.Integer, primary_key=True)
    entity_id = db.Column(db.Integer, db.ForeignKey("entities.id", ondelete="SET NULL"), unique=True)
    contact_id = db.Column(db.BigInteger, nullable=False, unique=True)
    email = db.Column(db.String(200))              # e-mail tel qu'envoyé la dernière fois
    payload_hash = db.Column(db.String(64))        # empreinte des valeurs envoyées
    in_list = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    state = db.Column(db.String(12), nullable=False, default=BREVO_LINKED, server_default=BREVO_LINKED)
    note = db.Column(db.String(300))               # motif du conflit, dernière erreur
    synced_at = db.Column(db.DateTime, default=datetime.utcnow)

    entity = db.relationship("Entity", foreign_keys=[entity_id])
