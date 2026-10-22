from datetime import datetime

from sqlalchemy import event
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from app.extensions import db

FY_OPEN = "open"
FY_PROVISIONAL = "provisional"
FY_CLOSED = "closed"
FY_STATUSES = (FY_OPEN, FY_PROVISIONAL, FY_CLOSED)
FY_STATUS_LABELS = {FY_OPEN: "Ouvert", FY_PROVISIONAL: "Clôture provisoire", FY_CLOSED: "Clôturé"}


class FiscalYear(db.Model):
    __tablename__ = "fiscal_years"

    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(50), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    # Verrou lu par tous les contrôles d'écriture : vrai dès la clôture provisoire.
    # Tenu à jour avec `status` (voir _sync_status_and_lock).
    closed = db.Column(db.Boolean, default=False, nullable=False)
    status = db.Column(db.String(12), nullable=False, default=FY_OPEN, server_default=FY_OPEN)
    provisional_at = db.Column(db.DateTime)
    closed_at = db.Column(db.DateTime)              # clôture définitive (irréversible)
    closed_by_user_id = db.Column(db.Integer)       # utilisateur de la méta-base
    fec_sha256 = db.Column(db.String(64))           # FEC figé à la clôture définitive
    fec_path = db.Column(db.String(300))
    allocation_decided_on = db.Column(db.Date)      # affectation du résultat (AG / associés)
    allocation_body = db.Column(db.String(100))
    # Assujetti à la TVA : TVA des achats en 44566 ; sinon incluse dans la charge.
    vat_liable = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    entries = db.relationship("JournalEntry", back_populates="fiscal_year", lazy="dynamic")

    @property
    def status_label(self):
        return FY_STATUS_LABELS.get(self.status, self.status)

    @property
    def is_final(self):
        return self.status == FY_CLOSED

    def __repr__(self):
        return f"<FiscalYear {self.label} {self.status}>"


@event.listens_for(Session, "before_flush")
def _sync_status_and_lock(session, flush_context, instances):
    """`status` et `closed` restent cohérents, quel que soit le champ modifié : statut changé →
    verrou recalculé ; verrou seul changé (ancien code, tests) → statut déduit."""
    for obj in list(session.new) + list(session.dirty):
        if not isinstance(obj, FiscalYear):
            continue
        attrs = sa_inspect(obj).attrs
        if obj.status is not None and attrs.status.history.has_changes():
            obj.closed = obj.status != FY_OPEN
        elif attrs.closed.history.has_changes() or obj.status is None:
            obj.status = FY_PROVISIONAL if obj.closed else FY_OPEN
        if obj.status != FY_OPEN and obj.provisional_at is None:
            obj.provisional_at = datetime.utcnow()
