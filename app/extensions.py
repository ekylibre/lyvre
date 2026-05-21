from flask import g, current_app, has_app_context
from flask_sqlalchemy import SQLAlchemy
from flask_sqlalchemy.session import Session as FSASession
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect


class MultiTenantSession(FSASession):
    """Session class that routes queries to the right engine.

    - Models with `__bind_key__ = 'meta'` always hit the meta engine.
    - Other models hit `g.tenant_engine` if set (per-request tenant DB),
      else fall back to the default engine (used by seed scripts).
    """

    def get_bind(self, mapper=None, clause=None, bind=None, **kw):
        if bind is not None:
            return bind
        if mapper is not None:
            bind_key = None
            try:
                for klass in mapper.class_.__mro__:
                    bind_key = klass.__dict__.get("__bind_key__")
                    if bind_key is not None:
                        break
            except (AttributeError, TypeError):
                bind_key = None
            if bind_key:
                return current_app.extensions["sqlalchemy"].engines[bind_key]
        if has_app_context() and getattr(g, "tenant_engine", None) is not None:
            return g.tenant_engine
        return current_app.extensions["sqlalchemy"].engines[None]


db = SQLAlchemy(session_options={"class_": MultiTenantSession})
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()
