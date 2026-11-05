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
# Jamais d'appel à l'INSEE depuis les tests : clé vide (les tests Sirene simulent les réponses).
os.environ["SIRENE_API_KEY"] = ""
os.environ["SIRENE_API_URL"] = "https://sirene.invalid/api-sirene/4"
os.environ["BREVO_API_KEY"] = ""  # jamais d'appel au compte Brevo réel depuis les tests

import pytest  # noqa: E402

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402


@pytest.fixture()
def app():
    app = create_app("development")
    app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        ANTHROPIC_API_KEY="",          # clé du serveur absente des tests (Assistant Claude, AG9b)
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


ALL_INTEGRATIONS = '{"enabled": ["documenso", "facebook", "ga4", "helloasso", "odoo", "qonto", "smtp", "stancer"], "dismissed": []}'


def _test_instance(**fields):
    """Instance « test » (base de test), créée une fois par test et sélectionnée dans le contexte
    d'application comme le fait une requête (`g.current_instance`) : les services qui lisent les
    interrupteurs d'intégration la trouvent hors requête. Intégrations toutes activées."""
    from flask import g

    from app.models import Instance

    instance = db.session.query(Instance).filter_by(slug="test").first()
    if instance is None:
        instance = Instance(slug="test", label="Test", database_url=os.environ["DATABASE_URL"],
                            integrations=ALL_INTEGRATIONS, **fields)
        db.session.add(instance)
        db.session.commit()
    g.current_instance = instance
    return instance


@pytest.fixture()
def instance(app):
    """Instance de test sélectionnée (intégrations activées), sans utilisateur connecté."""
    return _test_instance()


@pytest.fixture()
def login_as(app):
    """Client authentifié (utilisateur méta + instance pointant sur la base de test).

    Usage : ``client = login_as(is_admin=True)`` ; ``login_as(role="accountant")`` pour un
    expert-comptable ; ``role=None`` : connecté sans accès à l'instance.
    """
    from app.models import InstanceMembership, User

    def _login(is_admin=False, role="treasurer"):
        user = User(email=f"{'admin' if is_admin else 'user'}@example.org", is_admin=is_admin)
        user.set_password("x")
        instance = _test_instance()
        db.session.add(user)
        db.session.flush()
        if not is_admin and role:
            # Accès à l'instance de test (sans rôle : aucun accès, cf. app/access.py).
            db.session.add(InstanceMembership(user_id=user.id, instance_id=instance.id, role=role))
        db.session.commit()
        client = app.test_client()
        with client.session_transaction() as sess:
            sess["_user_id"] = str(user.id)
            sess["_fresh"] = True
            sess["instance_id"] = instance.id
        return client

    return _login


@pytest.fixture()
def closing_ready():
    """Décide les étapes 1 à 5 de l'assistant de clôture (ignorées avec motif) : la clôture
    provisoire devient possible. Usage : ``closing_ready(fy)``."""
    from app.models import ClosingStep
    from app.services.closing import DECIDED_BEFORE_CLOSE

    def _ready(fy):
        for step in DECIDED_BEFORE_CLOSE:
            db.session.add(ClosingStep(fiscal_year_id=fy.id, step=step, state="skipped", note="test"))
        db.session.commit()

    return _ready
