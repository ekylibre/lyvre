"""Configuration pytest : app Flask isolée sur une base SQLite temporaire.

Les variables d'environnement sont fixées **avant** l'import de l'application
pour que `app.config` lise une base jetable (jamais la base réelle).
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMPDIR = tempfile.mkdtemp(prefix="compta-asso-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMPDIR, 'test.db')}"
os.environ["META_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMPDIR, 'meta.db')}"
os.environ["FLASK_ENV"] = "development"
os.environ.setdefault("HELLOASSO_ORG_SLUG", "test-org")
os.environ.setdefault("MAIL_SERVER", "smtp.example.org")
os.environ.setdefault("MAIL_DEFAULT_SENDER", "noreply@example.org")

import pytest  # noqa: E402

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402


@pytest.fixture()
def app():
    app = create_app("development")
    app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
    )

    ctx = app.app_context()
    ctx.push()
    db.create_all()
    try:
        yield app
    finally:
        db.session.remove()
        db.drop_all()
        ctx.pop()


@pytest.fixture()
def session(app):
    return db.session
