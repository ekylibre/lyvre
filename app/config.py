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
    INTEGRATIONS_ENV_FALLBACK = False
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

    # Site Jekyll (import optionnel des contenus _data/*.yml dans le rapport).
    # Accepte soit un chemin local vers le dossier `_data`, soit une URL GitHub
    # (le dépôt est lu à distance → fonctionne hors localhost, sans clone).
    SITE_DATA_PATH = os.environ.get(
        "SITE_DATA_PATH",
        "https://github.com/asso-seconde-nature/seconde-nature.github.io/tree/main/",
    )

    # Rapport d'activité : répartition des trimestres éco à cheval sur l'exercice.
    # False = rattachement indivisible par date de début (défaut design) ;
    # True = pro-rata des jours. Surcharge ponctuelle via ?prorata=1.
    ECO_PRORATA = os.environ.get("ECO_PRORATA", "false").lower() in ("1", "true", "yes")

    # Adresse publique de Lyvre (liens envoyés par e-mail : mot de passe oublié). En production,
    # obligatoire pour ces liens (jamais l'en-tête Host de la requête) ; en développement, repli sur
    # l'adresse de la requête.
    APP_BASE_URL = os.environ.get("APP_BASE_URL", "")

    # SMTP / Flask-Mail (relance des adhérents, mot de passe oublié)
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "587"))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() in ("1", "true", "yes")
    MAIL_USE_SSL = os.environ.get("MAIL_USE_SSL", "false").lower() in ("1", "true", "yes")
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "")

    # Lexicon (OSFarm, lot AG3.e) : aides PAC publiées par l'ASP, lues par SIREN (route réservée aux membres). Clé du
    # serveur (`Authorization: Bearer`), jamais envoyée au navigateur ; vide : contrôle des aides publiées masqué.
    LEXICON_API_KEY = os.environ.get("LEXICON_API_KEY", "")
    LEXICON_URL = os.environ.get("LEXICON_URL", "https://lexicon.osfarm.org")

    # API Sirene v4 (INSEE) : pré-remplissage de la Structure et des tiers. Clé du serveur (en-tête
    # X-INSEE-Api-Key-Integration), jamais envoyée au navigateur ; vide : fonctions Sirene masquées.
    SIRENE_API_URL = os.environ.get("SIRENE_API_URL") or "https://api.insee.fr/api-sirene/4"
    SIRENE_API_KEY = os.environ.get("SIRENE_API_KEY", "")

    # Qonto (API Business, clé API) : repli global, surchargé par Configuration › Intégrations.
    # Noms alternatifs acceptés : QONTO_API_ID / QONTO_API_SECRET.
    QONTO_LOGIN = os.environ.get("QONTO_LOGIN") or os.environ.get("QONTO_API_ID", "")
    QONTO_SECRET_KEY = os.environ.get("QONTO_SECRET_KEY") or os.environ.get("QONTO_API_SECRET", "")
    QONTO_STAGING_TOKEN = os.environ.get("QONTO_STAGING_TOKEN", "")

    # Brevo : repli de développement seulement (INTEGRATIONS_ENV_FALLBACK) ; en production, la clé se
    # saisit dans Configuration › Intégrations.
    BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")


def _flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    return default if value is None else value.strip().lower() in ("1", "true", "yes", "on")


class DevelopmentConfig(Config):
    DEBUG = True
    # Réglages d'intégration repris du .env quand l'instance n'en a pas (développement seulement :
    # ailleurs, seuls les réglages de l'instance font foi).
    INTEGRATIONS_ENV_FALLBACK = _flag("INTEGRATIONS_ENV_FALLBACK", True)


class ProductionConfig(Config):
    DEBUG = False


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
