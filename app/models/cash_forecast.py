from datetime import datetime

from app.extensions import db


class CashForecastItem(db.Model):
    """Encaissement (montant positif) ou décaissement (négatif) attendu, saisi à la main pour le
    prévisionnel de trésorerie ; répété chaque mois jusqu'à `repeat_monthly_until` s'il est renseigné."""
    __tablename__ = "cash_forecast_items"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    label = db.Column(db.String(200), nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False)
    bank_account_id = db.Column(db.Integer, db.ForeignKey("bank_accounts.id", ondelete="SET NULL"))
    repeat_monthly_until = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    bank_account = db.relationship("BankAccount")
