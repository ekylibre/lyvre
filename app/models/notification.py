from datetime import datetime

from app.extensions import db

NOTIFICATION_LEVELS = ("success", "info", "warning", "danger")


class Notification(db.Model):
    """Message adressé à un utilisateur de l'instance (base de l'instance).

    `user_id` désigne un utilisateur de la méta-base (pas de clé étrangère entre bases) ;
    NULL = destiné à tous les utilisateurs de l'instance (job lancé hors requête).
    Créée à la fin d'une tâche en arrière-plan (`job_id`), lue par l'API /api/v1/notifications.
    """
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=True, index=True)
    kind = db.Column(db.String(40), nullable=False)          # job_done | job_failed
    level = db.Column(db.String(10), nullable=False, default="info")
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text)
    url = db.Column(db.String(300))                           # écran de la SPA concerné
    job_id = db.Column(db.Integer, db.ForeignKey("sync_jobs.id", ondelete="SET NULL"), nullable=True,
                       index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    read_at = db.Column(db.DateTime)

    @property
    def is_read(self):
        return self.read_at is not None

    def __repr__(self):
        return f"<Notification {self.id} {self.kind} user={self.user_id}>"
