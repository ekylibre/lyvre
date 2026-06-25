import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'seconde-nature.db'}"
    )
    META_DATABASE_URL = os.environ.get(
        "META_DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'meta.db'}"
    )
    SQLALCHEMY_BINDS = {"meta": META_DATABASE_URL}
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True
    STANCER_SECRET_KEY = os.environ.get("STANCER_SECRET_KEY", "")
    STANCER_MODE = os.environ.get("STANCER_MODE", "live")  # "live" or "test"
    ODOO_URL = os.environ.get("ODOO_URL", "")
    ODOO_DB = os.environ.get("ODOO_DB", "")
    ODOO_USERNAME = os.environ.get("ODOO_USERNAME", "")
    ODOO_API_KEY = os.environ.get("ODOO_API_KEY", "")
    HELLOASSO_CLIENT_ID = os.environ.get("HELLOASSO_CLIENT_ID", "")
    HELLOASSO_CLIENT_SECRET = os.environ.get("HELLOASSO_CLIENT_SECRET", "")
    HELLOASSO_ORG_SLUG = os.environ.get("HELLOASSO_ORG_SLUG", "")
    HELLOASSO_API_BASE = os.environ.get(
        "HELLOASSO_API_BASE", "https://api.helloasso.com"
    )

    # SMTP / Flask-Mail (relance des adhérents)
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "587"))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() in ("1", "true", "yes")
    MAIL_USE_SSL = os.environ.get("MAIL_USE_SSL", "false").lower() in ("1", "true", "yes")
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "")


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
