from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "users"
    __bind_key__ = "meta"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(200), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(200))
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    # Mot de passe initial ou fixé par un administrateur : à changer à la prochaine connexion.
    must_change_password = db.Column(db.Boolean, default=False, nullable=False, server_default=db.false())
    last_login_at = db.Column(db.DateTime, nullable=True)
    # Préférences d'interface (JSON : thème, colonnes masquées…), cf. app/api/session.py.
    preferences = db.Column(db.Text, nullable=False, default="{}", server_default="{}")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method="pbkdf2:sha256")

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.email}>"
