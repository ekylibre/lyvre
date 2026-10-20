"""Client HelloAsso API v5.

Auth : OAuth2 client_credentials sur /oauth2/token (token ~30 min).
Doc  : https://api.helloasso.com/v5/swagger/index.html
"""
import time

import requests


class HelloAssoConfigError(RuntimeError):
    pass


class HelloAssoClient:
    def __init__(self, client_id, client_secret, org_slug, api_base, timeout=30):
        self.timeout = timeout
        self.client_id = client_id
        self.client_secret = client_secret
        self.org_slug = org_slug
        self.api_base = api_base.rstrip("/")
        self._token = None
        self._token_expires_at = 0.0

    def _fetch_token(self):
        resp = requests.post(
            f"{self.api_base}/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            err = HelloAssoConfigError(
                f"Auth HelloAsso refusée ({resp.status_code}) : {resp.text[:200]}"
            )
            err.response = resp  # lu par le test d'intégration (statut HTTP + détail)
            raise err
        data = resp.json()
        self._token = data["access_token"]
        # 60 s de marge avant expiration
        self._token_expires_at = time.time() + int(data.get("expires_in", 1800)) - 60

    @property
    def token(self):
        if not self._token or time.time() >= self._token_expires_at:
            self._fetch_token()
        return self._token

    def _get(self, path, params=None):
        url = f"{self.api_base}{path}"
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {self.token}"},
            params=params or {},
            timeout=self.timeout,
        )
        if resp.status_code == 401:
            # token peut-être expiré — on retry une fois après refresh
            self._token = None
            resp = requests.get(
                url,
                headers={"Authorization": f"Bearer {self.token}"},
                params=params or {},
                timeout=self.timeout,
            )
        resp.raise_for_status()
        return resp.json()

    def paginate(self, path, params=None, page_size=100):
        """Yield chaque item d'un endpoint paginé HelloAsso.

        L'API v5 utilise un `continuationToken` (les champs totalCount/totalPages
        valent souvent -1). On itère tant que la réponse fournit un token et
        que la page reçue est pleine.
        """
        params = dict(params or {})
        params.setdefault("pageSize", page_size)
        size = params["pageSize"]
        while True:
            payload = self._get(path, params=params)
            items = payload.get("data") or []
            for it in items:
                yield it
            pagination = payload.get("pagination") or {}
            token = pagination.get("continuationToken")
            if not token or len(items) < size:
                return
            params.pop("pageIndex", None)
            params["continuationToken"] = token

    def org_path(self, suffix):
        if not self.org_slug:
            raise HelloAssoConfigError("HELLOASSO_ORG_SLUG manquant.")
        return f"/v5/organizations/{self.org_slug}{suffix}"

    def get_organization(self):
        """Organization details (name, url…) of the configured slug."""
        return self._get(self.org_path(""))


def from_app_config(timeout=30):
    from app.services import external_config

    if not external_config.is_enabled("helloasso"):
        raise HelloAssoConfigError(external_config.unavailable_message("helloasso"))
    cfg = external_config.get_all("helloasso")
    base = cfg.get("api_base") or "https://api.helloasso.com"
    missing = [k for k in ("client_id", "client_secret", "org_slug") if not cfg.get(k)]
    if missing:
        raise HelloAssoConfigError(
            "Configuration HelloAsso incomplète (manquant : " + ", ".join(missing)
            + ") — renseignez-la dans Configuration › Intégrations."
        )
    return HelloAssoClient(
        cfg["client_id"], cfg["client_secret"], cfg["org_slug"], base, timeout=timeout
    )
