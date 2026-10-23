from datetime import datetime

from app.extensions import db


class Instance(db.Model):
    __tablename__ = "instances"
    __bind_key__ = "meta"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(50), unique=True, nullable=False, index=True)
    label = db.Column(db.String(200), nullable=False)
    database_url = db.Column(db.String(500), nullable=False)
    # Plan comptable de l'instance ("asso", "sci", …). Pilote l'affichage des
    # menus (voir app/menu_config.py).
    chart = db.Column(db.String(20), nullable=False, default="asso", server_default="asso")
    # Mode de tenue (lot D, D19) : "double" (partie double) ou "simple" (recettes et dépenses,
    # associations seulement) ; pilote menus et fonctions comme le plan comptable.
    bookkeeping = db.Column(db.String(10), nullable=False, default="double", server_default="double")
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Instance {self.slug}>"
