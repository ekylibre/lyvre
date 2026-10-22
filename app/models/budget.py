from app.extensions import db


class BudgetLine(db.Model):
    """Montant prévu d'un compte de charge ou de produit (classe 6 ou 7) sur un exercice, global
    (`project_id` NULL) ou pour un projet. `month` : rang du mois dans l'exercice (1 = premier
    mois) ; NULL = montant annuel, réparti par douzièmes à l'affichage. Le compte peut être un
    regroupement (60, 64…) : le réalisé se calcule alors par préfixe."""
    __tablename__ = "budget_lines"
    __table_args__ = (db.Index("ix_budget_lines_scope", "fiscal_year_id", "project_id"),)

    id = db.Column(db.Integer, primary_key=True)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"))
    month = db.Column(db.Integer)
    amount_cents = db.Column(db.Integer, nullable=False, default=0)

    account = db.relationship("Account")
