from app.extensions import db

CURSOR_QONTO_SUPPLIER_INVOICES = "qonto_supplier_invoices"


class SyncCursor(db.Model):
    """Curseur d'une synchronisation à l'échelle de l'organisation (pas d'un compte)."""

    __tablename__ = "sync_cursors"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    # Date de début du premier passage ; NULL = début de l'exercice en cours.
    sync_from = db.Column(db.Date)
    # Début (UTC) de la dernière synchronisation réussie ; NULL = jamais.
    synced_at = db.Column(db.DateTime)

    def __repr__(self):
        return f"<SyncCursor {self.key} {self.synced_at}>"
