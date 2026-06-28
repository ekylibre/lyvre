from datetime import datetime
from app.extensions import db


class MetricSnapshot(db.Model):
    """Valeur d'une métrique pour une période, pour les sources non recalculables.

    On n'y stocke QUE ce qu'on ne sait pas recalculer à la volée : métriques des
    API externes (GA4, Facebook) et saisies manuelles (Vinted, groupe Facebook).
    Les métriques internes (éco/social) et l'impact environnemental sont calculés
    en direct depuis les tables existantes — jamais dupliqués ici.

    Clé d'unicité ``(source, metric_key, period_start, granularity)`` → upsert
    idempotent (re-synchro et corrections de saisie sans doublon).
    """
    __tablename__ = "metric_snapshots"
    __table_args__ = (
        db.UniqueConstraint(
            "source", "metric_key", "period_start", "granularity",
            name="uq_metric_snapshot_key",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(30), nullable=False, index=True)
    metric_key = db.Column(db.String(60), nullable=False, index=True)
    period_start = db.Column(db.Date, nullable=False, index=True)
    granularity = db.Column(
        db.String(10), nullable=False, default="month", server_default="month"
    )
    value = db.Column(db.Numeric(18, 4), nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    is_manual = db.Column(
        db.Boolean, nullable=False, default=False, server_default="false"
    )
    captured_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Pas de FK : la table `users` est sur le bind `meta`, pas dans la base tenant.
    entered_by_user_id = db.Column(db.Integer, nullable=True)
    note = db.Column(db.Text)

    def __repr__(self):
        return f"<MetricSnapshot {self.source}.{self.metric_key} {self.period_start}>"
