"""Données géographiques des calculettes 04 (carte RPG) et 07 (zonages d'une parcelle), lot AG12.d.

Sources vérifiées le 07/11/2026 (claudedocs/design_calculettes_agricoles.md § 10), publiques et sans clé :
- **IGN Géoplateforme**, WFS `https://data.geopf.fr/wfs/ows` (GeoJSON) :
  - `RPG.LATEST:parcelles_graphiques` (parcelles déclarées, code culture, surface) et `RPG.LATEST:codes_cultures` ;
  - Natura 2000 : `patrinat_sic:sic` (directive Habitats), `patrinat_zps:zps` (directive Oiseaux) ;
  - BCAE : `PRAIRIES.SENSIBLES.BCAE:prairies_sensibles`, `TOURBIERES_ZONES-HUMIDES.BCAE:bcae`,
    `HYDROGRAPHY.BCAE.LATEST:bcae_cours_eau` (lignes : cours d'eau à proximité).
  Requête par emprise (WFS 2.0, `urn:ogc:def:crs:EPSG::4326`, ordre latitude, longitude) : un très petit carré autour
  du point pour les zonages (le filtre « point » ne répond pas sur les couches Natura 2000).
- **Sandre**, WFS `https://services.sandre.eaufrance.fr/geo/zrpe` (GML seulement) : zones vulnérables aux nitrates
  `sa:ZoneVuln_delimitation_FXX`, filtre « point dans la zone » et attributs seuls (la géométrie d'une zone pèse
  plusieurs Mo).

Seules des coordonnées sortent de Lyvre. Délai borné, cache mémoire (`geodata.fetch_json`) ; un service qui ne répond
pas lève `GeoUnavailable`. Les tests remplacent `_ign` et `_sandre` : aucun appel réel.
"""
from __future__ import annotations

import math
import time
import xml.etree.ElementTree as ET
from urllib.parse import quote

import requests

from app.services.geodata import CACHE_SECONDS, TIMEOUT, GeoUnavailable, fetch_json

IGN_WFS = "https://data.geopf.fr/wfs/ows"
SANDRE_WFS = "https://services.sandre.eaufrance.fr/geo/zrpe"
RPG_LAYER, CODES_LAYER = "RPG.LATEST:parcelles_graphiques", "RPG.LATEST:codes_cultures"
MAX_RADIUS_M = 1000
MAX_PARCELS = 400
POINT_TOLERANCE_M = 5          # carré de ± 5 m autour du point pour les zonages surfaciques
STREAM_DISTANCE_M = 50         # cours d'eau BCAE recherchés dans un carré de ± 50 m
ZONINGS = (
    ("natura_sic", "Natura 2000 — site d'importance communautaire (directive Habitats)", "patrinat_sic:sic"),
    ("natura_zps", "Natura 2000 — zone de protection spéciale (directive Oiseaux)", "patrinat_zps:zps"),
    ("bcae_prairies", "BCAE 9 — prairie permanente sensible en zone Natura 2000", "PRAIRIES.SENSIBLES.BCAE:prairies_sensibles"),
    ("bcae_wetlands", "BCAE 2 — zone humide ou tourbière", "TOURBIERES_ZONES-HUMIDES.BCAE:bcae"),
)
_xml_cache: dict[str, tuple[float, str]] = {}


def _box(lat: float, lon: float, metres: float) -> str:
    dlat = metres / 111_320
    dlon = metres / (111_320 * max(math.cos(math.radians(lat)), 0.01))
    return f"{lat - dlat},{lon - dlon},{lat + dlat},{lon + dlon},urn:ogc:def:crs:EPSG::4326"


def _ign(layer: str, params: dict) -> dict:
    query = {"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "TYPENAMES": layer,
             "OUTPUTFORMAT": "application/json", **params}
    return fetch_json(IGN_WFS, query, "Le service cartographique de l'IGN")


def _sandre(query: str) -> str:
    hit = _xml_cache.get(query)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    try:
        response = requests.get(f"{SANDRE_WFS}?{query}", timeout=TIMEOUT)
        response.raise_for_status()
    except requests.RequestException:
        raise GeoUnavailable("Le service du Sandre (zones vulnérables)") from None
    if len(response.content) > 2_000_000:
        raise GeoUnavailable("Le service du Sandre (zones vulnérables)")
    if len(_xml_cache) > 200:
        _xml_cache.clear()
    _xml_cache[query] = (time.monotonic(), response.text)
    return response.text


# ------------------------------------------------------------------ RPG (calculette 04)

