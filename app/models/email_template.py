from datetime import datetime
from app.extensions import db

# Gabarit par défaut de relance d'adhésion. Variables Jinja disponibles :
# {{ nom }}, {{ email }}, {{ date_anniversaire }}, {{ lien_helloasso }}.
MEMBERSHIP_REMINDER_KEY = "membership_reminder"

DEFAULT_REMINDER_SUBJECT = "Votre adhésion arrive à échéance"
DEFAULT_REMINDER_BODY = """\
<p>Bonjour {{ nom }},</p>

<p>Votre adhésion est arrivée à échéance le {{ date_anniversaire }}.</p>

<p>Pour continuer à soutenir l'association, vous pouvez renouveler votre
adhésion en quelques clics :</p>

<p><a href="{{ lien_helloasso }}">Renouveler mon adhésion</a></p>

<p>Merci pour votre soutien,<br>
L'équipe de l'association</p>
"""


class EmailTemplate(db.Model):
    __tablename__ = "email_templates"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    subject = db.Column(db.String(300), nullable=False, default="")
    body_html = db.Column(db.Text, nullable=False, default="")
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<EmailTemplate {self.key}>"

    @classmethod
    def get_or_default(cls, key):
        """Retourne le gabarit en base ou un objet par défaut non persisté."""
        tpl = cls.query.filter_by(key=key).first()
        if tpl is not None:
            return tpl
        if key == MEMBERSHIP_REMINDER_KEY:
            return cls(
                key=key,
                subject=DEFAULT_REMINDER_SUBJECT,
                body_html=DEFAULT_REMINDER_BODY,
            )
        return cls(key=key, subject="", body_html="")
