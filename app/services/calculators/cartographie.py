"""Calculettes 04 (carte RPG) et 07 (zonages d'une parcelle), lot AG12.d : point choisi sur la carte, données de l'IGN et
du Sandre (`agri_geo`, sans clé). Le résultat porte une carte (`Result.map`) en plus du gabarit commun."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from app.services import agri_geo
from app.services.calculators import CalculatorError, Input, Result, Spec, Tool, number
from app.services.geodata import GeoUnavailable

GROUP_COLORS = ("#c8a03c", "#5b8c3a", "#3a6f8c", "#8c3a6f", "#c86e3c", "#6f8c3a", "#3a8c7a", "#8c7a3a")


def _point(v) -> tuple[float, float]:
    return v["point"]


def rpg(v, on):
    lat, lon = _point(v)
    radius = v["radius"] or 300
    if not 50 <= radius <= agri_geo.MAX_RADIUS_M:
        raise CalculatorError(f"Rayon entre 50 et {agri_geo.MAX_RADIUS_M} m.", "radius")
    try:
        features, labels = agri_geo.rpg_around(lat, lon, radius), agri_geo.crop_labels()
    except GeoUnavailable as exc:
        raise CalculatorError(exc.message, status=503) from None
    crops: dict[str, dict] = defaultdict(lambda: {"count": 0, "ha": Decimal(0)})
    groups, under = {}, None
    for f in features:
        p = f.get("properties") or {}
        code = p.get("code_cultu") or "?"
        label, group = labels.get(code, (code, ""))
        crops[code]["count"] += 1
        crops[code]["ha"] += Decimal(str(p.get("surf_parc") or 0))
        crops[code].update(label=label, group=group)
        color = groups.setdefault(group, GROUP_COLORS[len(groups) % len(GROUP_COLORS)])
        p.update(label=f"{label} — {p.get('surf_parc')} ha", color=color)
        if under is None and agri_geo.point_in(f.get("geometry"), lat, lon):
            under = f"{label} ({p.get('surf_parc')} ha)"
    rows = sorted(crops.items(), key=lambda kv: -kv[1]["ha"])
    total = sum((c["ha"] for _, c in rows), Decimal(0))
    warnings = []
    if len(features) >= agri_geo.MAX_PARCELS:
        warnings.append(f"Plus de {agri_geo.MAX_PARCELS} parcelles : réduisez le rayon.")
    if not features:
        warnings.append("Aucune parcelle déclarée autour de ce point (RPG).")
    return Result(headline=[("Parcelle sous le point", under or "aucune"), ("Parcelles autour", str(len(features))),
                            ("Surface déclarée", number(total, 2) + " ha")],
                  table={"columns": ["Culture", "Groupe", "Parcelles", "Surface (ha)"],
                         "rows": [[c["label"], c["group"], c["count"], number(c["ha"], 2)] for _, c in rows]},
                  warnings=warnings,
                  map={"center": [lat, lon], "zoom": 16 if radius <= 400 else 15,
                       "features": {"type": "FeatureCollection", "features": features}})


def zonings(v, on):
    lat, lon = _point(v)
    try:
        found = agri_geo.zonings_at(lat, lon)
    except GeoUnavailable as exc:
        raise CalculatorError(exc.message, status=503) from None
    inside = [z for z in found if z["inside"]]
    rows = [[z["label"], "à vérifier" if z.get("status") == "unknown" else "oui" if z["inside"] else "non",
             "; ".join(" ".join(x for x in (i["name"], f"({i['code']})" if i["code"] and i["code"] != i["name"] else "",
                                             i["note"] or "") if x) for i in z["items"])] for z in found]
    links = [(f"Fiche {i['code'] or i['name']}", i["url"]) for z in found for i in z["items"] if i.get("url")]
    return Result(headline=[("Zonages au point", str(len(inside))),
                            ("Zone vulnérable aux nitrates", "oui" if found[0]["inside"] else "non")],
                  table={"columns": ["Zonage", "Au point", "Détail"], "rows": rows},
                  details=[(label, url) for label, url in links],
                  warnings=["Zonages publiés (IGN, Sandre, DDT) à la date de la consultation : les obligations qui en "
                            "découlent (programme d'actions nitrates, document d'objectifs Natura 2000, BCAE, ICHN) se lisent "
                            "dans les textes. Zones défavorisées : seulement dans les 13 départements dont la DDT publie un "
                            "zonage postérieur à 2019, à confirmer avec elle (arrêtés modificatifs de 2023 et 2026)."],
                  map={"center": [lat, lon], "zoom": 15, "features": None})


POINT = Input("point", "Point sur la carte", "point", help="Cliquez sur la carte (latitude, longitude)")

TOOLS = [
    Tool(Spec(code="rpg", number="04", title="Carte RPG autour d'une parcelle", category="crops",
              summary="Parcelles déclarées à la PAC et leurs cultures autour d'un point (registre parcellaire graphique).",
              inputs=[POINT, Input("radius", "Rayon", "integer", "m", False, default="300")],
              example={"point": "45.8295,-0.7870", "radius": "300"},
              method="Parcelles du registre parcellaire graphique (RPG, dernière édition publiée par l'IGN) qui touchent le "
                     "carré de côté deux fois le rayon autour du point, avec leur code culture et leur surface déclarée ; "
                     "libellés des cultures de la nomenclature du RPG. Limites : données anonymes publiées avec un an de "
                     "décalage environ ; la surface est celle déclarée, pas la surface cadastrale.",
              sources=(("RPG — IGN (Géoplateforme)", "https://geoservices.ign.fr/rpg"),)), rpg),
    Tool(Spec(code="zonages", number="07", title="Zonages de ma parcelle", category="regulatory",
              summary="Zone vulnérable aux nitrates, Natura 2000 et zones BCAE au point choisi.",
              inputs=[POINT], example={"point": "45.8295,-0.7870"},
              method="Le point est comparé aux zonages publiés : zones vulnérables aux nitrates (Sandre, délimitation en "
                     "vigueur), sites Natura 2000 (INPN par l'IGN), couches BCAE de l'IGN (prairies sensibles, zones humides "
                     "et tourbières ; cours d'eau dans un rayon d'environ 50 m), zones agricoles défavorisées publiées par "
                     "la DDT du département (13 départements, data.gouv.fr). Limites : précision de quelques mètres aux "
                     "limites d'une zone ; département de la parcelle cadastrale la plus proche ; zonage ICHN à confirmer avec "
                     "la DDT, et « à vérifier » hors des départements couverts.",
              sources=(("Zones vulnérables — Sandre", "https://services.sandre.eaufrance.fr/geo/zrpe"),
                       ("Natura 2000 — INPN", "https://inpn.mnhn.fr/programme/natura2000"),
                       ("Géoplateforme IGN", "https://data.geopf.fr/wfs/ows"),
                       ("Zones défavorisées — ministère de l'Agriculture",
                        "https://agriculture.gouv.fr/aides-aux-exploitations-classement-en-zone-defavorisee"))), zonings),
]
