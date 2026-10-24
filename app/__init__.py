import os
from flask import Flask
from .config import config
from .extensions import db, migrate, login_manager, csrf


def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config.get(config_name, config["default"]))
    app.config.setdefault("MAX_CONTENT_LENGTH", 500 * 1024 * 1024)

    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Veuillez vous connecter."
    # API JSON : pas de redirection vers la page de connexion, mais une 401
    # (convertie en JSON par app.api.register_api).
    login_manager.blueprint_login_views["api"] = None

    # Import models so Alembic can detect them
    from . import models  # noqa: F401
    from .services import ledger_guard  # noqa: F401  (garde et historique des écritures, lot F1)

    from .tenant import register_tenant_hooks
    register_tenant_hooks(app)

    from .views.reports import bp as reports_bp
    from .views.auth import bp as auth_bp
    from .views.entities import bp as entities_bp
    from .views.impact import bp as impact_bp
    from .views.activity_report import bp as activity_report_bp
    from .views.instances import bp as instances_bp
    from .views.fec import bp as fec_bp
    from .views.purchases import bp as purchases_bp
    from .views.exports import bp as exports_bp
    from .views.integrations import legacy_bp as external_connections_bp

    # Pages migrées vers la SPA : avant les blueprints (un doublon d'endpoint échoue).
    from .spa import register_spa
    register_spa(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(entities_bp)
    app.register_blueprint(impact_bp)
    app.register_blueprint(activity_report_bp)
    app.register_blueprint(instances_bp)
    app.register_blueprint(fec_bp)
    app.register_blueprint(purchases_bp)
    app.register_blueprint(exports_bp)
    app.register_blueprint(external_connections_bp)

    _register_template_filters(app)

    from .frontend import register_frontend
    register_frontend(app)

    from .api import register_api
    register_api(app)

    return app


def _register_template_filters(app):
    # Gabarits du rapport d'activité (PDF, exports).
    @app.template_filter("euros")
    def euros_filter(cents):
        if cents is None:
            return "0,00 €"
        return f"{cents / 100:,.2f} €".replace(",", " ").replace(".", ",")
