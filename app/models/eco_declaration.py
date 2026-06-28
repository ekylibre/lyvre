from datetime import datetime
from app.extensions import db


class EcoDeclaration(db.Model):
    """Tonnages déclarés aux éco-organismes (Ecomaison, Ecologic), par trimestre.

    Issu de la déclaration éco-organismes : tonnage `entrant_t` (collecté) vs
    `sortant_t` (réemployé), par matière, plus le financement perçu. Sert de base
    *autoritaire* à la section impact du rapport d'activité.
    Tonnages en tonnes (`Numeric(10,3)`), financement en centimes.
    """
    __tablename__ = "eco_declarations"
    __table_args__ = (
        db.UniqueConstraint(
            "organism", "material", "quarter_label", name="uq_eco_declaration"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    organism = db.Column(db.String(20), nullable=False, index=True)   # ecomaison / ecologic
    material = db.Column(db.String(40), nullable=False)               # Meubles, D3E, Sports…
    quarter_label = db.Column(db.String(10), nullable=False)          # « T2 2025 »
    period_start = db.Column(db.Date, nullable=False, index=True)     # 1er jour du trimestre
    entrant_t = db.Column(db.Numeric(10, 3), nullable=False, default=0)
    sortant_t = db.Column(db.Numeric(10, 3), nullable=False, default=0)
    financing_cents = db.Column(db.Integer, nullable=False, default=0)
    source = db.Column(db.String(10), nullable=False, default="import",
                       server_default="import")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<EcoDeclaration {self.organism}/{self.material} {self.quarter_label}>"
