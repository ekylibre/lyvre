"""Exploitation fictive D : maraîchage en vente directe au micro-BA et au remboursement forfaitaire agricole,
entièrement synthétique (aucun dossier réel ne couvre ce cas ; lot AG1.f, exigence JE3).

    .venv/bin/python -m scripts.agri_fixtures.build_synthetic [--out tests/fixtures/agri]

Recettes et dépenses de l'année civile 2025 par catégorie (codes de ``simple_categories.AGRI_DEFAULTS``) ; graine
fixe : la sortie est reproductible.
"""
import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tests" / "fixtures" / "agri" / "D_micro_rfa"
YEAR = 2025


def operations(seed: int = 41) -> list[dict]:
    rng = random.Random(seed)
    ops = []

    def add(day, category, cents, label):
        ops.append({"date": day.isoformat(), "category": category, "amount_cents": cents, "label": label})

    day = date(YEAR, 1, 4)
    while day.year == YEAR:  # marché du samedi : légumes, plus fort de mai à octobre
        high = 5 <= day.month <= 10
        add(day, "ventes_vegetaux", rng.randint(32000, 61000) if high else rng.randint(9000, 21000), "Marché du samedi")
        day += timedelta(days=7)
    for month in range(1, 13):  # paniers AMAP, fin de mois
        add(date(YEAR, month, 28), "ventes_vegetaux", rng.randint(80000, 110000), "Paniers du mois")
    for month in (3, 6, 9, 12):  # restaurant (assujetti : vente éligible au remboursement forfaitaire)
        add(date(YEAR, month, 15), "ventes_vegetaux", rng.randint(60000, 90000), "Livraison restaurant")
    add(date(YEAR, 10, 20), "aides_pac", 98000, "Aides PAC : avance")
    add(date(YEAR, 12, 10), "aides_pac", 32000, "Aides PAC : solde")
    add(date(YEAR, 4, 12), "cessions", 150000, "Vente de l'ancien motoculteur")
    add(date(YEAR, 2, 3), "semences", 184000, "Semences et plants")
    add(date(YEAR, 3, 10), "engrais", 92000, "Amendements organiques")
    for month in range(1, 13):
        add(date(YEAR, month, 5), "carburant", rng.randint(6000, 14000), "Carburant")
    add(date(YEAR, 9, 29), "fermages", 120000, "Fermage (Saint-Michel)")
    for month in (3, 6, 11):
        add(date(YEAR, month, 25), "msa_exploitant", 115000, "Cotisations MSA")
    add(date(YEAR, 1, 15), "assurances", 64000, "Assurance de l'exploitation")
    add(date(YEAR, 7, 8), "entretien", 38000, "Réparation de la serre")
    return sorted(ops, key=lambda o: (o["date"], o["category"]))


EXCLUDED = {"cessions", "ichn", "entraide"}  # recettes exclues du micro-BA (CGI art. 64 bis)


def expected(ops: list[dict]) -> dict:
    receipts = [o for o in ops if o["category"] in {"ventes_vegetaux", "aides_pac", "cessions"}]
    return {"_comment": "Totaux de l'année civile (centimes), à relire par l'expert-comptable.",
            "receipts_cents": sum(o["amount_cents"] for o in receipts),
            "micro_receipts_cents": sum(o["amount_cents"] for o in receipts if o["category"] not in EXCLUDED),
            "excluded_cents": sum(o["amount_cents"] for o in receipts if o["category"] in EXCLUDED),
            "expenses_cents": sum(o["amount_cents"] for o in ops if o not in receipts),
            "operations": len(ops)}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    ops = operations()
    profile = {"label": "Les Jardins du Coteau (fictifs)", "legal_form_code": "EI", "income_tax": "IR",
               "ba_regime": "micro", "vat_regime": "rfa",
               "description": "Maraîchage en vente directe, micro-BA, remboursement forfaitaire agricole (synthétique)",
               "fiscal_years": [{"start": f"{YEAR}-01-01", "end": f"{YEAR}-12-31"}]}
    (args.out / "profile.json").write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", "utf-8")
    (args.out / "operations.json").write_text(json.dumps(ops, ensure_ascii=False, indent=1) + "\n", "utf-8")
    (args.out / "expected.json").write_text(json.dumps(expected(ops), ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(f"D_micro_rfa : {len(ops)} opérations")


if __name__ == "__main__":
    main()
