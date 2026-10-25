"""API Sirene v4 de l'INSEE (lot G3) : fiches d'unités légales et d'établissements, recherche par nom,
proposition de champs pour la Structure et les tiers.

Appels côté serveur seulement (la clé `SIRENE_API_KEY` ne va jamais au navigateur), délai de 10 s,
cache de 24 h des fiches. Quota de l'INSEE : 30 requêtes par minute, 2 000 par heure. Le limiteur
vit dans le processus (gunicorn : 1 processus, plusieurs fils) ; plusieurs processus demanderaient
un stockage commun. Un appel interactif hors quota est refusé tout de suite (`busy`) ; une tâche de
fond attend son tour (`limiter.wait()`).

Réponses v4 (`/etat-courant/...`) : champs à plat ; l'adresse d'un établissement n'est renvoyée que
si `champs` la demande ; listes multicritères sous `items[].item`.
"""
from __future__ import annotations

import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field

import requests
from flask import current_app

from app.services import nomenclatures

TIMEOUT = 10
CACHE_SECONDS = 24 * 3600
CACHE_MAX = 2000
BATCH = 100  # numéros par appel multicritère
SEARCH_LIMIT = 10
ESTABLISHMENT_FIELDS = ["siren", "siret", "statutDiffusionEtablissement", "etatEtablissement", "etablissementSiege",
                        "activitePrincipaleEtablissement", "nomenclatureActivitePrincipaleEtablissement",
                        "adresseEtablissement"]
INDIVIDUAL = "1000"  # catégorie juridique : entrepreneur individuel
REPETITIONS = {"B": "bis", "T": "ter", "Q": "quater", "C": "quinquies"}


class SireneError(Exception):
    """`code` : not_configured | not_found | busy | unavailable | invalid."""

    def __init__(self, code: str, message: str, retry_after: int | None = None):
        super().__init__(message)
        self.code, self.message, self.retry_after = code, message, retry_after


# ------------------------------------------------------------------ quota


class RateLimiter:
    """Fenêtres glissantes (30 / minute, 2 000 / heure), partagées par les fils du processus."""

    def __init__(self, limits=((30, 60), (2000, 3600)), clock=time.monotonic):
        self.limits, self.clock = limits, clock
        self.calls: deque[float] = deque()
        self.lock = threading.Lock()

    def _delay(self, now: float) -> float:
        longest = max(window for _count, window in self.limits)
        while self.calls and now - self.calls[0] >= longest:
            self.calls.popleft()
        delay = 0.0
        for count, window in self.limits:
            recent = [t for t in self.calls if now - t < window]
            if len(recent) >= count:
                delay = max(delay, window - (now - recent[-count]))
        return delay

    def acquire(self) -> None:
        """Réserve un appel, ou lève `busy` avec le délai d'attente (appel interactif)."""
        with self.lock:
            now = self.clock()
            delay = self._delay(now)
            if delay > 0:
                raise SireneError("busy", "Trop de recherches Sirene : réessayez dans quelques secondes.",
                                  retry_after=max(1, int(delay + 0.999)))
            self.calls.append(now)

    def wait(self) -> None:
        """Attend son tour, puis réserve un appel (tâche de fond)."""
        while True:
            try:
                return self.acquire()
            except SireneError as exc:
                time.sleep(exc.retry_after or 1)


limiter = RateLimiter()
_cache: dict[str, tuple[float, object]] = {}
_cache_lock = threading.Lock()


def available() -> bool:
    return bool(current_app.config.get("SIRENE_API_KEY"))


def _request(method: str, path: str, *, params=None, body=None, cache=True, background=False):
    """Appel de l'API (JSON) ; `SireneError` normalisée, jamais le message brut de l'INSEE."""
    if not available():
        raise SireneError("not_configured", "Sirene n'est pas configuré sur ce serveur.")
    key = f"{method} {path} {params!r} {body!r}"
    if cache:
        with _cache_lock:
            hit = _cache.get(key)
        if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
            return hit[1]
    (limiter.wait if background else limiter.acquire)()
    url = current_app.config["SIRENE_API_URL"].rstrip("/") + path
    headers = {"X-INSEE-Api-Key-Integration": current_app.config["SIRENE_API_KEY"], "Accept": "application/json"}
    try:
        response = requests.request(method, url, params=params, json=body, headers=headers, timeout=TIMEOUT)
    except requests.RequestException:
        raise SireneError("unavailable", "Sirene ne répond pas : réessayez plus tard.") from None
    if response.status_code == 404:
        raise SireneError("not_found", "Numéro inconnu de Sirene.")
    if response.status_code == 429:
        raise SireneError("busy", "Sirene est très sollicité : réessayez dans un instant.",
                          retry_after=_retry_after(response))
    if response.status_code == 400 and "doublon" in response.text.lower():
        valid = re.search(r"\b(\d{9}|\d{14})\b", response.text)
        raise SireneError("not_found", "Numéro remplacé dans Sirene" + (f" par {valid.group(1)}." if valid else "."))
    if not response.ok:
        current_app.logger.warning("Sirene %s %s : HTTP %s", method, path, response.status_code)
        raise SireneError("unavailable", "Sirene ne répond pas : réessayez plus tard.")
    try:
        data = response.json()
    except ValueError:
        raise SireneError("unavailable", "Réponse de Sirene illisible.") from None
    if cache:
        with _cache_lock:
            if len(_cache) >= CACHE_MAX:
                _cache.clear()
            _cache[key] = (time.monotonic(), data)
    return data


