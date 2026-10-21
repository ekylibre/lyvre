"""Client de l'API Business Qonto (authentification par clé API).

Doc : https://docs.qonto.com/get-started/business-api
- En-tête `Authorization: {identifiant}:{clé secrète}` (ce n'est pas du Basic).
- Bac à sable : autre URL + en-tête `X-Qonto-Staging-Token`.
- Limites : 1 000 requêtes / 10 s par IP → 429 ; au-delà de 200 réponses 401 en une
  heure, Qonto bloque : on n'insiste jamais après un 401 / 403.
- Pagination : `page` / `per_page`, `meta.next_page` ; `page × per_page ≤ 10 000`.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Iterator

import requests

PRODUCTION_BASE = "https://thirdparty.qonto.com/v2"
SANDBOX_BASE = "https://thirdparty-sandbox.staging.qonto.co/v2"

RATE_LIMIT_RETRIES = 3   # 429 : attente Retry-After, sinon 2 s, 4 s, 8 s
SERVER_RETRIES = 2       # 5xx et erreurs réseau
MAX_RETRY_AFTER = 30     # secondes


class QontoError(RuntimeError):
    """Erreur de l'API Qonto ; `response` porte la réponse HTTP quand il y en a une."""

    def __init__(self, message, response=None):
        super().__init__(message)
        self.response = response


class QontoConfigError(QontoError):
    """Intégration désactivée ou configuration incomplète."""


class QontoAuthError(QontoError):
    """Identifiants refusés (401 / 403) : jamais de nouvelle tentative."""


def format_datetime(value: datetime) -> str:
    """Datetime (naïf = UTC) au format ISO 8601 attendu par Qonto."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class QontoClient:
    def __init__(self, login, secret_key, staging_token=None, timeout=30, retry=True,
                 session=None, sleep=time.sleep):
        self.base_url = SANDBOX_BASE if staging_token else PRODUCTION_BASE
        self.timeout = timeout
        self.retry = retry
        self._sleep = sleep
        self._session = session or requests.Session()
        self._session.headers.update({
            "Authorization": f"{login}:{secret_key}",
            "Accept": "application/json",
        })
        if staging_token:
            self._session.headers["X-Qonto-Staging-Token"] = staging_token

    # ------------------------------------------------------------------ HTTP

    def _get(self, path, params=None) -> dict:
        rate_limited = server_errors = 0
        while True:
            try:
                resp = self._session.get(f"{self.base_url}{path}", params=params,
                                         timeout=self.timeout)
            except (requests.ConnectionError, requests.Timeout):
                if not self.retry or server_errors >= SERVER_RETRIES:
                    raise
                server_errors += 1
                self._sleep(2 ** server_errors)
                continue

            if resp.status_code in (401, 403):
                raise QontoAuthError(f"Qonto a refusé les identifiants (HTTP {resp.status_code}).",
                                     response=resp)
            if resp.status_code == 429:
                if not self.retry or rate_limited >= RATE_LIMIT_RETRIES:
                    raise QontoError("Trop de requêtes vers Qonto (HTTP 429).", response=resp)
                rate_limited += 1
                self._sleep(self._retry_after(resp, 2 ** rate_limited))
                continue
            if resp.status_code >= 500:
                if not self.retry or server_errors >= SERVER_RETRIES:
                    raise QontoError(f"Qonto rencontre une erreur (HTTP {resp.status_code}).",
                                     response=resp)
                server_errors += 1
                self._sleep(2 ** server_errors)
                continue
            if resp.status_code >= 400:
                raise QontoError(f"Qonto a répondu HTTP {resp.status_code}.", response=resp)
            return resp.json()

    @staticmethod
    def _retry_after(resp, default):
        try:
            return min(float(resp.headers.get("Retry-After")), MAX_RETRY_AFTER)
        except (TypeError, ValueError):
            return default

    # ------------------------------------------------------------- ressources

    def organization(self) -> dict:
        """Organisation authentifiée, avec ses comptes (`bank_accounts`)."""
        return self._get("/organization").get("organization") or {}

    def bank_accounts(self) -> list[dict]:
        return self.organization().get("bank_accounts") or []

    def list_transactions(self, bank_account_id, *, statuses=("completed",), page=1, per_page=100,
                          updated_from=None, updated_to=None, settled_from=None,
                          settled_to=None) -> tuple[list[dict], dict]:
        """Une page de transactions : (transactions, meta)."""
        params = {
            "bank_account_id": bank_account_id,
            "status[]": list(statuses),
            "page": page,
            "per_page": per_page,
            "sort_by": "settled_at:asc",
        }
        for name, value in (("updated_at_from", updated_from), ("updated_at_to", updated_to),
                            ("settled_at_from", settled_from), ("settled_at_to", settled_to)):
            if value is not None:
                params[name] = format_datetime(value)
        payload = self._get("/transactions", params=params)
        return payload.get("transactions") or [], payload.get("meta") or {}

    def iter_transactions(self, bank_account_id, **filters) -> Iterator[tuple[list[dict], dict]]:
        """Pages successives (transactions, meta) tant que `meta.next_page` est renseigné."""
        page = 1
        while page:
            items, meta = self.list_transactions(bank_account_id, page=page, **filters)
            yield items, meta
            page = meta.get("next_page")

    def list_supplier_invoices(self, *, page=1, per_page=100, updated_from=None, updated_to=None,
                               created_from=None, created_to=None,
                               sort_by="updated_at:asc") -> tuple[list[dict], dict]:
        """Une page de factures d'achat (avoirs et documents à revoir compris) : (factures, meta)."""
        params = {"page": page, "per_page": per_page, "sort_by": sort_by}
        for name, value in (("updated_at_from", updated_from), ("updated_at_to", updated_to),
                            ("created_at_from", created_from), ("created_at_to", created_to)):
            if value is not None:
                params[f"filter[{name}]"] = format_datetime(value)
        payload = self._get("/supplier_invoices", params=params)
        return payload.get("supplier_invoices") or [], payload.get("meta") or {}


def from_app_config(timeout=30, retry=True) -> QontoClient:
    from app.services import external_config

    if not external_config.is_enabled("qonto"):
        raise QontoConfigError(external_config.unavailable_message("qonto"))
    cfg = external_config.get_all("qonto")
    missing = [k for k in external_config.SERVICE_REQUIRED_KEYS["qonto"] if not cfg.get(k)]
    if missing:
        raise QontoConfigError(
            "Configuration Qonto incomplète (manquant : " + ", ".join(missing)
            + ") — Configuration › Intégrations."
        )
    return QontoClient(cfg["login"], cfg["secret_key"], cfg.get("staging_token"),
                       timeout=timeout, retry=retry)
