"""Relevé de compte mensuel (PDF) d'un compte bancaire : récupéré de Qonto ou déposé à la main
(claudedocs/design_releves_qonto.md § 2). Un relevé par compte et par mois ; jamais supprimé depuis
l'interface. Le fichier est rangé dans le dossier de l'instance (`file_path`, relatif)."""
from datetime import datetime

from app.extensions import db

SOURCE_QONTO = "qonto"
SOURCE_UPLOAD = "upload"


class BankStatement(db.Model):
    __tablename__ = "bank_statements"
    __table_args__ = (db.UniqueConstraint("bank_account_id", "period", name="uq_bank_statements_period"),)

    id = db.Column(db.Integer, primary_key=True)
    bank_account_id = db.Column(db.Integer, db.ForeignKey("bank_accounts.id", ondelete="RESTRICT"), nullable=False,
                                index=True)
    period = db.Column(db.Date, nullable=False)  # 1er jour du mois du relevé
    source = db.Column(db.String(10), nullable=False, default=SOURCE_QONTO)
    qonto_id = db.Column(db.String(36))
    file_path = db.Column(db.String(255), nullable=False)
    file_name = db.Column(db.String(255))
    file_size = db.Column(db.Integer, nullable=False, default=0)
    sha256 = db.Column(db.String(64), nullable=False)
    fetched_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    replaced_at = db.Column(db.DateTime)
    user_id = db.Column(db.Integer)

    bank_account = db.relationship("BankAccount", backref=db.backref("statements", lazy="dynamic"))

    def __repr__(self):
        return f"<BankStatement {self.bank_account_id} {self.period:%Y-%m}>"
