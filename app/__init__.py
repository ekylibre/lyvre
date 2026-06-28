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

    # Import models so Alembic can detect them
    from . import models  # noqa: F401

    from .tenant import register_tenant_hooks
    register_tenant_hooks(app)

    from .views.dashboard import bp as dashboard_bp
    from .views.accounts import bp as accounts_bp
    from .views.fiscal_years import bp as fiscal_years_bp
    from .views.journals import bp as journals_bp
    from .views.bank_accounts import bp as bank_accounts_bp
    from .views.entries import bp as entries_bp
    from .views.imports import bp as imports_bp
    from .views.reconciliation import bp as reconciliation_bp
    from .views.reports import bp as reports_bp
    from .views.auth import bp as auth_bp
    from .views.entities import bp as entities_bp
    from .views.rules import bp as rules_bp
    from .views.work_times import bp as work_times_bp
    from .views.impact import bp as impact_bp
    from .views.activity_report import bp as activity_report_bp
    from .views.payouts import bp as payouts_bp
    from .views.orders import bp as orders_bp
    from .views.customer_invoices import bp as customer_invoices_bp
    from .views.users import bp as users_bp
    from .views.instances import bp as instances_bp
    from .views.external_connections import bp as external_connections_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(accounts_bp)
    app.register_blueprint(fiscal_years_bp)
    app.register_blueprint(journals_bp)
    app.register_blueprint(bank_accounts_bp)
    app.register_blueprint(entries_bp)
    app.register_blueprint(imports_bp)
    app.register_blueprint(reconciliation_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(entities_bp)
    app.register_blueprint(rules_bp)
    app.register_blueprint(work_times_bp)
    app.register_blueprint(impact_bp)
    app.register_blueprint(activity_report_bp)
    app.register_blueprint(payouts_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(customer_invoices_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(instances_bp)
    app.register_blueprint(external_connections_bp)

    _register_template_filters(app)

    return app


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

    @app.template_filter("from_json")
    def from_json_filter(value):
        if not value:
            return {}
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return {}
