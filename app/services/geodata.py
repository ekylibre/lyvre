"""Données géographiques des baux (lot L3, décisions BX1, BX2, L-C3, L-C4).

- Couches affichées sur la carte, par emprise : parcelles cadastrales (IGN, Parcellaire Express) et
  bâtiments (IGN, BD TOPO), WFS de la Géoplateforme, public, sans clé.
- Fiche de la parcelle cliquée : **Lexicon** (`tools/parcel-identifier.json`) — surface officielle,
  nombre et emprise au sol des bâtiments, commune ; même identifiant de parcelle que l'IGN.
- Centre de la carte : géocodage IGN de l'adresse de la structure (mis en cache sur l'organisation).

Seules des coordonnées, emprises et références cadastrales sortent de Lyvre. Délai borné, petit
cache mémoire ; un service qui ne répond pas lève `GeoUnavailable` (message lisible). Les tests
remplacent `fetch_json` : aucun appel réel.
"""
from __future__ import annotations

import re
import time

import requests

TIMEOUT = 10  # secondes
CACHE_SECONDS = 15 * 60
MAX_BBOX_DEGREES = 0.03  # environ 2 à 3 km de côté
IGN_WFS = "https://data.geopf.fr/wfs/ows"
IGN_GEOCODE = "https://data.geopf.fr/geocodage/search"
LEXICON = "https://lexicon.osfarm.org"
PARCEL_LAYER = "CADASTRALPARCELS.PARCELLAIRE_EXPRESS:parcelle"
BUILDING_LAYER = "BDTOPO_V3:batiment"
IDU = re.compile(r"^\d{5}[0-9A-Z]{3}[0-9A-Z]{2}\d{4}$")

_cache: dict[str, tuple[float, object]] = {}


class GeoUnavailable(RuntimeError):
    def __init__(self, service: str):
        super().__init__(f"{service} ne répond pas : réessayez plus tard, ou saisissez les biens sans carte.")
        self.message = str(self)


def fetch_json(url: str, params: dict, service: str):
    """GET JSON avec délai borné et cache ; `GeoUnavailable` si le service ne répond pas."""
    key = url + "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    try:
        response = requests.get(url, params=params, timeout=TIMEOUT, headers={"Accept": "application/json"})
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        raise GeoUnavailable(service) from None
    if len(_cache) > 500:
        _cache.clear()
    _cache[key] = (time.monotonic(), data)
    return data


def parse_bbox(value: str) -> tuple[float, float, float, float]:
    """`ouest,sud,est,nord` en degrés (WGS84), emprise limitée."""
    try:
        west, south, east, north = (float(v) for v in str(value).split(","))
    except ValueError:
        raise ValueError("Emprise attendue : ouest,sud,est,nord.") from None
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("Emprise invalide.")
    if east - west > MAX_BBOX_DEGREES or north - south > MAX_BBOX_DEGREES:
        raise ValueError("Zone trop grande : rapprochez-vous pour afficher les parcelles.")
    return west, south, east, north


def _wfs(layer: str, bbox, service: str) -> list[dict]:
    west, south, east, north = bbox
    data = fetch_json(IGN_WFS, {
        "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "TYPENAMES": layer,
        "OUTPUTFORMAT": "application/json", "COUNT": 2000, "SRSNAME": "EPSG:4326",
        # WFS 2.0 en EPSG:4326 : latitude d'abord.
        "BBOX": f"{south:.6f},{west:.6f},{north:.6f},{east:.6f},urn:ogc:def:crs:EPSG::4326",
    }, service)
    return data.get("features") or []


def short_ref(idu: str) -> str:
    """17387000AH0248 → « AH 248 »."""
    return f"{idu[8:10].lstrip('0') or '0'} {int(idu[10:])}" if IDU.match(idu or "") else idu


def parcels(bbox) -> dict:
    features = []
    for f in _wfs(PARCEL_LAYER, bbox, "Le cadastre de l'IGN"):
        p = f.get("properties") or {}
        idu = p.get("idu")
        if not idu or not f.get("geometry"):
            continue
        features.append({"type": "Feature", "id": idu, "geometry": f["geometry"],
                         "properties": {"idu": idu, "ref": short_ref(idu), "insee": p.get("code_insee"),
                                        "commune": p.get("nom_com"), "area_m2": p.get("contenance")}})
    return {"type": "FeatureCollection", "features": features}


def buildings(bbox) -> dict:
    features = []
    for f in _wfs(BUILDING_LAYER, bbox, "La BD TOPO de l'IGN"):
        p = f.get("properties") or {}
        if not f.get("geometry"):
            continue
        features.append({"type": "Feature", "id": p.get("cleabs") or f.get("id"), "geometry": f["geometry"],
                         "properties": {"id": p.get("cleabs") or f.get("id"), "nature": p.get("nature"),
                                        "usage": p.get("usage_1"), "height": p.get("hauteur")}})
    return {"type": "FeatureCollection", "features": features}


def _value(section: dict | None, key: str):
    item = (section or {}).get(key) or {}
    return item.get("value") if isinstance(item, dict) else None


def parcel_at(lat: float, lon: float) -> dict | None:
    """Fiche Lexicon de la parcelle au point : identifiant, référence, surface, bâtiments, commune."""
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Coordonnées invalides.")
    data = fetch_json(f"{LEXICON}/tools/parcel-identifier.json",
                      {"latitude": f"{lat:.6f}", "longitude": f"{lon:.6f}"}, "Lexicon")
    cadastre = data.get("cadastre") or {}
    idu = _value(cadastre, "id")
    if not idu:
        return None
    return {"idu": idu, "ref": short_ref(idu), "area_m2": _value(cadastre, "area"),
            "buildings": _value(cadastre, "buildings") or 0,
            "buildings_area_m2": _value(cadastre, "buildings-ground-area") or 0,
            "commune": _value(data.get("information"), "city"),
            "geometry": ((data.get("geolocation") or {}).get("shape"))}


def parcel_by_ref(idu: str) -> dict | None:
    """Parcelle par identifiant (17387000AH0248) : contour IGN (ajout hors carte, NF5)."""
    idu = (idu or "").strip().upper()
    if not IDU.match(idu):
        raise ValueError("Référence cadastrale attendue : code commune, préfixe, section et numéro (17387000AH0248).")
    data = fetch_json(IGN_WFS, {
        "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "TYPENAMES": PARCEL_LAYER,
        "OUTPUTFORMAT": "application/json", "SRSNAME": "EPSG:4326", "CQL_FILTER": f"idu='{idu}'",
    }, "Le cadastre de l'IGN")
    feature = next(iter(data.get("features") or []), None)
    if feature is None:
        return None
    p = feature.get("properties") or {}
    return {"type": "Feature", "id": idu, "geometry": feature.get("geometry"),
            "properties": {"idu": idu, "ref": short_ref(idu), "insee": p.get("code_insee"),
                           "commune": p.get("nom_com"), "area_m2": p.get("contenance")}}


def geocode(address: str) -> dict | None:
    if not (address or "").strip():
        return None
    data = fetch_json(IGN_GEOCODE, {"q": address.strip()[:200], "limit": 1}, "Le géocodage de l'IGN")
    feature = next(iter(data.get("features") or []), None)
    if feature is None:
        return None
    lon, lat = feature["geometry"]["coordinates"]
    props = feature.get("properties") or {}
    return {"lat": lat, "lon": lon, "label": props.get("label"), "score": props.get("score"),
            "insee": props.get("citycode")}
