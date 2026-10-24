"""Client Docuseal (lot L4, décisions BX5, BX10, BX16) : API REST `{url}/api`, clé en en-tête
`X-Auth-Token`, serveur et clé propres à chaque instance (intégration `docuseal`, sans repli `.env` :
une copie de base ne peut pas envoyer à la signature sans être configurée).

- `create_submission` : PDF en base64 (`POST /submissions/pdf`), signataires dans l'ordre
  (`order: preserved`), champs de signature placés par les balises `{{…;type=signature}}` du PDF ;
- `submission` : statut de l'envoi et de chaque signataire (`GET /submissions/{id}`) ;
- `documents` : PDF signés (`GET /submissions/{id}/documents`) ; `download` ne lit que des adresses
  du serveur configuré ;
- `archive` : annulation de l'envoi (`DELETE /submissions/{id}`).

Les tests remplacent `Client` (aucun appel réel).
"""
from __future__ import annotations

import base64
from urllib.parse import urlparse

import requests

from app.services import external_config

TIMEOUT = 30


class DocusealError(RuntimeError):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def base_url() -> str:
    return (external_config.get("docuseal", "url") or "").strip().rstrip("/")


class Client:
    def __init__(self, url: str, api_key: str, timeout: float = TIMEOUT):
        if not url or not api_key:
            raise DocusealError("Intégration Docuseal non configurée (Configuration › Intégrations).")
        self.url, self.api_key, self.timeout = url.rstrip("/"), api_key, timeout
        # Serveur auto-hébergé : API sous /api ; service en ligne : api.docuseal.com (ou .eu) sans préfixe.
        host = urlparse(self.url).netloc
        self.api = self.url if host.startswith("api.") else f"{self.url}/api"
        self.file_hosts = {host, host.removeprefix("api.")}

    @classmethod
    def from_config(cls, timeout: float = TIMEOUT) -> "Client":
        return cls(base_url(), external_config.get("docuseal", "api_key") or "", timeout)

    def _request(self, method: str, path: str, json=None):
        try:
            response = requests.request(method, f"{self.api}{path}", json=json, timeout=self.timeout,
                                        headers={"X-Auth-Token": self.api_key, "Accept": "application/json"})
        except requests.RequestException:
            raise DocusealError(f"Le serveur Docuseal {self.url} ne répond pas.") from None
        if response.status_code in (401, 403):
            raise DocusealError("Clé d'API Docuseal refusée : vérifiez l'intégration.")
        if response.status_code >= 400:
            detail = ""
            try:
                detail = (response.json() or {}).get("error") or ""
            except ValueError:
                pass
            raise DocusealError(f"Docuseal a refusé la demande ({response.status_code}){' : ' + detail if detail else ''}.")
        try:
            return response.json() if response.content else {}
        except ValueError:
            raise DocusealError("Réponse illisible du serveur Docuseal.") from None

    def probe(self):
        return self._request("GET", "/templates?limit=1")

    def create_submission(self, name: str, pdf: bytes, submitters: list[dict], external_id: str,
                          send_email: bool = True) -> dict:
        body = {"name": name, "order": "preserved", "send_email": send_email,
                "documents": [{"name": name, "file": base64.b64encode(pdf).decode()}],
                "submitters": submitters}
        data = self._request("POST", "/submissions/pdf", body)
        # Réponse : la soumission (avec ses signataires), ou la liste des signataires selon la version.
        if isinstance(data, list):
            return {"id": data[0].get("submission_id") if data else None, "submitters": data}
        return data

    def submission(self, submission_id) -> dict:
        return self._request("GET", f"/submissions/{submission_id}")

    def documents(self, submission_id) -> list[dict]:
        return (self._request("GET", f"/submissions/{submission_id}/documents") or {}).get("documents") or []

    def archive(self, submission_id) -> None:
        self._request("DELETE", f"/submissions/{submission_id}")

    def download(self, url: str) -> bytes:
        """Fichier d'un envoi : seulement sur le serveur configuré (pas d'adresse fournie par ailleurs)."""
        if urlparse(url).netloc not in self.file_hosts:
            raise DocusealError("Adresse de document hors du serveur Docuseal : téléchargement refusé.")
        try:
            response = requests.get(url, timeout=self.timeout, headers={"X-Auth-Token": self.api_key})
            response.raise_for_status()
        except requests.RequestException:
            raise DocusealError("Document signé indisponible sur le serveur Docuseal.") from None
        return response.content