def _retry_after(response) -> int:
    reset = response.headers.get("x-rate-limit-reset")  # horodatage en millisecondes
    try:
        return max(1, int(int(reset) / 1000 - time.time() + 0.999))
    except (TypeError, ValueError):
        return 60


def _items(data) -> list[dict]:
    return [row.get("item", row) for row in (data or {}).get("items", [])]


# ------------------------------------------------------------------ fiches


def legal_unit(siren: str, background=False) -> dict:
    return _request("GET", f"/etat-courant/unites-legales/{siren}", background=background)


def establishment(siret: str, background=False) -> dict:
    return _request("GET", f"/etat-courant/etablissements/{siret}", params={"champs": ",".join(ESTABLISHMENT_FIELDS)},
                    background=background)


def _batched(path: str, key: str, values: list[str], extra: dict, background: bool, index: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    values = sorted(set(values))
    for start in range(0, len(values), BATCH):
        chunk = values[start:start + BATCH]
        body = {key: chunk, **extra, "nombre": len(chunk) * (1 if index == key else 5)}
        for item in _items(_request("POST", path, body=body, background=background)):
            out.setdefault(item.get(index), item)
    return out


def legal_units(sirens: list[str], background=False) -> dict[str, dict]:
    """Unités légales par SIREN, 100 par appel."""
    return _batched("/etat-courant/unites-legales/multicritere", "siren", sirens, {}, background, "siren")


def head_offices(sirens: list[str], background=False) -> dict[str, dict]:
    """Établissement siège par SIREN, 100 par appel."""
    return _batched("/etat-courant/etablissements/multicritere", "siren", sirens,
                    {"etablissementSiege": True, "champs": ESTABLISHMENT_FIELDS}, background, "siren")


def establishments(sirets: list[str], background=False) -> dict[str, dict]:
    """Établissements par SIRET, 100 par appel."""
    return _batched("/etat-courant/etablissements/multicritere", "siret", sirets,
                    {"champs": ESTABLISHMENT_FIELDS}, background, "siret")


# ------------------------------------------------------------------ proposition


def vat_number(siren: str) -> str:
    """N° de TVA intracommunautaire français calculé : FR + clé + SIREN (D7)."""
    return f"FR{(12 + 3 * (int(siren) % 97)) % 97:02d}{siren}"


def unit_name(unit: dict) -> str:
    """Dénomination, ou « Prénom Nom » d'un entrepreneur individuel ; casse de Sirene (D5)."""
    if unit.get("denominationUniteLegale"):
        return unit["denominationUniteLegale"]
    first = unit.get("prenomUsuelUniteLegale") or unit.get("prenom1UniteLegale")
    last = unit.get("nomUsageUniteLegale") or unit.get("nomUniteLegale")
    return " ".join(p for p in (first, last) if p) or unit.get("siren", "")


def address(est: dict) -> dict:
    a = est.get("adresseEtablissement") or {}
    repetition = a.get("indiceRepetitionEtablissement")
    street = " ".join(p for p in (a.get("numeroVoieEtablissement"), REPETITIONS.get(repetition or "", repetition),
                                  (a.get("typeVoieEtablissement") or "").lower() or None,
                                  a.get("libelleVoieEtablissement")) if p)
    foreign = a.get("libellePaysEtrangerEtablissement")
    return {"address_line1": street or None, "address_line2": a.get("complementAdresseEtablissement") or None,
            "postal_code": a.get("codePostalEtablissement") or None,
            "city": a.get("libelleCommuneEtablissement") or a.get("libelleCommuneEtrangerEtablissement") or None,
            "country": foreign.title() if foreign else "France"}


def _active_unit(unit: dict) -> bool:
    return unit.get("etatUniteLegale") not in ("C", "4")  # v4 : 4 = cessée (C en v3)


def _open(est: dict) -> bool:
    return est.get("etatEtablissement") not in ("F", "3")  # v4 : 3 = fermé (F en v3)


@dataclass
class Proposal:
    values: dict
    computed: list[str] = field(default_factory=list)
    state: str = "active"
    warnings: list[str] = field(default_factory=list)
    labels: dict = field(default_factory=dict)

    def payload(self) -> dict:
        return {"proposal": self.values, "computed": self.computed, "state": self.state,
                "warnings": self.warnings, "labels": self.labels}


def build_proposal(unit: dict, est: dict | None, *, for_entity: bool, association: bool = False,
                   requested_siret: str | None = None) -> Proposal:
    """Champs Lyvre tirés d'une unité légale et d'un établissement (siège, ou celui demandé)."""
    siren = unit.get("siren")
    category = unit.get("categorieJuridiqueUniteLegale")
    values = {"name": unit_name(unit), "siren": siren, "siret": (est or {}).get("siret")}
    warnings = []
    if est is not None:
        if unit.get("statutDiffusionUniteLegale") == "P" or est.get("statutDiffusionEtablissement") == "P":
            warnings.append("Diffusion partielle : l'adresse n'est pas communiquée par l'INSEE.")
        else:
            values.update(address(est))
    if requested_siret and est is not None and est.get("siret") != requested_siret:
        warnings.append("Établissement fermé : le siège est proposé.")
    if for_entity:
        source = est if est is not None and est.get("activitePrincipaleEtablissement") else None
        naf = (source or {}).get("activitePrincipaleEtablissement") or unit.get("activitePrincipaleUniteLegale")
        nomenclature = ((source or {}).get("nomenclatureActivitePrincipaleEtablissement")
                        or unit.get("nomenclatureActivitePrincipaleUniteLegale"))
        values["person_kind"] = "individual" if category == INDIVIDUAL else "company"
    else:
        naf = unit.get("activitePrincipaleUniteLegale")
        nomenclature = unit.get("nomenclatureActivitePrincipaleUniteLegale")
        values["legal_form"] = nomenclatures.legal_form_label(category) if category else None
        if association and unit.get("identifiantAssociationUniteLegale"):
            values["rna"] = unit["identifiantAssociationUniteLegale"]
    values["naf_code"] = (naf or "").replace(".", "") or None
    values["naf_nomenclature"] = nomenclature if naf else None
    values["vat_number"] = vat_number(siren) if siren else None
    state = "active" if _active_unit(unit) and (est is None or _open(est)) else "ceased"
    labels = {"legal_form": nomenclatures.legal_form_label(category) if category else None,
              "naf": nomenclatures.naf_label(values["naf_code"], nomenclature) if values["naf_code"] else None}
    return Proposal({k: v for k, v in values.items() if v not in (None, "")}, ["vat_number"] if siren else [],
                    state, warnings, labels)


def proposal(siren: str | None = None, siret: str | None = None, *, for_entity: bool = False,
             association: bool = False) -> Proposal:
    """Proposition pour un SIREN (siège) ou un SIRET (cet établissement, ou le siège s'il est fermé)."""
    est = None
    if siret:
        est = establishment(siret)
        siren = est.get("siren") or siret[:9]
    unit = legal_unit(siren)
    requested = siret
    if est is None or (not _open(est) and _active_unit(unit)):
        nic = unit.get("nicSiegeUniteLegale")
        if nic:
            try:
                est = establishment(f"{siren}{nic}")
            except SireneError as exc:
                if exc.code != "not_found":
                    raise
    return build_proposal(unit, est, for_entity=for_entity, association=association, requested_siret=requested)


# ------------------------------------------------------------------ recherche


def _candidate(unit: dict, est: dict | None) -> dict:
    a = address(est) if est and unit.get("statutDiffusionUniteLegale") != "P" else {}
    return {"siren": unit.get("siren"), "siret": (est or {}).get("siret"), "name": unit_name(unit),
            "legal_form": nomenclatures.legal_form_label(unit.get("categorieJuridiqueUniteLegale"))
            if unit.get("categorieJuridiqueUniteLegale") else None,
            "postal_code": a.get("postal_code"), "city": a.get("city"),
            "head_office": bool((est or {}).get("etablissementSiege")),
            "active": _active_unit(unit) and (est is None or _open(est))}


def search(text: str, postal_code: str | None = None, limit: int = SEARCH_LIMIT) -> list[dict]:
    """Nom, SIREN ou SIRET. Un numéro donne sa fiche ; un nom, 2 appels : unités légales actives,
    puis leurs sièges (ou leurs établissements dans le code postal donné)."""
    digits = re.sub(r"[\s.]", "", text or "")
    if re.fullmatch(r"\d{9}|\d{14}", digits):
        siret = digits if len(digits) == 14 else None
        est = establishment(siret) if siret else None
        unit = legal_unit(digits[:9])
        if est is None and unit.get("nicSiegeUniteLegale"):
            est = head_offices([digits[:9]]).get(digits[:9])
        return [_candidate(unit, est)]
    text = (text or "").strip()
    if len(text) < 2:
        raise SireneError("invalid", "Saisissez au moins deux caractères, un SIREN ou un SIRET.")
    units = _items(_request("POST", "/etat-courant/unites-legales/multicritere", cache=False, body={
        "denominationUniteLegale": [text], "etatUniteLegale": ["1"], "nombre": limit}))
    if not units:
        return []
    sirens = [u["siren"] for u in units]
    postal = re.sub(r"\s", "", postal_code or "")
    if postal:
        rows = _items(_request("POST", "/etat-courant/etablissements/multicritere", cache=False, body={
            "siren": sirens, "codePostalEtablissement": [postal], "etatEtablissement": ["1"],
            "champs": ESTABLISHMENT_FIELDS, "nombre": limit}))
        by_siren = {u["siren"]: u for u in units}
        return [_candidate(by_siren[e["siren"]], e) for e in rows if e.get("siren") in by_siren][:limit]
    offices = head_offices(sirens)
    return [_candidate(u, offices.get(u["siren"])) for u in units]
