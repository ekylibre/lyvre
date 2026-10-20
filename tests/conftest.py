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
        from app.tenant import clear_engine_cache

        db.session.remove()
        db.drop_all()
        # Les moteurs tenant sont mis en cache par id d'instance ; les ids repartent à 1
        # à chaque test (méta-base recréée) : un moteur d'un test précédent serait réutilisé.
        clear_engine_cache()
        ctx.pop()


@pytest.fixture()
def session(app):
    return db.session


@pytest.fixture()
def login_as(app):
    """Client authentifié (utilisateur méta + instance pointant sur la base de test).

    Usage : ``client = login_as(is_admin=True)``.
    """
    from app.models import Instance, User

    def _login(is_admin=False):
        user = User(email=f"{'admin' if is_admin else 'user'}@example.org", is_admin=is_admin)
        user.set_password("x")
        instance = Instance(slug="test", label="Test", database_url=os.environ["DATABASE_URL"])
        db.session.add_all([user, instance])
        db.session.commit()
        client = app.test_client()
        with client.session_transaction() as sess:
            sess["_user_id"] = str(user.id)
            sess["_fresh"] = True
            sess["instance_id"] = instance.id
        return client

    return _login
