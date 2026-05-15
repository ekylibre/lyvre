import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'compta.db'}"
    )
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


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
