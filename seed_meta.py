"""Bootstrap the meta database.

Creates the meta tables (users + instances) if needed, then ensures:
 - one admin user exists (from ADMIN_EMAIL/ADMIN_PASSWORD env vars), and
 - one default instance points to the existing tenant database.

Idempotent: running twice does not duplicate rows.
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import inspect, text  # noqa: E402

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Instance, User  # noqa: E402


def _ensure_column(table: str, column: str, ddl: str) -> None:
    """Add ``column`` to ``table`` of a pre-existing meta database.

    ``db.create_all`` only creates missing tables, never ALTERs existing ones,
    so meta databases created before the column was introduced need this
    lightweight, idempotent migration.
    """
    engine = db.engines.get("meta") or db.engine
    inspector = inspect(engine)
    if table not in inspector.get_table_names():
        return  # create_all will build it with the column
    if column in {col["name"] for col in inspector.get_columns(table)}:
        return
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
    print(f"Colonne {table}.{column} ajoutée.")


def _ensure_instance_chart_column() -> None:
    _ensure_column("instances", "chart", "VARCHAR(20) NOT NULL DEFAULT 'asso'")


def _ensure_instance_bookkeeping_column() -> None:
    _ensure_column("instances", "bookkeeping", "VARCHAR(10) NOT NULL DEFAULT 'double'")


def _ensure_user_preferences_column() -> None:
    _ensure_column("users", "preferences", "TEXT NOT NULL DEFAULT '{}'")


DEFAULT_ADMIN_EMAIL = "admin@local"
DEFAULT_ADMIN_PASSWORD = "admin"
DEFAULT_INSTANCE_SLUG = "seconde-nature"
DEFAULT_INSTANCE_LABEL = "Seconde Nature"
DEFAULT_INSTANCE_URL = "sqlite:///seconde-nature.db"


def _default_instance_chart() -> str:
    """Chart of the default instance: the one already loaded in the tenant
    database, else $DEFAULT_INSTANCE_CHART, else "asso" (same rule as
    seed_accounts.resolve_chart, which runs first in the Docker entrypoint)."""
    from seed_accounts import resolve_chart

    codes = []
    if "accounts" in inspect(db.engine).get_table_names():
        codes = [code for (code,) in db.session.execute(text("SELECT code FROM accounts"))]
    return resolve_chart(None, codes, os.environ.get("DEFAULT_INSTANCE_CHART"))


def _backfill_memberships() -> None:
    """Reprise des accès lors de la création de `instance_memberships` (une seule fois) :
    chaque utilisateur garde l'accès à chaque instance qu'il voyait jusque-là (toutes),
    avec le rôle administrateur s'il était administrateur global, trésorier sinon.
    Ne repasse jamais ensuite : un accès retiré n'est pas recréé au démarrage suivant."""
    from app.models import InstanceMembership

    users = db.session.query(User).all()
    instances = db.session.query(Instance).all()
    for user in users:
        for instance in instances:
            db.session.add(InstanceMembership(user_id=user.id, instance_id=instance.id,
                                              role="admin" if user.is_admin else "treasurer"))
    print(f"Accès repris : {len(users)} utilisateur(s) × {len(instances)} instance(s).")


def main() -> int:
    app = create_app()
    with app.app_context():
        # Create meta tables (the memberships backfill runs only when its table is new).
        memberships_existed = "instance_memberships" in inspect(db.engines["meta"]).get_table_names()
        db.create_all(bind_key=["meta"])
        _ensure_instance_chart_column()
        _ensure_instance_bookkeeping_column()
        _ensure_user_preferences_column()

        admin_email = (os.environ.get("ADMIN_EMAIL") or DEFAULT_ADMIN_EMAIL).strip().lower()
        admin_password = os.environ.get("ADMIN_PASSWORD") or DEFAULT_ADMIN_PASSWORD

        user = db.session.query(User).filter(User.email == admin_email).first()
        if user is None:
            user = User(
                email=admin_email,
                full_name="Administrateur",
                is_admin=True,
                is_active=True,
            )
            user.set_password(admin_password)
            db.session.add(user)
            print(f"Admin user created: {admin_email}")
        else:
            print(f"Admin user already exists: {admin_email}")

        instance_url = os.environ.get("DEFAULT_INSTANCE_URL", DEFAULT_INSTANCE_URL)
        instance_slug = os.environ.get("DEFAULT_INSTANCE_SLUG", DEFAULT_INSTANCE_SLUG)
        instance_label = os.environ.get("DEFAULT_INSTANCE_LABEL", DEFAULT_INSTANCE_LABEL)

        existing = db.session.query(Instance).filter(Instance.slug == instance_slug).first()
        if existing is None:
            chart = _default_instance_chart()
            instance = Instance(
                slug=instance_slug,
                label=instance_label,
                database_url=instance_url,
                chart=chart,
                is_active=True,
            )
            db.session.add(instance)
            print(f"Default instance created: {instance_slug} → {instance_url} (plan {chart})")
        else:
            print(f"Default instance already exists: {instance_slug}")

        db.session.flush()
        if not memberships_existed:
            _backfill_memberships()
        db.session.commit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
