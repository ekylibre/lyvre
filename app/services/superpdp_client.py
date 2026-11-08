"""Client de l'API SUPER PDP (lot PDP1, référence OpenAPI 1.39.0.beta lue le 08/11/2026).

- URL de base `https://api.superpdp.tech/v1.beta/` ; jeton OAuth 2.1 « client credentials » sur
  `https://api.superpdp.tech/oauth2/token` (identifiants d'une application créée dans SUPER PDP, une par entreprise) ;
  le jeton dure 30 minutes : gardé en mémoire et redemandé avant expiration. La clé détermine l'environnement
  (bac à sable ou production) : rien à choisir dans Lyvre.
- Routes utilisées : `GET /companies/me`, `GET /directory_entries`, `POST /invoices` (Factur-X en `application/pdf`),
  `GET /invoices?direction=in&starting_after_id=` (réception, séquence strictement croissante), `GET /invoices/{id}/download`,
  `GET /invoice_events?starting_after_id=` (statuts), `POST /invoice_events` (statut « encaissée », refus…).
"""
from __future__ import annotations

import threading
import time

import requests

from app.services import external_config

BASE = "https://api.superpdp.tech"
API = f"{BASE}/v1.beta"
TOKEN_URL = f"{BASE}/oauth2/token"
_TOKENS: dict[str, tuple[str, float]] = {}
_LOCK = threading.Lock()


class SuperPdpError(RuntimeError):
    def __init__(self, message, response=None):
        super().__init__(message)
        self.response = response


class SuperPdpConfigError(SuperPdpError):
    pass


def _detail(response) -> str:
    try:
        body = response.json()
    except ValueError:
        return (response.text or "")[:200]
    if isinstance(body, dict):
        error = body.get("error") if isinstance(body.get("error"), (dict, str)) else body
        if isinstance(error, dict):
            return str(error.get("message") or error.get("description") or error)[:300]
        return str(error)[:300]
    return str(body)[:300]


class SuperPdpClient:
    def __init__(self, client_id: str, client_secret: str, timeout: int = 30, session=None):
        self.client_id, self.client_secret, self.timeout = client_id, client_secret, timeout
        self.http = session or requests.Session()

    # -------------------------------------------------------------- jeton

    def token(self) -> str:
        with _LOCK:
            cached = _TOKENS.get(self.client_id)
            if cached and cached[1] > time.time() + 60:
                return cached[0]
        resp = self.http.post(TOKEN_URL, data={"grant_type": "client_credentials", "client_id": self.client_id,
                                               "client_secret": self.client_secret}, timeout=self.timeout)
        if resp.status_code >= 400:
            raise SuperPdpError(f"Identifiants refusés par SUPER PDP (HTTP {resp.status_code}) : {_detail(resp)}", resp)
        body = resp.json()
        token = body.get("access_token")
        if not token:
            raise SuperPdpError("SUPER PDP n'a pas renvoyé de jeton d'accès.", resp)
        with _LOCK:
            _TOKENS[self.client_id] = (token, time.time() + int(body.get("expires_in") or 1800))
        return token

    def _request(self, method: str, path: str, *, retry: bool = True, **kwargs):
        headers = {"Authorization": f"Bearer {self.token()}", "Accept": "application/json", **kwargs.pop("headers", {})}
        resp = self.http.request(method, f"{API}{path}", headers=headers, timeout=self.timeout, **kwargs)
        if resp.status_code == 401 and retry:                  # jeton révoqué ou expiré : un nouvel essai
            with _LOCK:
                _TOKENS.pop(self.client_id, None)
            return self._request(method, path, retry=False, headers=headers, **kwargs)
        if resp.status_code >= 400:
            raise SuperPdpError(f"SUPER PDP a répondu HTTP {resp.status_code} : {_detail(resp)}", resp)
        return resp

    def _json(self, method: str, path: str, **kwargs) -> dict:
        return self._request(method, path, **kwargs).json()

    # -------------------------------------------------------------- routes

    def company(self) -> dict:
        return self._json("GET", "/companies/me")

    def directory_entries(self) -> list[dict]:
        return self._json("GET", "/directory_entries").get("data") or []

    def send_invoice(self, content: bytes, external_id: str, mime: str = "application/pdf") -> dict:
        return self._json("POST", "/invoices", params={"external_id": external_id[:64]}, data=content,
                          headers={"Content-Type": mime})

    def invoices(self, direction: str, starting_after_id: int | None = None, limit: int = 50) -> dict:
        params = {"direction": direction, "limit": limit, "order": "asc"}
        if starting_after_id:
            params["starting_after_id"] = starting_after_id
        return self._json("GET", "/invoices", params=params)

    def download(self, invoice_id: int) -> tuple[bytes, str]:
        resp = self._request("GET", f"/invoices/{invoice_id}/download", headers={"Accept": "application/pdf, application/xml"})
        return resp.content, (resp.headers.get("Content-Type") or "application/octet-stream").split(";")[0]

    def events(self, starting_after_id: int | None = None, limit: int = 100) -> dict:
        params = {"limit": limit}
        if starting_after_id:
            params["starting_after_id"] = starting_after_id
        return self._json("GET", "/invoice_events", params=params)

    def events_of(self, invoice_id: int) -> list[dict]:
        return self._json("GET", "/invoice_events", params={"invoice_id": int(invoice_id)}).get("data") or []

    def post_event(self, invoice_id: int, status_code: str, details: list | None = None) -> dict:
        """Statut de la réforme (`fr:212` encaissée : `details` porte le montant encaissé, `reported_data`)."""
        body: dict = {"invoice_id": int(invoice_id), "status_code": status_code}
        if details:
            body["details"] = details
        return self._json("POST", "/invoice_events", json=body)


def from_app_config(timeout: int = 30) -> SuperPdpClient:
    if not external_config.is_enabled("superpdp"):
        raise SuperPdpConfigError(external_config.unavailable_message("superpdp") or "Intégration SUPER PDP désactivée.")
    cfg = external_config.get_all("superpdp")
    if not cfg.get("client_id") or not cfg.get("client_secret"):
        raise SuperPdpConfigError("Intégration SUPER PDP non configurée : client_id et client_secret de l'application.")
    return SuperPdpClient(cfg["client_id"], cfg["client_secret"], timeout=timeout)
