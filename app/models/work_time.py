from datetime import datetime
from app.extensions import db


class WorkTime(db.Model):
    """Temps de travaux saisi pour un bénévole.

    ``hours`` est une valeur non monétaire (``Numeric(6, 2)``, ex. ``2.50``).
    La valorisation se calcule à la volée en centimes :
    ``round(hours * task_type.hourly_rate_cents)``.
    """
    __tablename__ = "work_times"

    id = db.Column(db.Integer, primary_key=True)
    entity_id = db.Column(
        db.Integer,
        db.ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_type_id = db.Column(
        db.Integer,
        db.ForeignKey("task_types.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    work_date = db.Column(db.Date, nullable=False, index=True)
    hours = db.Column(db.Numeric(6, 2), nullable=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    entity = db.relationship("Entity", back_populates="work_times")
    task_type = db.relationship("TaskType", back_populates="work_times")

    @property
    def valuation_cents(self):
        """Valorisation en centimes = heures × taux horaire (arrondi entier)."""
        if self.hours is None or self.task_type is None:
            return 0
        return int(round(float(self.hours) * self.task_type.hourly_rate_cents))

    def __repr__(self):
        return f"<WorkTime entity={self.entity_id} {self.work_date} {self.hours}h>"
