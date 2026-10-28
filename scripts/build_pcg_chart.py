"""Construit `data/plan_comptable_societe.json` à partir du PCG 2026 (référentiel `societe`, lot T1,
`claudedocs/design_societe_tva.md` § 3.1).

Lit la liste des comptes du règlement ANC (titre XI, chapitre II : pages 133 à 151 du PDF
`doc/ref_compta/PCG--1er-janvier-2026.pdf`) et écrit les comptes des classes 1 à 7 au format des
autres plans (`code`, `label`, `account_type`, `is_header` pour les seules classes). Exécuté une fois,
sortie versionnée et relue :

    .venv/bin/python scripts/build_pcg_chart.py [--pdf PCG.pdf] [--out data/plan_comptable_societe.json]
"""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "doc" / "ref_compta" / "PCG--1er-janvier-2026.pdf"
OUT = ROOT / "data" / "plan_comptable_societe.json"
FIRST_PAGE, LAST_PAGE = 133, 151  # numéros imprimés (1 = première page)

ACCOUNT_TYPES = {"1": "EQUITY", "2": "ASSET", "3": "ASSET", "4": "TIERS", "5": "ASSET",
                 "6": "EXPENSE", "7": "REVENUE"}
CLASS_LINE = re.compile(r"^CLASSE\s+([1-8])\s*:\s*(.+)$")
CODE_LINE = re.compile(r"^(\d{2,7})(?:\s+(.*))?$")
NOISE = re.compile(r"^(Version 1er janvier 2026|Page \d+ sur \d+|Chapitre .*|Art\. \d.*"
                   r"|61/62 Autres charges externes)$")  # titre de regroupement sans compte
# Fin de la liste des comptes : la suite de la page est du texte (articles sur la classe 8).
END_OF_LIST = re.compile(r"^Le plan de comptes est suffisamment détaillé")
# Comptes dont le PCG donne une note au lieu d'un intitulé, ou une plage (« 471 à 473 »).
LABELS = {
    "36": "Stocks provenant d'immobilisations",
    "38": "Stocks en voie d'acheminement, mis en dépôt ou donnés en consignation",
    "471": "Comptes d'attente",
    "608": "Frais accessoires incorporés aux achats",
    "672": "Charges sur exercices antérieurs",
    "772": "Produits sur exercices antérieurs",
}
# Sous-comptes que Lyvre utilise et que le PCG ne détaille pas.
EXTRA = [
    ("44574", "TVA collectée à encaisser"),
]


def lines(pdf_path: Path):
    import fitz  # PyMuPDF

    doc = fitz.open(pdf_path)
    for index in range(FIRST_PAGE - 1, LAST_PAGE):
        for raw in doc[index].get_text().splitlines():
            line = " ".join(raw.split())
            if line and not NOISE.match(line):
                yield line


def parse(pdf_path: Path) -> list[dict]:
    accounts: dict[str, dict] = {}
    current = None
    started = False
    for line in lines(pdf_path):
        if END_OF_LIST.match(line):
            break
        heading = CLASS_LINE.match(line)
        if heading:
            started = True
            number = heading.group(1)
            current = None
            if number == "8":
                break
            accounts[number] = {"code": number, "label": heading.group(2).strip().upper(),
                                "account_type": ACCOUNT_TYPES[number], "is_header": True}
            continue
        if not started:
            continue
        match = CODE_LINE.match(line)
        if match and match.group(1)[0] in ACCOUNT_TYPES:
            code = match.group(1)
            current = {"code": code, "label": (match.group(2) or "").strip(),
                       "account_type": ACCOUNT_TYPES[code[0]], "is_header": False}
            accounts.setdefault(code, current)
            current = accounts[code]
            continue
        if current is not None:  # libellé sur la ligne suivante ou sur plusieurs lignes
            current["label"] = f"{current['label']} {line}".strip()
    for code, label in EXTRA:
        accounts.setdefault(code, {"code": code, "label": label, "account_type": ACCOUNT_TYPES[code[0]],
                                   "is_header": False})
    for account in accounts.values():
        label = re.sub(r"\s+", " ", account["label"]).strip()
        label = re.sub(r"(\w)- (\w)", r"\1-\2", label)  # césure de fin de ligne (« elle- même »)
        account["label"] = LABELS.get(account["code"], label.replace("’", "'"))
    return sorted(accounts.values(), key=lambda a: (a["code"][0], a["code"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pdf", type=Path, default=PDF)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    accounts = parse(args.pdf)
    missing = [a["code"] for a in accounts if not a["label"]]
    if missing:
        raise SystemExit(f"Comptes sans libellé : {', '.join(missing)}")
    args.out.write_text(json.dumps(accounts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(accounts)} comptes écrits dans {args.out}")


if __name__ == "__main__":
    main()
