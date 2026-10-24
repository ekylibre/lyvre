"""Carte figée d'un bail (lot L3, décision L-C6) : photo aérienne IGN (WMS de la Géoplateforme) sur
l'emprise des lignes du bail, zones dessinées et lettrées avec Pillow, mention « © IGN ».

L'image est rangée sous `instance_dir()/baux/<bail>/carte-<empreinte>.png` : l'empreinte vient des
géométries et des lettres, une image n'est refaite que si elles changent, et un texte de bail figé
garde l'image qu'il cite. Photo indisponible : les zones seules sur fond clair (NF3).
"""
from __future__ import annotations

import hashlib
import io
import json
import math
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

from app.models import Lease
from app.services.attachments import instance_dir

WMS = "https://data.geopf.fr/wms-r"
WIDTH = 1600
MIN_HEIGHT, MAX_HEIGHT = 600, 1100
MARGIN = 0.15
EARTH = 6378137.0
FILL, OUTLINE, BACKGROUND = (70, 80, 200, 105), (40, 50, 170, 255), (232, 236, 226)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def mercator(lon: float, lat: float) -> tuple[float, float]:
    """WGS84 → Web Mercator (EPSG:3857), en mètres."""
    lat = max(min(lat, 85.0), -85.0)
    return EARTH * math.radians(lon), EARTH * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def _polygons(geometry: dict | None) -> list[list[list[float]]]:
    """Anneaux extérieurs d'un Polygon / MultiPolygon (les trous sont ignorés sur l'image)."""
    if not geometry:
        return []
    if geometry.get("type") == "Polygon":
        return [geometry["coordinates"][0]]
    if geometry.get("type") == "MultiPolygon":
        return [poly[0] for poly in geometry["coordinates"]]
    return []


def fingerprint(lease: Lease) -> str | None:
    shapes = [(i.letter or "", i.geometry) for i in lease.items if _polygons(i.geometry)]
    if not shapes:
        return None
    return hashlib.sha256(json.dumps(shapes, sort_keys=True).encode()).hexdigest()[:12]


def folder(lease: Lease) -> Path:
    return instance_dir() / "baux" / str(lease.id)


def frame(rings: list[list[list[float]]]) -> tuple[float, float, float, float, int, int]:
    """Emprise Web Mercator (marge comprise) et taille de l'image, au rapport de l'emprise."""
    xs, ys = zip(*(mercator(lon, lat) for ring in rings for lon, lat, *_ in ring))
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    dx, dy = max(maxx - minx, 20.0), max(maxy - miny, 20.0)
    minx, maxx = minx - dx * MARGIN, maxx + dx * MARGIN
    miny, maxy = miny - dy * MARGIN, maxy + dy * MARGIN
    height = round(WIDTH * (maxy - miny) / (maxx - minx))
    if not MIN_HEIGHT <= height <= MAX_HEIGHT:
        height = min(max(height, MIN_HEIGHT), MAX_HEIGHT)
        # Emprise élargie dans le sens qui manque, pour garder des pixels carrés.
        cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
        width_m, height_m = maxx - minx, maxy - miny
        if height_m / width_m < height / WIDTH:
            height_m = width_m * height / WIDTH
        else:
            width_m = height_m * WIDTH / height
        minx, maxx, miny, maxy = cx - width_m / 2, cx + width_m / 2, cy - height_m / 2, cy + height_m / 2
    return minx, miny, maxx, maxy, WIDTH, height


def fetch_image(params: dict) -> Image.Image | None:
    """Photo aérienne IGN de l'emprise ; None si le service ne répond pas."""
    try:
        response = requests.get(WMS, params=params, timeout=20)
        response.raise_for_status()
        return Image.open(io.BytesIO(response.content)).convert("RGB")
    except (requests.RequestException, OSError):
        return None


def _font(size: int):
    try:
        return ImageFont.truetype(FONT, size)
    except OSError:
        return ImageFont.load_default(size=size)


def render(lease: Lease) -> str | None:
    """Image de la carte du bail (nom du fichier), refaite seulement si les zones ont changé ; None
    si aucune ligne n'a de géométrie."""
    key = fingerprint(lease)
    if key is None:
        return None
    name = f"carte-{key}.png"
    path = folder(lease) / name
    if path.exists():
        return name
    shapes = [(item.letter or "", _polygons(item.geometry)) for item in lease.items if _polygons(item.geometry)]
    minx, miny, maxx, maxy, width, height = frame([ring for _l, rings in shapes for ring in rings])
    photo = fetch_image({
        "SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap", "LAYERS": "ORTHOIMAGERY.ORTHOPHOTOS",
        "STYLES": "", "CRS": "EPSG:3857", "BBOX": f"{minx:.2f},{miny:.2f},{maxx:.2f},{maxy:.2f}",
        "WIDTH": width, "HEIGHT": height, "FORMAT": "image/jpeg"})
    base = (photo.resize((width, height)) if photo is not None else Image.new("RGB", (width, height), BACKGROUND)).convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    def pixel(lon, lat):
        x, y = mercator(lon, lat)
        return (x - minx) / (maxx - minx) * width, (maxy - y) / (maxy - miny) * height

    labels = []
    for letter, rings in shapes:
        largest = max(rings, key=len)
        for ring in rings:
            draw.polygon([pixel(lon, lat) for lon, lat, *_ in ring], fill=FILL, outline=OUTLINE, width=3)
        points = [pixel(lon, lat) for lon, lat, *_ in largest]
        labels.append((letter, sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points)))
    image = Image.alpha_composite(base, overlay)
    draw = ImageDraw.Draw(image)
    font = _font(46)
    for letter, x, y in labels:
        if letter:
            draw.text((x, y), letter, font=font, fill=(255, 255, 255, 255), anchor="mm",
                      stroke_width=4, stroke_fill=(20, 25, 90, 255))
    credit = "© IGN — Géoplateforme" if photo is not None else "Photo aérienne indisponible — © IGN"
    draw.text((width - 12, height - 10), credit, font=_font(20), fill=(255, 255, 255, 255), anchor="rd",
              stroke_width=2, stroke_fill=(0, 0, 0, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(path, "PNG", optimize=True)
    return name
