"""Abonnement d'un utilisateur au résumé du lundi de l'échéancier (lot AG9a.d, design § 7), dans la base de
l'instance : un utilisateur suit chaque exploitation séparément.

Sans ligne, un utilisateur qui écrit sur l'instance (administrateur ou trésorier) est abonné (Q-E4) ; un
administrateur global sans rôle sur l'instance ne l'est que s'il s'abonne. `last_sent_week` (« 2026-W45 ») rend
l'envoi idempotent. `ical_token` sert à l'export iCal (lot AG9a.e).
"""
from datetime import datetime

from app.extensions import db


class AgendaSubscription(db.Model):
    __tablename__ = "agenda_subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False, unique=True)   # utilisateur de la méta-base
    subscribed = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    last_sent_week = db.Column(db.String(8))
    last_sent_at = db.Column(db.DateTime)
    ical_token = db.Column(db.String(64), unique=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
