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

    from .tenant import register_tenant_hooks
    register_tenant_hooks(app)

    from .views.bank_accounts import bp as bank_accounts_bp
    from .views.imports import bp as imports_bp
    from .views.reconciliation import bp as reconciliation_bp
    from .views.reports import bp as reports_bp
    from .views.auth import bp as auth_bp
    from .views.entities import bp as entities_bp
    from .views.impact import bp as impact_bp
    from .views.activity_report import bp as activity_report_bp
    from .views.payouts import bp as payouts_bp
    from .views.orders import bp as orders_bp
    from .views.customer_invoices import bp as customer_invoices_bp
    from .views.instances import bp as instances_bp
    from .views.purchases import bp as purchases_bp
    from .views.integrations import bp as integrations_bp, legacy_bp as external_connections_bp

    # Pages migrées vers la SPA : avant les blueprints (un doublon d'endpoint échoue).
    from .spa import register_spa
    register_spa(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(bank_accounts_bp)
    app.register_blueprint(imports_bp)
    app.register_blueprint(reconciliation_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(entities_bp)
    app.register_blueprint(impact_bp)
    app.register_blueprint(activity_report_bp)
    app.register_blueprint(payouts_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(customer_invoices_bp)
    app.register_blueprint(instances_bp)
    app.register_blueprint(purchases_bp)
    app.register_blueprint(integrations_bp)
    app.register_blueprint(external_connections_bp)

    _register_template_filters(app)
    _register_context_processors(app)

    from .frontend import register_frontend
    register_frontend(app)

    from .api import register_api
    register_api(app)

    return app


def _register_context_processors(app):
    from flask_login import current_user
    from .menu_config import build_nav
    from .tenant import current_chart

    from .services import external_config

    # "disabled" / "unconfigured" / None — used by integrations/_macros.html.
    app.jinja_env.globals["integration_state"] = external_config.unavailable_reason

    @app.context_processor
    def inject_nav_menus():
        is_admin = bool(getattr(current_user, "is_admin", False))
        return {"nav_menus": build_nav(chart=current_chart(), is_admin=is_admin)}


def _register_template_filters(app):
    import json

    @app.template_filter("euros")
    def euros_filter(cents):
        if cents is None:
            return "0,00 €"
        return f"{cents / 100:,.2f} €".replace(",", " ").replace(".", ",")

    @app.template_filter("abs_euros")
    def abs_euros_filter(cents):
        return euros_filter(abs(cents) if cents else 0)

    @app.template_filter("rate")
    def rate_filter(bp):
        from .services.catalog import format_rate
        return format_rate(bp)

    @app.template_filter("integration_label")
    def integration_label_filter(slug):
        from .services.external_config import SERVICE_LABELS
        return SERVICE_LABELS.get(slug, slug)

    @app.template_filter("local_dt")
    def local_dt_filter(value, fmt="%d/%m/%Y %H:%M"):
        """Naive UTC datetime (as stored) → Europe/Paris, formatted."""
        from datetime import timezone
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        if value is None:
            return ""
        try:
            tz = ZoneInfo("Europe/Paris")
        except ZoneInfoNotFoundError:
            tz = timezone.utc
        return value.replace(tzinfo=timezone.utc).astimezone(tz).strftime(fmt)

    @app.template_filter("from_json")
    def from_json_filter(value):
        if not value:
            return {}
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return {}
