"""Construit data/insee/*.json depuis les fichiers de nomenclature publiés par l'INSEE (lot G3).

    python scripts/build_insee_nomenclatures.py cj <fichier> [--source URL]      # catégories juridiques (niveau III)
    python scripts/build_insee_nomenclatures.py naf_rev2 <fichier> [--source URL]
    python scripts/build_insee_nomenclatures.py naf_2025 <fichier> [--source URL]

Fichier .xls, .xlsx ou .csv tel que publié. Le script ne télécharge rien : il lit le fichier fourni,
repère dans chaque feuille les cellules qui ont la forme d'un code (4 chiffres ; « 68.20B ») et prend
le premier texte qui les suit sur la ligne comme libellé. Relançable ; la source et la date de
construction sont notées en tête du JSON.
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parents[1] / "data" / "insee"
KINDS = {
    "cj": ("categories_juridiques.json", re.compile(r"^\d{4}$"), "Catégories juridiques, niveau III"),
    "naf_rev2": ("naf_rev2.json", re.compile(r"^\d{2}\.?\d{2}[A-Z]$"), "NAF rév. 2, sous-classes"),
    "naf_2025": ("naf_2025.json", re.compile(r"^\d{2}\.?\d{2}[A-Z]$"), "NAF 2025, sous-classes"),
}


def _sheets(path: Path) -> list[pd.DataFrame]:
    if path.suffix.lower() == ".csv":
        for sep in (";", ",", "\t"):
            frame = pd.read_csv(path, sep=sep, dtype=str, header=None, encoding_errors="replace")
            if frame.shape[1] > 1:
                return [frame]
        return [frame]
    return list(pd.read_excel(path, sheet_name=None, dtype=str, header=None).values())


def extract(path: Path, pattern: re.Pattern) -> dict[str, str]:
    codes: dict[str, str] = {}
    for frame in _sheets(path):
        for row in frame.itertuples(index=False):
            cells = [str(c).strip() for c in row if isinstance(c, str) or (c == c and c is not None)]
            for i, cell in enumerate(cells):
                if pattern.match(cell):
                    label = next((c for c in cells[i + 1:] if c and not pattern.match(c) and c.lower() != "nan"), None)
                    if label:
                        codes.setdefault(cell.replace(".", ""), " ".join(label.split()))
                    break
    return dict(sorted(codes.items()))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("kind", choices=sorted(KINDS))
    parser.add_argument("file", type=Path)
    parser.add_argument("--source", default="", help="adresse de publication du fichier (notée dans le JSON)")
    args = parser.parse_args(argv)
    name, pattern, title = KINDS[args.kind]
    codes = extract(args.file, pattern)
    if not codes:
        sys.exit(f"Aucun code trouvé dans {args.file}.")
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {"title": title, "source": args.source or args.file.name, "built_at": date.today().isoformat(),
               "count": len(codes), "codes": codes}
    (OUT / name).write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{OUT / name} : {len(codes)} codes.")


if __name__ == "__main__":
    main()
