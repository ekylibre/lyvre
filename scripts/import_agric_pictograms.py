"""Génère frontend/src/components/pictograms.generated.ts à partir du jeu d'icônes agric (Ekylibre, licence MIT).

Lot NV4 (claudedocs/design_navigation.md § 5.2) : on n'embarque que la liste fermée PICTOGRAMS, sous forme de tracés
(`path`), sans police ni dépendance. Les polygones et rectangles sont convertis en tracés ; les formes blanches
(classe CSS `fill:#FFFFFF`) deviennent des découpes (masque), les formes `fill:none` sont ignorées.

Usage : python scripts/import_agric_pictograms.py [/chemin/vers/agric]
"""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend" / "src" / "components" / "pictograms.generated.ts"
DEFAULT_AGRIC = Path.home() / "projects" / "agric"

PICTOGRAMS = [
    "apple", "barn", "bee-hive", "corn", "cow", "farm", "farmer", "fertilization", "goat", "grape", "harvester",
    "harvesting", "horse", "land-parcels", "leaf", "milk", "pig", "plots-rpg", "plots-telepac", "seed", "seeding",
    "sheep", "silo", "sprayer", "spraying", "tractor", "tree", "vine", "wheat",
]
SVG_NS = "{http://www.w3.org/2000/svg}"


def _num(v: str) -> str:
    return re.sub(r"\s+", " ", v.strip())


def _shape_d(el) -> str | None:
    tag = el.tag.replace(SVG_NS, "")
    if tag == "path":
        return _num(el.get("d", ""))
    if tag == "polygon" or tag == "polyline":
        pts = re.findall(r"-?[\d.]+(?:e-?\d+)?", el.get("points", ""))
        pairs = [f"{pts[i]},{pts[i + 1]}" for i in range(0, len(pts) - 1, 2)]
        return "M" + " L".join(pairs) + (" Z" if tag == "polygon" else "")
    if tag == "rect":
        x, y = float(el.get("x", 0)), float(el.get("y", 0))
        w, h = float(el.get("width")), float(el.get("height"))
        return f"M{x:g},{y:g} h{w:g} v{h:g} h{-w:g} Z"
    return None


def _class_fills(root) -> dict[str, str]:
    fills = {}
    for style in root.iter(f"{SVG_NS}style"):
        for name, body in re.findall(r"\.([\w-]+)\s*\{([^}]*)\}", style.text or ""):
            m = re.search(r"fill\s*:\s*([^;]+)", body)
            if m:
                fills[name] = m.group(1).strip().lower()
    return fills


def parse(path: Path) -> dict:
    root = ET.parse(path).getroot()
    fills = _class_fills(root)
    shapes, cuts = [], []
    for el in root.iter():
        d = _shape_d(el)
        if not d:
            continue
        fill = (el.get("fill") or fills.get(el.get("class", ""), "")).lower()
        if fill == "none":
            continue
        (cuts if fill in ("#fff", "#ffffff", "white") else shapes).append(d)
    return {"viewBox": _num(root.get("viewBox", "0 0 1000 1000")), "paths": shapes, "cuts": cuts}


def main(agric: Path) -> None:
    glyphs = agric / "glyphs"
    data = {name: parse(glyphs / f"{name}.svg") for name in PICTOGRAMS}
    lines = [
        "// Fichier généré par scripts/import_agric_pictograms.py : ne pas modifier à la main.",
        "// Pictogrammes issus d'agric (https://github.com/ekylibre/agric), © 2013 Brice Texier, licence MIT.",
        "export interface PictogramData { viewBox: string; paths: string[]; cuts: string[] }",
        "",
        "export const PICTOGRAMS: Record<string, PictogramData> = {",
    ]
    for name, p in data.items():
        lines.append(f'  "{name}": {{')
        lines.append(f'    viewBox: "{p["viewBox"]}",')
        lines.append("    paths: [" + ", ".join(f'"{d}"' for d in p["paths"]) + "],")
        lines.append("    cuts: [" + ", ".join(f'"{d}"' for d in p["cuts"]) + "],")
        lines.append("  },")
    lines.append("};")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(data)} pictogrammes écrits dans {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_AGRIC)
