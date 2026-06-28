from datetime import datetime
from app.extensions import db


class ReportContent(db.Model):
    """Bloc narratif éditable du rapport d'activité, par exercice.

    Texte rédigé à la main (édito, rapport moral, intros de section,
    perspectives…), identifié par `block_key` et rattaché à un exercice.
    Pas de FK vers `users` (table sur le bind `meta`, hors base tenant).
    """
    __tablename__ = "report_contents"
    __table_args__ = (
        db.UniqueConstraint(
            "fiscal_year_id", "block_key", name="uq_report_content"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    fiscal_year_id = db.Column(
        db.Integer,
        db.ForeignKey("fiscal_years.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    block_key = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(200))
    body_html = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by_user_id = db.Column(db.Integer, nullable=True)

    fiscal_year = db.relationship("FiscalYear")

    def __repr__(self):
        return f"<ReportContent fy={self.fiscal_year_id} {self.block_key}>"
