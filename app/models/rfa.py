"""Remboursement forfaitaire agricole, 3520 (lot AG2.e, claudedocs/design_tva_agricole.md § 6) : attestations
d'achats des clients et demandes déposées. Une demande non déposée n'a pas de ligne : elle se calcule à la volée
(`app/services/rfa.py`)."""
import json
from datetime import datetime

from app.extensions import db

RFA_CLAIM_STATUSES = {"declared": "Déposée", "refunded": "Remboursée"}


class RfaAttestation(db.Model):
    """Attestation d'achats d'un client assujetti pour une année de ventes (une par client et par année), avec sa
    pièce (colonnes `attachment_*`, `app/services/attachments.py`)."""
    __tablename__ = "rfa_attestations"
    __table_args__ = (db.UniqueConstraint("entity_id", "year", name="uq_rfa_attestations_entity_year"),)

    id = db.Column(db.Integer, primary_key=True)
    entity_id = db.Column(db.Integer, db.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False)
    received_on = db.Column(db.Date)
    note = db.Column(db.String(300))
    attachment_path = db.Column(db.String(300))
    attachment_name = db.Column(db.String(200))
    attachment_mime = db.Column(db.String(60))
    attachment_size = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    entity = db.relationship("Entity")


class RfaClaim(db.Model):
    """Demande de remboursement forfaitaire d'une année de ventes, déposée : bases figées par classe de taux,
    forfait, écriture de créance (partie double)."""
    __tablename__ = "rfa_claims"

    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False, unique=True)
    status = db.Column(db.String(10), nullable=False, default="declared", server_default="declared")
    high_base_cents = db.Column(db.Integer, nullable=False, default=0)
    low_base_cents = db.Column(db.Integer, nullable=False, default=0)
    amount_cents = db.Column(db.Integer, nullable=False, default=0)
    detail_json = db.Column(db.Text, nullable=False, default="{}")
    declared_on = db.Column(db.Date, nullable=False)
    refunded_on = db.Column(db.Date)
    entry_id = db.Column(db.Integer, db.ForeignKey("journal_entries.id", ondelete="SET NULL"))
    declared_by_user_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    entry = db.relationship("JournalEntry")

    @property
    def detail(self) -> dict:
        return json.loads(self.detail_json or "{}")
