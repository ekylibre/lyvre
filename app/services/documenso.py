"""Client Documenso (lot L4, décisions BX5, BX10, BX16) : API v2 `{url}/api/v2`, jeton d'équipe en
en-tête `Authorization` ; serveur et jeton propres à chaque instance (intégration `documenso`, sans
repli `.env` : une copie de base ne peut pas envoyer à la signature sans être configurée).

Documenso (édition communautaire, auto-hébergée) accepte un PDF par l'API, contrairement à
l'édition libre de Docuseal :

- `create_envelope` : PDF et signataires (`POST /envelope/create`, multipart), signature **dans
  l'ordre** (`signingOrder: SEQUENTIAL`) ; les champs viennent des balises `{{signature, r1}}` du PDF
  (r1 = premier signataire) ;
- `distribute` : envoi des invitations (`POST /envelope/distribute`) ;
- `envelope` : statut de l'envoi et de chaque signataire (`GET /envelope/{id}`) ;
- `download_signed`, `audit_log` : PDF signé et journal d'audit ;
- `cancel` : annulation d'un envoi en cours (`POST /envelope/cancel`).

Les tests remplacent `Client` (aucun appel réel).
"""
from __future__ import annotations

import json

import requests

from app.services import external_config

TIMEOUT = 30


class DocumensoError(RuntimeError):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def base_url() -> str:
    return (external_config.get("documenso", "url") or "").strip().rstrip("/")


class Client:
    def __init__(self, url: str, api_key: str, timeout: float = TIMEOUT):
        if not url or not api_key:
            raise DocumensoError("Intégration Documenso non configurée (Configuration › Intégrations).")
        self.url, self.api_key, self.timeout = url.rstrip("/"), api_key, timeout
        self.api = f"{self.url}/api/v2"

    @classmethod
    def from_config(cls, timeout: float = TIMEOUT) -> "Client":
        return cls(base_url(), external_config.get("documenso", "api_key") or "", timeout)

    def _send(self, method: str, path: str, raw: bool = False, **kwargs):
        try:
            response = requests.request(method, f"{self.api}{path}", timeout=self.timeout,
                                        headers={"Authorization": self.api_key, "Accept": "application/json"}, **kwargs)
        except requests.RequestException:
            raise DocumensoError(f"Le serveur Documenso {self.url} ne répond pas.") from None
        if response.status_code in (401, 403):
            raise DocumensoError("Jeton d'API Documenso refusé : vérifiez l'intégration.")
        if response.status_code >= 400:
            detail = ""
            try:
                detail = (response.json() or {}).get("message") or ""
            except ValueError:
                pass
            raise DocumensoError(f"Documenso a refusé la demande ({response.status_code}){' : ' + detail if detail else ''}.")
        if raw:
            return response.content
        try:
            return response.json() if response.content else {}
        except ValueError:
            raise DocumensoError("Réponse illisible du serveur Documenso.") from None

    def probe(self):
        return self._send("GET", "/envelope?perPage=1")

    def create_envelope(self, title: str, pdf: bytes, recipients: list[dict], external_id: str,
                        send_email: bool = True) -> str:
        """Brouillon d'envoi : PDF, signataires dans l'ordre (r1, r2…) ; renvoie son identifiant."""
        payload = {"type": "DOCUMENT", "title": title, "externalId": external_id,
                   "recipients": [{"email": r["email"], "name": r["name"], "role": "SIGNER", "signingOrder": n}
                                  for n, r in enumerate(recipients, start=1)],
                   "meta": {"signingOrder": "SEQUENTIAL", "distributionMethod": "EMAIL" if send_email else "NONE",
                            "language": "fr"}}
        data = self._send("POST", "/envelope/create", data={"payload": json.dumps(payload)},
                          files={"files": (f"{external_id}.pdf", pdf, "application/pdf")})
        if not data.get("id"):
            raise DocumensoError("Documenso n'a pas renvoyé l'identifiant de l'envoi.")
        return data["id"]

    def resize_signatures(self, envelope_id: str, width: float, height: float) -> int:
        """Champs de signature d'un brouillon agrandis (en % de la page) : la balise du PDF ne donne
        que la hauteur d'une ligne de texte. Renvoie le nombre de champs de signature."""
        fields = [f for f in (self.envelope(envelope_id).get("fields") or []) if f.get("type") == "SIGNATURE"]
        if fields:
            self._send("POST", "/envelope/field/update-many", json={"envelopeId": envelope_id, "data": [
                {"id": f["id"], "type": "SIGNATURE", "width": width, "height": height} for f in fields]})
        return len(fields)

    def add_initials(self, envelope_id: str, pages: int, boxes: list[tuple[float, float, float, float]]) -> int:
        """Cases de paraphe sur chaque page : `boxes[n]` = (x, y, largeur, hauteur) en % de la page pour
        le n-ième signataire (ordre de signature). Renvoie le nombre de champs créés."""
        recipients = sorted(self.envelope(envelope_id).get("recipients") or [], key=lambda r: r.get("signingOrder") or 0)
        data = [{"recipientId": r["id"], "type": "INITIALS", "page": page, "positionX": x, "positionY": y,
                 "width": w, "height": h}
                for page in range(1, pages + 1) for r, (x, y, w, h) in zip(recipients, boxes)]
        if data:
            self._send("POST", "/envelope/field/create-many", json={"envelopeId": envelope_id, "data": data})
        return len(data)

    def distribute(self, envelope_id: str) -> dict:
        return self._send("POST", "/envelope/distribute", json={"envelopeId": envelope_id})

    def envelope(self, envelope_id: str) -> dict:
        return self._send("GET", f"/envelope/{envelope_id}")

    def download_signed(self, item_id: str) -> bytes:
        return self._send("GET", f"/envelope/item/{item_id}/download?version=signed", raw=True)

    def audit_log(self, envelope_id: str) -> bytes:
        return self._send("GET", f"/envelope/{envelope_id}/audit-log/download", raw=True)

    def cancel(self, envelope_id: str) -> None:
        self._send("POST", "/envelope/cancel", json={"envelopeId": envelope_id})

    def delete(self, envelope_id: str) -> None:
        self._send("POST", "/envelope/delete", json={"envelopeId": envelope_id})
