from datetime import datetime
from app.extensions import db


class ReportArchive(db.Model):
    """Version figée (PDF) du rapport d'activité d'un exercice.

    Les chiffres du rapport sont *live* (ils évoluent) ; archiver fige un PDF
    consultable d'une version publiée. Versionné par exercice (`version`
    incrémental). Fichier stocké sous
    ``instance/uploads/report/<fiscal_year_id>/archives/v<n>.pdf``.
    """
    __tablename__ = "report_archives"
    __table_args__ = (
        db.UniqueConstraint("fiscal_year_id", "version", name="uq_report_archive"),
    )

    id = db.Column(db.Integer, primary_key=True)
    fiscal_year_id = db.Column(
        db.Integer,
        db.ForeignKey("fiscal_years.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version = db.Column(db.Integer, nullable=False)
    label = db.Column(db.String(200))
    path = db.Column(db.String(300), nullable=False)
    prorata = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by_user_id = db.Column(db.Integer, nullable=True)

    fiscal_year = db.relationship("FiscalYear")

    def __repr__(self):
        return f"<ReportArchive fy={self.fiscal_year_id} v{self.version}>"
