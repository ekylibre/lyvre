"""État enregistré d'une occurrence de l'échéancier (lot AG9a.b, claudedocs/design_echeancier_agricole.md § 5.2) :
faite ou ignorée, par qui, comment. Les occurrences elles-mêmes se calculent à la volée (`app/services/agenda.py`)."""
from datetime import datetime

from app.extensions import db

# `unlinked` : paiement reconnu puis détaché par l'utilisateur ; l'occurrence redevient à faire et n'est plus
# rapprochée automatiquement (lot AG9a.c).
DEADLINE_STATES = {"done": "Faite", "skipped": "Ignorée", "unlinked": "Paiement détaché"}
DEADLINE_ORIGINS = {"manual": "Saisie", "bank": "Paiement reconnu"}


class DeadlineState(db.Model):
    __tablename__ = "deadline_states"
    __table_args__ = (db.UniqueConstraint("deadline_id", "occurs_on", "period", name="uq_deadline_states_occurrence"),)

    id = db.Column(db.Integer, primary_key=True)
    deadline_id = db.Column(db.String(20), nullable=False, index=True)   # « FIS-03#2 » : fiche et rang de l'événement
    occurs_on = db.Column(db.Date, nullable=False)
    period = db.Column(db.String(60), nullable=False, default="")
    status = db.Column(db.String(10), nullable=False)
    done_on = db.Column(db.Date)
    origin = db.Column(db.String(12), nullable=False, default="manual", server_default="manual")
    bank_transaction_id = db.Column(db.Integer, db.ForeignKey("bank_transactions.id", ondelete="SET NULL"))
    note = db.Column(db.String(300))
    user_id = db.Column(db.Integer)  # utilisateur de la méta-base
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    bank_transaction = db.relationship("BankTransaction")
