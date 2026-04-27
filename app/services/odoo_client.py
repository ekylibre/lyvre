"""Client XML-RPC Odoo.

Utilise les endpoints standard :
- /xmlrpc/2/common  : authenticate(db, login, password) → uid
- /xmlrpc/2/object  : execute_kw(db, uid, password, model, method, args, kwargs)

L'API key (depuis Odoo 14) est passée à la place du password.
"""
from urllib.parse import urljoin
from xmlrpc.client import ServerProxy

from flask import current_app


class OdooConfigError(RuntimeError):
    pass


class OdooClient:
    def __init__(self, url, db, username, password):
        self.url = url.rstrip("/") + "/"
        self.db = db
        self.username = username
        self.password = password
        self._common = ServerProxy(urljoin(self.url, "xmlrpc/2/common"), allow_none=True)
        self._object = ServerProxy(urljoin(self.url, "xmlrpc/2/object"), allow_none=True)
        self._uid = None

    @property
    def uid(self):
        if self._uid is None:
            uid = self._common.authenticate(self.db, self.username, self.password, {})
            if not uid:
                raise OdooConfigError(
                    "Authentification Odoo refusée — vérifiez ODOO_DB / "
                    "ODOO_USERNAME / ODOO_API_KEY."
                )
            self._uid = uid
        return self._uid

    def execute_kw(self, model, method, args=None, kwargs=None):
        return self._object.execute_kw(
            self.db, self.uid, self.password,
            model, method, args or [], kwargs or {},
        )

    def search_read(self, model, domain=None, fields=None, limit=None, offset=0, order=None):
        kwargs = {"offset": offset}
        if fields is not None:
            kwargs["fields"] = fields
        if limit is not None:
            kwargs["limit"] = limit
        if order is not None:
            kwargs["order"] = order
        return self.execute_kw(model, "search_read", [domain or []], kwargs)


def from_app_config():
    """Construit un OdooClient à partir de la config Flask."""
    url = current_app.config.get("ODOO_URL")
    db = current_app.config.get("ODOO_DB")
    username = current_app.config.get("ODOO_USERNAME")
    password = current_app.config.get("ODOO_API_KEY")
    missing = [k for k, v in (
        ("ODOO_URL", url), ("ODOO_DB", db),
        ("ODOO_USERNAME", username), ("ODOO_API_KEY", password),
    ) if not v]
    if missing:
        raise OdooConfigError(
            "Configuration Odoo incomplète : " + ", ".join(missing)
            + " — à définir dans .env"
        )
    return OdooClient(url, db, username, password)