def crop_labels() -> dict[str, tuple[str, str]]:
    data = _ign(CODES_LAYER, {"COUNT": 1000})
    return {f["properties"]["code_culture"]: (f["properties"].get("libelle_culture") or f["properties"]["code_culture"],
                                              f["properties"].get("libelle_groupe_culture") or "")
            for f in data.get("features") or [] if f.get("properties", {}).get("code_culture")}


def rpg_around(lat: float, lon: float, radius_m: int) -> list[dict]:
    """Parcelles déclarées touchant le carré de côté 2 × rayon autour du point (GeoJSON, WGS84)."""
    data = _ign(RPG_LAYER, {"COUNT": MAX_PARCELS, "SRSNAME": "EPSG:4326",
                            "BBOX": _box(lat, lon, min(max(radius_m, 10), MAX_RADIUS_M))})
    return data.get("features") or []


def point_in(geometry: dict | None, lat: float, lon: float) -> bool:
    """Point dans un (Multi)Polygon GeoJSON (règle pair-impair ; trous compris)."""
    if not geometry:
        return False
    polygons = geometry["coordinates"] if geometry.get("type") == "MultiPolygon" else [geometry.get("coordinates") or []]
    for polygon in polygons:
        inside = False
        for ring in polygon:
            for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
                if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
                    inside = not inside
        if inside:
            return True
    return False


# ------------------------------------------------------------------ zonages (calculette 07)

def vulnerable_zone(lat: float, lon: float) -> dict | None:
    """Zone vulnérable aux nitrates contenant le point (Sandre), ou None."""
    flt = ('<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0" xmlns:gml="http://www.opengis.net/gml/3.2">'
           '<fes:Intersects><fes:ValueReference>msGeometry</fes:ValueReference>'
           f'<gml:Point srsName="urn:ogc:def:crs:EPSG::4326"><gml:pos>{lat} {lon}</gml:pos></gml:Point>'
           '</fes:Intersects></fes:Filter>')
    query = ("SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=sa:ZoneVuln_delimitation_FXX&COUNT=5"
             "&PROPERTYNAME=CdEuZoneVuln,NomZoneVuln,NumTexteReglem,DatePubliTexteReglem,URLTexteReglem"
             f"&FILTER={quote(flt)}")
    return parse_vulnerable(_sandre(query))


def parse_vulnerable(text: str) -> dict | None:
    try:
        root = ET.fromstring(text.encode())
    except ET.ParseError:
        raise GeoUnavailable("Le service du Sandre (zones vulnérables)") from None
    if root.tag.endswith("ExceptionReport"):
        raise GeoUnavailable("Le service du Sandre (zones vulnérables)")
    for member in root.iter():
        if member.tag.endswith("ZoneVuln_delimitation_FXX"):
            values = {child.tag.rsplit("}", 1)[-1]: (child.text or "").strip() for child in member}
            return {"code": values.get("CdEuZoneVuln") or None, "name": values.get("NomZoneVuln") or None,
                    "act": values.get("NumTexteReglem") or None, "act_date": values.get("DatePubliTexteReglem") or None,
                    "url": values.get("URLTexteReglem") or None}
    return None


def zonings_at(lat: float, lon: float) -> list[dict]:
    """Zonages au point : [{key, label, inside, items: [{name, code, url}]}] (Sandre, puis IGN)."""
    out = []
    zone = vulnerable_zone(lat, lon)
    out.append({"key": "nitrates", "label": "Zone vulnérable aux nitrates", "inside": zone is not None,
                "items": [{"name": zone["name"] or zone["code"], "code": zone["code"], "url": zone["url"],
                           "note": f"arrêté {zone['act']}" if zone["act"] else None}] if zone else []})
    for key, label, layer in ZONINGS:
        data = _ign(layer, {"COUNT": 10, "SRSNAME": "EPSG:4326", "BBOX": _box(lat, lon, POINT_TOLERANCE_M)})
        items = []
        for feature in data.get("features") or []:
            p = feature.get("properties") or {}
            items.append({"name": p.get("nom_site") or p.get("nom") or label, "code": p.get("id_mnhn") or p.get("code"),
                          "url": p.get("url_fiche"), "note": None})
        out.append({"key": key, "label": label, "inside": bool(items), "items": items})
    streams = _ign("HYDROGRAPHY.BCAE.LATEST:bcae_cours_eau",
                   {"COUNT": 10, "SRSNAME": "EPSG:4326", "BBOX": _box(lat, lon, STREAM_DISTANCE_M)})
    count = len(streams.get("features") or [])
    out.append({"key": "bcae_streams", "label": f"BCAE 4 — cours d'eau à moins d'environ {STREAM_DISTANCE_M} m (bande tampon)",
                "inside": bool(count), "items": [{"name": f"{count} tronçon(s) de cours d'eau BCAE", "code": None,
                                                  "url": None, "note": None}] if count else []})
    return out
