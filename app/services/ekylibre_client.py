"""Connecteur Ekylibre, lot AG11.a (claudedocs/design_connecteur_ekylibre.md, AGD28) : **adaptateur unique** de l'API.

Tout ce qui dépend de l'API v2 d'Ekylibre (chemins, en-têtes, champs des vues `jbuilder` du dépôt public
`ekylibre/ekylibre`, branche `main`, lues le 07/11/2026) est ici ; le reste de Lyvre ne manipule que les objets
neutres `Production`, `Intervention` et `Matter`. L'API doit devenir celle du « jumeau numérique » de la ferme
(Q-K2) : seul ce module changera.

- Jeton : `POST /api/v2/tokens {email, password}` → `{token}` ; le mot de passe n'est jamais conservé.
  Révocation : `DELETE /api/v2/tokens/<jeton>`.
- Appels : en-tête `Authorization: simple-token <email> <jeton>` ; lecture seule (GET), jamais d'écriture.
- Sûreté : URL `https` seulement, sans identifiants ni adresse privée (résolution DNS contrôlée), pas de
  redirection suivie, délai d'attente et taille de réponse bornés.

Formats **à vérifier sur l'instance de démonstration** (Q-K5) : la surface (`net_surface_area`, un `Measure` sans
`as_json` dans Ekylibre : objet `{value, unit}`, texte « 12.5 hectare » ou fraction « 25/2 » sont acceptés) et la
durée de travail (`working_duration`, lue en secondes).
"""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from urllib.parse import quote, urlsplit

import requests

TIMEOUT = 30
MAX_BYTES = 30 * 1024 * 1024
API = "/api/v2"
SURFACE_UNITS = {"hectare": Decimal(1), "are": Decimal("0.01"), "square_meter": Decimal("0.0001"),
                 "centiare": Decimal("0.0001"), "ha": Decimal(1), "m2": Decimal("0.0001")}
COST_KINDS = ("inputs", "doers", "tools", "receptions")


class EkylibreError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.message, self.status = message, status


# ------------------------------------------------------------------ objets neutres

@dataclass
class Production:
    """Culture (plante) d'Ekylibre : activité, surface en hectares, période de production."""
    id: int
    name: str
    activity_id: int | None
    activity_name: str | None
    surface_ha: Decimal | None
    started_on: date | None
    stopped_on: date | None
    dead_at: date | None = None


@dataclass
class Intervention:
    id: int
    nature: str | None
    procedure: str | None
    name: str | None
    state: str | None
    started_at: datetime | None
    stopped_at: datetime | None
    working_seconds: int
    costs: dict[str, Decimal]                     # inputs, doers, tools, receptions (euros)
    targets: list[int] = field(default_factory=list)
    tools: list[int] = field(default_factory=list)

    @property
    def total_cost(self) -> Decimal:
        return sum(self.costs.values(), Decimal(0))


@dataclass
class Matter:
    id: int
    name: str
    variant_id: int | None
    variety: str | None
    quantity: Decimal | None
    unit: str | None


# ------------------------------------------------------------------ conversions tolérantes

def _decimal(raw) -> Decimal | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, dict):
        return _decimal(raw.get("value"))
    text = str(raw).strip().split(" ")[0]
    try:
        if "/" in text:
            fraction = Fraction(text)
            return Decimal(fraction.numerator) / Decimal(fraction.denominator)
        return Decimal(text)
    except (InvalidOperation, ValueError, ZeroDivisionError):
        return None


def surface_ha(raw) -> Decimal | None:
    """Surface en hectares depuis un `Measure` sérialisé (objet, texte avec unité, nombre)."""
    value = _decimal(raw)
    if value is None:
        return None
    if isinstance(raw, dict):
        unit = str(raw.get("unit") or "hectare")
    else:
        parts = str(raw).strip().split(" ")
        unit = parts[1] if len(parts) > 1 else "hectare"
    factor = SURFACE_UNITS.get(unit)
    if factor is None:
        raise EkylibreError(f"Unité de surface inconnue : « {unit} ».")
    return (value * factor).quantize(Decimal("0.0001"))


def _when(raw) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def _day(raw) -> date | None:
    moment = _when(raw)
    return moment.date() if moment else None


def _int(raw) -> int | None:
    try:
        return int(raw) if raw is not None and raw != "" else None
    except (TypeError, ValueError):
        return None


def production(raw: dict) -> Production:
    return Production(id=int(raw["id"]), name=str(raw.get("name") or ""), activity_id=_int(raw.get("activity_id")),
                      activity_name=raw.get("activity_name"), surface_ha=surface_ha(raw.get("net_surface_area")),
                      started_on=_day(raw.get("production_started_on")), stopped_on=_day(raw.get("production_stopped_on")),
                      dead_at=_day(raw.get("dead_at")))


def intervention(raw: dict) -> Intervention:
    costing = raw.get("costing") or {}
    parameters = raw.get("parameters") or []
    return Intervention(
        id=int(raw["id"]), nature=raw.get("nature"), procedure=raw.get("procedure_name"), name=raw.get("name"),
        state=raw.get("state"), started_at=_when(raw.get("started_at")), stopped_at=_when(raw.get("stopped_at")),
        working_seconds=_int(raw.get("working_duration")) or 0,
        costs={kind: _decimal(costing.get(kind)) or Decimal(0) for kind in COST_KINDS},
        targets=[p["product_id"] for p in parameters if p.get("role") == "target" and p.get("product_id")],
        tools=[p["product_id"] for p in parameters if p.get("role") == "tool" and p.get("product_id")])


