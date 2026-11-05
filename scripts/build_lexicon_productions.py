"""Extrait des productions de Lexicon pour l'analytique agricole (lot AG8.a, claudedocs/design_analytique_agricole.md § 3).

Lit le paquet public du jeu `productions` (tables `master_productions` et `productions__translations`) et écrit
`data/analytic/lexicon_productions.json` : référence, nom français, famille d'activités, usage, dates théoriques de
cycle (jour et mois, et décalage d'année), unité, durée de vie. Licence CC-BY-SA 4.0 (Ekylibre SAS), citée dans le fichier.

    python scripts/build_lexicon_productions.py [--version 2026.10.07.1]
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import urllib.request
from datetime import date
from pathlib import Path

BASE = "https://lexicon-packages.osfarm.org/productions"
OUT = Path(__file__).resolve().parents[1] / "data" / "analytic" / "lexicon_productions.json"
MP_COLUMNS = ["reference_name", "activity_family", "specie", "usage", "started_on", "stopped_on", "agroedi_crop_code",
              "season", "life_duration", "support_unit", "idea_botanic_family", "idea_specie_family",
              "idea_output_family", "color", "translation_id"]


def _rows(url: str) -> list[list[str]]:
    request = urllib.request.Request(url, headers={"User-Agent": "Lyvre"})
    with urllib.request.urlopen(request, timeout=60) as resp:  # noqa: S310 — paquet public de Lexicon
        text = gzip.decompress(resp.read()).decode("utf-8")
    return list(csv.reader(io.StringIO(text)))


def build(version: str) -> dict:
    data = f"{BASE}/{version}/data"
    names = {row[0]: row[1] for row in _rows(f"{data}/productions__translations_0.csv.gz") if len(row) >= 2}
    items = []
    for row in _rows(f"{data}/master_productions_0.csv.gz"):
        rec = dict(zip(MP_COLUMNS, row))
        start, stop = date.fromisoformat(rec["started_on"]), date.fromisoformat(rec["stopped_on"])
        items.append({"reference": rec["reference_name"], "name": names.get(rec["translation_id"], rec["reference_name"]),
                      "family": rec["activity_family"], "usage": rec["usage"] or None, "specie": rec["specie"] or None,
                      "start": start.strftime("%m-%d"), "stop": stop.strftime("%m-%d"),
                      "year_offset": stop.year - start.year, "life_duration": rec["life_duration"] or None,
                      "unit": rec["support_unit"]})
    items.sort(key=lambda i: (i["family"], i["name"]))
    return {"_source": {"dataset": "productions", "version": version, "url": f"{BASE}/{version}/",
                        "provider": "Ekylibre SAS (Lexicon)", "licence": "CC-BY-SA 4.0",
                        "licence_url": "https://creativecommons.org/licenses/by-sa/4.0/deed.fr"},
            "productions": items}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="2026.10.07.1")
    args = parser.parse_args()
    payload = build(args.version)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(payload['productions'])} productions → {OUT}")
