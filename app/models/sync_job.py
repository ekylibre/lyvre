from datetime import datetime
from app.extensions import db


SYNC_KIND_PAYOUTS = "payouts"
SYNC_KIND_PAYOUT_PAYMENTS = "payout_payments"
SYNC_KIND_METRICS = "metrics"
SYNC_KIND_QONTO = "qonto_transactions"
SYNC_KIND_QONTO_INVOICES = "qonto_supplier_invoices"
SYNC_KIND_QONTO_SALES = "qonto_sales"
SYNC_KIND_RECEIPTS_ISSUE = "donation_receipts"
SYNC_KIND_RECEIPTS_SEND = "donation_receipts_send"
SYNC_KIND_SIRENE_REFRESH = "sirene_refresh"
SYNC_KIND_BREVO = "brevo_sync"
SYNC_KIND_EKYLIBRE = "ekylibre_sync"
SYNC_KIND_EKYLIBRE_ANALYSIS = "ekylibre_restore_analysis"   # lot RE6 : analyse d'une sauvegarde
SYNC_KIND_EKYLIBRE_RESTORE = "ekylibre_restore"
SYNC_KIND_SUPERPDP = "superpdp_sync"                         # lot PDP1 : réception et statuts            # lot RE6 : restauration

SYNC_STATUS_RUNNING = "running"
SYNC_STATUS_DONE = "done"
SYNC_STATUS_FAILED = "failed"


class SyncJob(db.Model):
    __tablename__ = "sync_jobs"

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(40), nullable=False, index=True)
    payout_id = db.Column(
        db.Integer,
        db.ForeignKey("payouts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    bank_account_id = db.Column(
        db.Integer,
        db.ForeignKey("bank_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Utilisateur (méta-base) qui a lancé la tâche : destinataire de la notification de fin.
    started_by_user_id = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(20), nullable=False, default=SYNC_STATUS_RUNNING, index=True)
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    finished_at = db.Column(db.DateTime)
    progress_done = db.Column(db.Integer, default=0, nullable=False)
    progress_total = db.Column(db.Integer)
    message = db.Column(db.Text)
    result_json = db.Column(db.Text)

    payout = db.relationship("Payout", foreign_keys=[payout_id])

    @property
    def is_running(self):
        return self.status == SYNC_STATUS_RUNNING

    @property
    def is_terminal(self):
        return self.status in (SYNC_STATUS_DONE, SYNC_STATUS_FAILED)

    def __repr__(self):
        return f"<SyncJob {self.id} {self.kind} {self.status}>"
