"""Aides PAC et subventions (lot AG3, claudedocs/design_aides_pac.md § 8.1) : dossiers d'aide et leurs versements.

Les écritures restent celles de la banque et de l'inventaire : le dossier porte la campagne, le dispositif, les
montants (demandé, notifié, versé) et le compte, et sert au rattachement à l'exercice (AG3.c) et à la reprise des
subventions d'investissement (AG3.d).
"""
from datetime import datetime

from app.extensions import db

AID_NATURES = {"operating": "Subvention d'exploitation", "investment": "Subvention d'investissement",
               "mixed": "Mixte (exploitation et investissement)"}
AID_TRIGGERS = {"pac_deadline": "Date limite de la demande PAC", "decision": "Décision d'attribution",
                "payment": "Encaissement"}
AID_STATUSES = {"requested": "Demandée", "granted": "Attribuée", "closed": "Soldée", "refused": "Refusée"}
AID_PAYMENT_KINDS = {"advance": "Avance", "balance": "Solde", "installment": "Fraction", "clawback": "Reversement",
                     "other": "Autre"}


class Aid(db.Model):
    """Dossier d'aide : une campagne (année) d'un dispositif (`data/aids/schemes.yml`)."""
    __tablename__ = "aids"

    id = db.Column(db.Integer, primary_key=True)
    analytic_target = db.Column(db.String(24))                       # lot AG8.c : « activity:ID » ou « key:ID »
    scheme = db.Column(db.String(40), nullable=False)
    label = db.Column(db.String(200), nullable=False)
    campaign = db.Column(db.Integer, nullable=False, index=True)
    funder_entity_id = db.Column(db.Integer, db.ForeignKey("entities.id", ondelete="SET NULL"))
    payer = db.Column(db.String(60))
    nature = db.Column(db.String(12), nullable=False, default="operating")
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False)
    operating_account_id = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="RESTRICT"))
    investment_share_cents = db.Column(db.Integer)          # aide mixte : part d'investissement (131)
    trigger = db.Column(db.String(14), nullable=False, default="decision")
    decision_on = db.Column(db.Date)
    requested_cents = db.Column(db.Integer)
    notified_cents = db.Column(db.Integer)
    notified_on = db.Column(db.Date)
    payment_request_deadline = db.Column(db.Date)
    payment_requested_on = db.Column(db.Date)
    commitment_end_on = db.Column(db.Date)
    status = db.Column(db.String(10), nullable=False, default="requested", server_default="requested")
    grant_entry_id = db.Column(db.Integer, db.ForeignKey("journal_entries.id", ondelete="SET NULL"))   # octroi 441 / 131
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    account = db.relationship("Account", foreign_keys=[account_id])
    operating_account = db.relationship("Account", foreign_keys=[operating_account_id])
    funder = db.relationship("Entity")
    payments = db.relationship("AidPayment", back_populates="aid", cascade="all, delete-orphan",
                               order_by="AidPayment.paid_on, AidPayment.id")
    accruals = db.relationship("AidAccrual", back_populates="aid", cascade="all, delete-orphan")
    grant_entry = db.relationship("JournalEntry", foreign_keys=[grant_entry_id])
    assets = db.relationship("AidAsset", back_populates="aid", cascade="all, delete-orphan", order_by="AidAsset.id")
    releases = db.relationship("AidRelease", back_populates="aid", cascade="all, delete-orphan")


class AidPayment(db.Model):
    """Versement d'un dossier (négatif pour un reversement) ; lié à un virement du relevé quand il en vient
    (rattachement, AG3.b), saisi à la main sinon (compensation, retenue)."""
    __tablename__ = "aid_payments"

    id = db.Column(db.Integer, primary_key=True)
    aid_id = db.Column(db.Integer, db.ForeignKey("aids.id", ondelete="CASCADE"), nullable=False, index=True)
    paid_on = db.Column(db.Date, nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False)
    kind = db.Column(db.String(12), nullable=False, default="other")
    bank_transaction_id = db.Column(db.Integer, db.ForeignKey("bank_transactions.id", ondelete="SET NULL"), index=True)
    note = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    aid = db.relationship("Aid", back_populates="payments")
    bank_transaction = db.relationship("BankTransaction")


