from datetime import datetime
from app.extensions import db


class BankAccount(db.Model):
    __tablename__ = "bank_accounts"

    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(100), nullable=False)
    iban = db.Column(db.String(34))
    # Nature (lot D.1) : `bank` (relevés OFX / Qonto, rapprochement) ou `cash` (caisse, compte 53x,
    # mouvements saisis à la main).
    kind = db.Column(db.String(8), nullable=False, default="bank", server_default="bank")
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    # Lien Qonto : compte Qonto synchronisé, date de début, curseur de la dernière synchro réussie (UTC).
    qonto_account_id = db.Column(db.String(36), unique=True, nullable=True)
    qonto_sync_from = db.Column(db.Date, nullable=True)
    qonto_synced_at = db.Column(db.DateTime, nullable=True)
    # Solde bancaire d'ouverture (relevé) au début de la journée `opening_balance_date`, saisi par
    # l'utilisateur : le solde bancaire affiché en ajoute les transactions importées (hors annulées).
    # `opening_entry_id` : écriture d'apport initial (512 contre 101 / 102 / 103 / 108) passée à la saisie.
    opening_balance_cents = db.Column(db.Integer, nullable=True)
    opening_balance_date = db.Column(db.Date, nullable=True)
    opening_entry_id = db.Column(db.Integer, db.ForeignKey("journal_entries.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    account = db.relationship("Account", back_populates="bank_accounts")
    transactions = db.relationship("BankTransaction", back_populates="bank_account", lazy="dynamic")

    def __repr__(self):
        return f"<BankAccount {self.label}>"
