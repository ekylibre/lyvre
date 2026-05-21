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

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Instance, User  # noqa: E402


DEFAULT_ADMIN_EMAIL = "admin@local"
DEFAULT_ADMIN_PASSWORD = "admin"
DEFAULT_INSTANCE_SLUG = "seconde-nature"
DEFAULT_INSTANCE_LABEL = "Seconde Nature"
DEFAULT_INSTANCE_URL = "sqlite:///seconde-nature.db"


def main() -> int:
    app = create_app()
    with app.app_context():
        # Create meta tables.
        db.create_all(bind_key=["meta"])

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
            instance = Instance(
                slug=instance_slug,
                label=instance_label,
                database_url=instance_url,
                is_active=True,
            )
            db.session.add(instance)
            print(f"Default instance created: {instance_slug} → {instance_url}")
        else:
            print(f"Default instance already exists: {instance_slug}")

        db.session.commit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
