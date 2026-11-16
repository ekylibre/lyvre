from app.extensions import db


class SimpleCategory(db.Model):
    """Catégorie de recette ou de dépense de la comptabilité simplifiée (lot D, D21) : libellé
    sans vocabulaire comptable, rattaché à un compte du plan associatif (l'écriture générée l'utilise)."""
    __tablename__ = "simple_categories"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), unique=True, nullable=False)
    label = db.Column(db.String(120), nullable=False)
    kind = db.Column(db.String(8), nullable=False)          # income | expense
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)
    active = db.Column(db.Boolean, nullable=False, default=True)
    # Lot AG1.a : recette exclue du micro-BA (cessions, ICHN, primes d'équipement, entraide ; CGI art. 64 bis).
    excluded_from_micro = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    # Lot AG2.e : classe de taux du remboursement forfaitaire (high, low, excluded ; nul : à choisir).
    rfa_rate = db.Column(db.String(10))
    # Lot AG10.e : recette de vente directe à des particuliers sans facture (e-reporting B2C).
    direct_sale = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())

    account = db.relationship("Account")