AID_ACCRUAL_STATUSES = {"posted": "Passée", "dismissed": "Écartée"}


class AidAccrual(db.Model):
    """Décision de clôture sur un dossier pour un exercice (lot AG3.c) : produit à recevoir (441) ou constaté d'avance
    (487) passé avec son montant et, s'il diffère du calcul, son motif ; ou proposition écartée avec un motif.
    L'écriture est une écriture d'inventaire (`source_ref` « aid:<id> » ou « aid-deferred:<id> ») : supprimée depuis
    la clôture, la proposition revient."""
    __tablename__ = "aid_accruals"
    __table_args__ = (db.UniqueConstraint("aid_id", "fiscal_year_id", name="uq_aid_accruals_aid_fy"),)

    id = db.Column(db.Integer, primary_key=True)
    aid_id = db.Column(db.Integer, db.ForeignKey("aids.id", ondelete="CASCADE"), nullable=False, index=True)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False)
    kind = db.Column(db.String(10), nullable=False, default="accrued")        # accrued (441) | deferred (487)
    proposed_cents = db.Column(db.Integer, nullable=False, default=0)
    amount_cents = db.Column(db.Integer)
    reason = db.Column(db.String(500))
    status = db.Column(db.String(10), nullable=False)
    journal_entry_id = db.Column(db.Integer, db.ForeignKey("journal_entries.id", ondelete="SET NULL"))
    user_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    aid = db.relationship("Aid", back_populates="accruals")
    journal_entry = db.relationship("JournalEntry")


class AidAsset(db.Model):
    """Immobilisation financée par une subvention d'investissement (lot AG3.d), avec le montant affecté."""
    __tablename__ = "aid_assets"
    __table_args__ = (db.UniqueConstraint("aid_id", "asset_id", name="uq_aid_assets_aid_asset"),)

    id = db.Column(db.Integer, primary_key=True)
    aid_id = db.Column(db.Integer, db.ForeignKey("aids.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id = db.Column(db.Integer, db.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    amount_cents = db.Column(db.Integer, nullable=False)

    aid = db.relationship("Aid", back_populates="assets")
    asset = db.relationship("Asset")


AID_RELEASE_KINDS = {"depreciation": "Au rythme de l'amortissement", "disposal": "Sortie de l'immobilisation",
                     "manual": "Saisie (bien non amortissable)"}


class AidRelease(db.Model):
    """Reprise d'une subvention d'investissement sur un exercice (lot AG3.d), figée quand elle est passée : D 139 /
    C 747 au dernier jour de l'exercice. Une reprise saisie (bien non amortissable, Q-P7) attend l'écriture avec son
    motif (`entry_id` vide)."""
    __tablename__ = "aid_releases"

    id = db.Column(db.Integer, primary_key=True)
    aid_id = db.Column(db.Integer, db.ForeignKey("aids.id", ondelete="CASCADE"), nullable=False, index=True)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id = db.Column(db.Integer, db.ForeignKey("assets.id", ondelete="SET NULL"))
    kind = db.Column(db.String(12), nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(500))
    entry_id = db.Column(db.Integer, db.ForeignKey("journal_entries.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    aid = db.relationship("Aid", back_populates="releases")
    asset = db.relationship("Asset")
    fiscal_year = db.relationship("FiscalYear")


class CapPublished(db.Model):
    """Aides PAC publiées par l'ASP pour un SIREN et une année (lot AG3.e), lues dans Lexicon (jeu
    `cap_beneficiaries`) et gardées en cache dans l'instance : jamais additionnées entre années, jamais versionnées
    ni journalisées."""
    __tablename__ = "cap_published"
    __table_args__ = (db.UniqueConstraint("siren", "year", name="uq_cap_published_siren_year"),)

    id = db.Column(db.Integer, primary_key=True)
    siren = db.Column(db.String(9), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    feaga_cents = db.Column(db.Integer, nullable=False, default=0)
    feader_cents = db.Column(db.Integer, nullable=False, default=0)
    cofinanced_cents = db.Column(db.Integer, nullable=False, default=0)
    total_cents = db.Column(db.Integer, nullable=False, default=0)
    fetched_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
