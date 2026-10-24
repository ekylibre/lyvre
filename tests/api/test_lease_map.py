"""Lot L3 : carte des biens — couches IGN et fiche Lexicon (faux services, aucun appel réel),
géométrie des lignes, image figée (projection, réemploi, photo indisponible), carte dans le PDF."""
from datetime import date
from io import BytesIO

import pytest
from PIL import Image
from pypdf import PdfReader

from app.extensions import db
from app.models import Lease
from app.services import geodata, lease_documents, lease_map
from test_lease_wizard import _tenant, admin  # noqa: F401  (fixture)

API = "/api/v1/leases"
# Parcelle AH 248 simplifiée (carré d'environ 75 m de côté) et un bâtiment dedans.
SQUARE = {"type": "Polygon", "coordinates": [[[-0.7840, 45.8270], [-0.7830, 45.8270], [-0.7830, 45.8277],
                                               [-0.7840, 45.8277], [-0.7840, 45.8270]]]}
BUILDING = {"type": "Polygon", "coordinates": [[[-0.7838, 45.8272], [-0.7836, 45.8272], [-0.7836, 45.8273],
                                                 [-0.7838, 45.8273], [-0.7838, 45.8272]]]}
WFS_PARCELS = {"features": [{"geometry": SQUARE, "properties": {"idu": "17387000AH0248", "code_insee": "17387",
                                                                 "nom_com": "Saint-Porchaire", "contenance": 5619}}]}
WFS_BUILDINGS = {"features": [{"geometry": BUILDING, "properties": {"cleabs": "BATIMENT01", "nature": "Indifférenciée",
                                                                     "usage_1": "Agricole", "hauteur": 6}}]}
LEXICON = {"cadastre": {"id": {"value": "17387000AH0248"}, "area": {"value": 5619}, "buildings": {"value": 2},
                        "buildings-ground-area": {"value": 155}},
           "information": {"city": {"value": "ST PORCHAIRE"}}, "geolocation": {"shape": SQUARE}}
GEOCODE = {"features": [{"geometry": {"coordinates": [-0.783794, 45.827801]},
                         "properties": {"label": "1 Rue des Exemples 17250 Saint-Porchaire", "score": 0.95,
                                        "citycode": "17387"}}]}


@pytest.fixture()
def services(app, monkeypatch, tmp_path):
    """Faux IGN, Lexicon et WMS ; pièces de l'instance dans un dossier temporaire."""
    monkeypatch.setattr(app, "instance_path", str(tmp_path))
    calls = {"fetch": [], "photo": 0, "down": False}

    def fetch_json(url, params, service):
        calls["fetch"].append((url, params))
        if calls["down"]:
            raise geodata.GeoUnavailable(service)
        if "geocodage" in url:
            return GEOCODE
        if "lexicon" in url:
            return LEXICON
        if params.get("TYPENAMES") == geodata.BUILDING_LAYER:
            return WFS_BUILDINGS
        return WFS_PARCELS

    def fetch_image(params):
        calls["photo"] += 1
        return None if calls["down"] else Image.new("RGB", (params["WIDTH"], params["HEIGHT"]), (40, 120, 40))

    monkeypatch.setattr(geodata, "fetch_json", fetch_json)
    monkeypatch.setattr(lease_map, "fetch_image", fetch_image)
    return calls


def test_layers_parcel_card_and_center(admin, services):  # noqa: F811
    bbox = "-0.7870,45.8255,-0.7800,45.8295"
    parcels = admin.get(f"/api/v1/geo/parcels?bbox={bbox}").get_json()
    assert parcels["features"][0]["properties"] == {"idu": "17387000AH0248", "ref": "AH 248", "insee": "17387",
                                                     "commune": "Saint-Porchaire", "area_m2": 5619}
    assert services["fetch"][-1][1]["BBOX"].startswith("45.825500,-0.787000,45.829500,-0.780000")  # latitude d'abord
    assert admin.get(f"/api/v1/geo/buildings?bbox={bbox}").get_json()["features"][0]["properties"]["usage"] == "Agricole"
    card = admin.get("/api/v1/geo/parcel?lat=45.8272&lon=-0.7838").get_json()["item"]
    assert (card["ref"], card["area_m2"], card["buildings_area_m2"]) == ("AH 248", 5619, 155)
    assert admin.get("/api/v1/geo/parcel?ref=17387000AH0248").get_json()["item"]["properties"]["ref"] == "AH 248"
    assert admin.get("/api/v1/geo/parcel?ref=AH248").status_code == 422
    assert admin.get("/api/v1/geo/parcels?bbox=0,0,1,1").status_code == 422  # trop grand
    center = admin.get("/api/v1/geo/organization").get_json()["center"]
    assert (center["lat"], center["insee"], center["zoom"]) == (45.827801, "17387", 17)

    services["down"] = True
    resp = admin.get(f"/api/v1/geo/parcels?bbox={bbox}")
    assert resp.status_code == 503 and "ne répond pas" in resp.get_json()["error"]["message"]
    assert admin.get("/api/v1/geo/organization").get_json()["center"]["label"] == "France"


