from datetime import datetime
from app.extensions import db


class TaskType(db.Model):
    """Type de tâche paramétrable pour la saisie des temps de travaux.

    Le taux horaire est stocké en centimes entiers (convention du projet) :
    25 €/h -> ``hourly_rate_cents = 2500``.
    """
    __tablename__ = "task_types"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    hourly_rate_cents = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(
        db.Boolean, nullable=False, default=True, server_default="true"
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    work_times = db.relationship("WorkTime", back_populates="task_type", lazy="dynamic")

    def __repr__(self):
        return f"<TaskType {self.name}>"
