from datetime import datetime
from app.extensions import db


class ReportAsset(db.Model):
    """Photo du rapport d'activité, rattachée à un exercice et un emplacement.

    Fichier stocké sous ``instance/uploads/report/<fiscal_year_id>/``.
    """
    __tablename__ = "report_assets"

    id = db.Column(db.Integer, primary_key=True)
    fiscal_year_id = db.Column(
        db.Integer,
        db.ForeignKey("fiscal_years.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    slot = db.Column(db.String(50), nullable=False)   # cover, section_impact…
    path = db.Column(db.String(300), nullable=False)
    caption = db.Column(db.String(300))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    fiscal_year = db.relationship("FiscalYear")

    def __repr__(self):
        return f"<ReportAsset fy={self.fiscal_year_id} {self.slot}>"
