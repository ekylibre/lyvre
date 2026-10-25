"""Client de l'API Brevo v3 (lot B1) : compte, listes, attributs et contacts.

En-tête `api-key`, délai de 15 s. Débit limité à 10 requêtes par seconde (la moitié du quota
annoncé par `x-sib-ratelimit-limit`) ; sur 429, attente jusqu'à `x-sib-ratelimit-reset` puis
nouvelle tentative (3 au plus). Le compte Brevo peut restreindre l'API à des adresses IP
autorisées : ce refus a son propre code (`ip_not_allowed`), avec la marche à suivre. Ni la clé ni
le corps des réponses ne sont journalisés.
"""
from __future__ import annotations

import re
import threading
import time

import requests

from app.services import external_config

API_BASE = "https://api.brevo.com/v3"
TIMEOUT = 15
MIN_INTERVAL = 0.1  # 10 requêtes par seconde au plus
MAX_RETRIES = 3
PAGE = 500  # contacts par page de lecture
BATCH = 50  # contacts par mise à jour groupée

_pace_lock = threading.Lock()
_last_call = [0.0]


class BrevoError(Exception):
    """`code` : not_configured | invalid_key | ip_not_allowed | not_found | duplicate | busy |
    invalid | unavailable."""

    def __init__(self, code: str, message: str, status: int | None = None):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def _pace() -> None:
    with _pace_lock:
        wait = _last_call[0] + MIN_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.monotonic()


def _message(response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    return str(body.get("message") or "") if isinstance(body, dict) else ""


def _error(response) -> BrevoError:
    text, status = _message(response), response.status_code
    if status in (401, 403) and "unrecognised ip" in text.lower():
        found = re.search(r"address\s+([0-9a-fA-F:.]+)", text)
        ip = f" ({found.group(1).rstrip('.')})" if found else ""
        return BrevoError("ip_not_allowed", f"L'adresse IP du serveur{ip} n'est pas autorisée dans Brevo : "
                          "ajoutez-la dans Brevo › Sécurité › IP autorisées, puis réessayez.", status)
    if status in (401, 403):
        return BrevoError("invalid_key", "Clé API refusée par Brevo : vérifiez-la dans Configuration › Intégrations.",
                          status)
    if status == 404:
        return BrevoError("not_found", "Introuvable dans Brevo.", status)
    if status == 400 and ("already exist" in text.lower() or "duplicate" in text.lower()):
        return BrevoError("duplicate", "Ce contact existe déjà dans Brevo.", status)
    if status == 400:
        return BrevoError("invalid", f"Brevo a refusé la demande : {text[:200]}" if text else "Brevo a refusé la demande.",
                          status)
    if status == 429:
        return BrevoError("busy", "Brevo est très sollicité : réessayez dans un instant.", status)
    return BrevoError("unavailable", f"Brevo rencontre une erreur (HTTP {status}), réessayez plus tard.", status)


class Client:
    def __init__(self, api_key: str, base: str = API_BASE, timeout: int = TIMEOUT):
        if not api_key:
            raise BrevoError("not_configured", "Brevo n'est pas configuré : renseignez la clé API.")
        self.base, self.timeout = base.rstrip("/"), timeout
        self.headers = {"api-key": api_key, "accept": "application/json"}

    @classmethod
    def from_config(cls, timeout: int = TIMEOUT) -> "Client":
        return cls(external_config.get("brevo", "api_key") or "", timeout=timeout)

    def request(self, method: str, path: str, *, params=None, body=None):
        for attempt in range(MAX_RETRIES + 1):
            _pace()
            try:
                response = requests.request(method, self.base + path, params=params, json=body,
                                            headers=self.headers, timeout=self.timeout)
            except requests.RequestException:
                raise BrevoError("unavailable", "Brevo ne répond pas : réessayez plus tard.") from None
            if response.status_code == 429 and attempt < MAX_RETRIES:
                try:
                    reset = float(response.headers.get("x-sib-ratelimit-reset") or 1)
                except ValueError:
                    reset = 1.0
                time.sleep(min(max(reset, 0.5), 60))
                continue
            if not response.ok:
                raise _error(response)
            if response.status_code == 204 or not response.content:
                return None
            try:
                return response.json()
            except ValueError:
                raise BrevoError("unavailable", "Réponse de Brevo illisible.") from None
        raise BrevoError("busy", "Brevo est très sollicité : réessayez dans un instant.")

    # ------------------------------------------------------------------ compte, listes, attributs

    def account(self) -> dict:
        return self.request("GET", "/account") or {}

    def lists(self) -> list[dict]:
        out, offset = [], 0
        while True:
            page = (self.request("GET", "/contacts/lists", params={"limit": 50, "offset": offset}) or {}).get("lists") or []
            out += page
            if len(page) < 50:
                return out
            offset += 50

    def attributes(self) -> list[dict]:
        return (self.request("GET", "/contacts/attributes") or {}).get("attributes") or []

    def create_attribute(self, name: str, kind: str) -> None:
        self.request("POST", f"/contacts/attributes/normal/{name}", body={"type": kind})

    # ------------------------------------------------------------------ contacts

    def contacts(self) -> list[dict]:
        """Tous les contacts du compte (500 par page)."""
        out, offset = [], 0
        while True:
            page = (self.request("GET", "/contacts", params={"limit": PAGE, "offset": offset}) or {}).get("contacts") or []
            out += page
            if len(page) < PAGE:
                return out
            offset += PAGE

    def create_contact(self, email: str, ext_id: str, attributes: dict, list_ids: list[int]) -> int | None:
        """Création seule (jamais `updateEnabled` ni `forceMerge`) ; renvoie l'id du contact."""
        body = {"email": email, "ext_id": ext_id, "attributes": attributes, "listIds": list_ids}
        return (self.request("POST", "/contacts", body=body) or {}).get("id")

    def update_batch(self, rows: list[dict]) -> None:
        """Mises à jour par `id` (paquets de 50). Champs permis : attributes, listIds, ext_id."""
        for start in range(0, len(rows), BATCH):
            self.request("POST", "/contacts/batch", body={"contacts": rows[start:start + BATCH]})

    def update_contact(self, contact_id: int, row: dict) -> None:
        self.request("PUT", f"/contacts/{contact_id}", params={"identifierType": "contact_id"}, body=row)

    def unlink(self, list_id: int, contact_ids: list[int]) -> None:
        for start in range(0, len(contact_ids), 150):
            self.request("POST", f"/contacts/lists/{list_id}/contacts/remove",
                         body={"ids": contact_ids[start:start + 150]})