def _lease_with_zones(admin):  # noqa: F811
    lease = admin.post(API, json={"draft": True, "entity_id": _tenant().id, "unit_label": "La Vauzelle",
                                  "kind": "derogatory", "start_date": date.today().isoformat()}).get_json()["item"]
    land = admin.post(f"{API}/{lease['id']}/items", json={
        "label": "Potager", "nature": "land", "area_m2": 5619, "unit_price": "140", "cadastral_refs": ["AH 248"],
        "geometry": SQUARE, "source": "parcels"})
    assert land.status_code == 201, land.get_json()
    admin.post(f"{API}/{lease['id']}/items", json={"label": "Bureau", "nature": "building", "area_m2": 40,
                                                   "unit_price": "2", "geometry": BUILDING, "source": "buildings"})
    return lease["id"]


def test_item_geometry_is_checked(admin, services):  # noqa: F811
    lease_id = _lease_with_zones(admin)
    items = admin.get(f"{API}/{lease_id}").get_json()["item"]["items"]
    assert [(i["source"], i["has_geometry"]) for i in items] == [("parcels", True), ("buildings", True)]
    for bad in ({"type": "Point", "coordinates": [0, 0]}, {"type": "Polygon", "coordinates": [[[0, 0], [1, 1]]]},
                {"type": "Polygon", "coordinates": [[[0, 95], [1, 1], [2, 2], [0, 95]]]}, "x"):
        resp = admin.post(f"{API}/{lease_id}/items", json={"label": "Mauvais", "geometry": bad})
        assert resp.status_code == 422, bad
    assert admin.post(f"{API}/{lease_id}/items", json={"label": "X", "geometry": SQUARE, "source": "?"}).status_code == 422


def test_map_image_rendered_once_and_in_pdf(admin, services):  # noqa: F811
    lease_id = _lease_with_zones(admin)
    lease = db.session.get(Lease, lease_id)
    name = lease_map.render(lease)
    assert name and name == lease_map.render(lease) and services["photo"] == 1  # réemployée
    image = Image.open(lease_map.folder(lease) / name)
    assert image.width == lease_map.WIDTH and lease_map.MIN_HEIGHT <= image.height <= lease_map.MAX_HEIGHT
    minx, miny, maxx, maxy, width, height = lease_map.frame(
        [lease_map._polygons(i.geometry)[0] for i in lease.items])
    x, y = lease_map.mercator(-0.78325, 45.82750)  # dans la parcelle, hors du bâtiment
    inside = image.getpixel((int((x - minx) / (maxx - minx) * width), int((maxy - y) / (maxy - miny) * height)))
    assert inside[2] > inside[1]  # zone teintée de bleu sur la photo verte
    assert image.getpixel((5, 5)) == (40, 120, 40)  # marge : photo seule

    admin.post(f"{API}/{lease_id}/activate", json={"frequency": "yearly"})
    text = db.session.get(Lease, lease_id).document_html
    assert f'<img class="map" src="lease-map:{name}">' in text
    pdf = PdfReader(BytesIO(admin.get(f"{API}/{lease_id}/preview.pdf").data))
    assert {img.name for page in pdf.pages for img in page.images} and len(pdf.pages[0].images) == 1

    # Retouche : la carte du bail reste, toute autre image est retirée.
    body = text + '<p><img src="http://exemple.org/x.png"><img src="lease-map:../../secret.png"></p>'
    admin.put(f"{API}/{lease_id}/document", json={"body_html": body})
    kept = db.session.get(Lease, lease_id).document_html
    assert kept.count("<img") == 1 and "exemple.org" not in kept


def test_map_without_photo_and_without_zones(admin, services):  # noqa: F811
    lease_id = _lease_with_zones(admin)
    services["down"] = True
    lease = db.session.get(Lease, lease_id)
    name = lease_map.render(lease)
    assert Image.open(lease_map.folder(lease) / name).getpixel((5, 5)) == lease_map.BACKGROUND
    plain = admin.post(API, json={"draft": True, "entity_id": _tenant().id, "unit_label": "Maison", "kind": "residential",
                                  "start_date": date.today().isoformat()}).get_json()["item"]
    admin.post(f"{API}/{plain['id']}/items", json={"label": "Maison", "nature": "flat", "unit_price": "9600"})
    assert lease_map.render(db.session.get(Lease, plain["id"])) is None
    assert lease_documents.context(db.session.get(Lease, plain["id"]))["biens"]["carte"] == ""