def matter(raw: dict) -> Matter:
    return Matter(id=int(raw["id"]), name=str(raw.get("name") or ""), variant_id=_int(raw.get("variant_id")),
                  variety=raw.get("variety"), quantity=_decimal(raw.get("population")), unit=raw.get("unit_name"))


# ------------------------------------------------------------------ URL sûre

def _resolve(host: str) -> list[str]:
    return [info[4][0] for info in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)]


def check_url(url: str) -> str:
    """URL de base normalisée (`https://hôte[:port]`) ; EkylibreError si elle n'est pas sûre."""
    parts = urlsplit((url or "").strip())
    if parts.scheme != "https" or not parts.hostname:
        raise EkylibreError("Adresse Ekylibre attendue en https://… (par exemple https://ferme.ekylibre.farm).")
    if parts.username or parts.password:
        raise EkylibreError("L'adresse ne doit pas contenir d'identifiants.")
    try:
        addresses = _resolve(parts.hostname)
    except OSError:
        raise EkylibreError(f"Serveur Ekylibre « {parts.hostname} » introuvable.") from None
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%")[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise EkylibreError("Adresse Ekylibre refusée (réseau privé ou local).")
    port = f":{parts.port}" if parts.port else ""
    return f"https://{parts.hostname}{port}"


# ------------------------------------------------------------------ appels

def _request(method: str, url: str, timeout: float, **kwargs) -> requests.Response:
    try:
        response = requests.request(method, url, timeout=timeout, allow_redirects=False, stream=True, **kwargs)
    except requests.Timeout:
        raise EkylibreError(f"Délai dépassé ({timeout:g} s) : Ekylibre ne répond pas.") from None
    except requests.RequestException:
        raise EkylibreError("Le serveur Ekylibre ne répond pas.") from None
    body = b""
    for chunk in response.iter_content(65536):
        body += chunk
        if len(body) > MAX_BYTES:
            response.close()
            raise EkylibreError("Réponse d'Ekylibre trop volumineuse.")
    response._content = body  # noqa: SLF001 — corps lu une fois, borné
    if 300 <= response.status_code < 400:
        raise EkylibreError("Ekylibre redirige vers une autre adresse : vérifiez l'URL de l'instance.", response.status_code)
    if response.status_code in (401, 403):
        raise EkylibreError("Identifiants ou jeton refusés par Ekylibre.", response.status_code)
    if response.status_code == 404:
        raise EkylibreError("Ressource introuvable chez Ekylibre : vérifiez l'URL de l'instance.", 404)
    if response.status_code >= 400:
        raise EkylibreError(f"Ekylibre a refusé la demande (HTTP {response.status_code}).", response.status_code)
    return response


def _json(response: requests.Response):
    try:
        return response.json() if response.content else {}
    except ValueError:
        raise EkylibreError("Réponse illisible d'Ekylibre (JSON attendu).") from None


def obtain_token(url: str, email: str, password: str, timeout: float = TIMEOUT) -> str:
    """Jeton de l'utilisateur ; le mot de passe n'est transmis qu'ici et n'est pas conservé."""
    base = check_url(url)
    if not email or not password:
        raise EkylibreError("Email et mot de passe Ekylibre obligatoires.")
    data = _json(_request("POST", f"{base}{API}/tokens", timeout, json={"email": email.strip(), "password": password},
                          headers={"Accept": "application/json"}))
    token = data.get("token") if isinstance(data, dict) else None
    if not token:
        raise EkylibreError("Ekylibre n'a pas renvoyé de jeton.")
    return str(token)


def revoke_token(url: str, token: str, timeout: float = TIMEOUT) -> None:
    base = check_url(url)
    _request("DELETE", f"{base}{API}/tokens/{quote(token, safe='')}", timeout, headers={"Accept": "application/json"})


class Client:
    def __init__(self, url: str, email: str, token: str, timeout: float = TIMEOUT):
        if not url or not email or not token:
            raise EkylibreError("Intégration Ekylibre non configurée (Configuration › Intégrations).")
        self.base, self.email, self.token, self.timeout = check_url(url), email.strip(), token, timeout

    @classmethod
    def from_config(cls, timeout: float = TIMEOUT) -> "Client":
        from app.services import external_config
        return cls(external_config.get("ekylibre", "url") or "", external_config.get("ekylibre", "email") or "",
                   external_config.get("ekylibre", "token") or "", timeout)

    def _get(self, path: str, params: dict | None = None):
        return _json(_request("GET", f"{self.base}{API}{path}", self.timeout, params=params, headers={
            "Accept": "application/json", "Authorization": f"simple-token {self.email} {self.token}"}))

    def profile(self) -> dict:
        data = self._get("/profile")
        return data if isinstance(data, dict) else {}

    def productions(self) -> list[Production]:
        return [production(raw) for raw in self._list("/products/plants")]

    def parcels(self) -> list[Production]:
        """Parcelles (lot AG11.b) : mêmes champs qu'une culture, sans activité (contrôle des surfaces)."""
        return [production(raw) for raw in self._list("/products/land_parcels")]

    def matters(self) -> list[Matter]:
        return [matter(raw) for raw in self._list("/products/matters")]

    def interventions(self) -> list[Intervention]:
        """Toutes les interventions non rejetées (l'API n'a ni filtre de date ni pagination)."""
        return [intervention(raw) for raw in self._list("/interventions")]

    def _list(self, path: str) -> list[dict]:
        data = self._get(path)
        if not isinstance(data, list):
            raise EkylibreError(f"Réponse inattendue d'Ekylibre pour {path} (liste attendue).")
        return [row for row in data if isinstance(row, dict) and "id" in row]
