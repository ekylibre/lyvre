"""Construit `data/agri_purchase_categories.json` : catégories d'articles agricoles avec compte et taux de TVA par
défaut (lot AG1.e, `claudedocs/design_compta_agricole.md` § 7.1).

Source : jeu « variants » de Lexicon (catégories d'articles de référence d'Ekylibre, CC-BY-SA 4.0), dont les comptes
sont des clés d'usage onoma, traduites en numéros du plan agricole 2023 (nomenclature `accounts` d'onoma,
`fr_pcga2023`) puis rattachées au compte existant du plan agri au préfixe le plus long. Seuls sont gardés les achats
en 60 à 62 et les ventes en 70 (pas de TVA sur les salaires, impôts ou immobilisations). Taux de TVA : proposition
de Lexicon, à valider par l'expert-comptable (AGD5). Exécuté une fois, sortie versionnée et relue :

    .venv/bin/python scripts/build_agri_categories.py --onoma <dossier>/reference.xml \
        [--csv ~/projects/lexicon/data/variants/"variants - categories.csv"]
"""
import argparse
import csv
import json
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV = Path.home() / "projects" / "lexicon" / "data" / "variants" / "variants - categories.csv"
OUT = ROOT / "data" / "agri_purchase_categories.json"
PURCHASE_PREFIXES = ("60", "61", "62")
SALE_PREFIXES = ("70",)
# Corrections de Lyvre aux propositions de Lexicon (à valider par l'expert-comptable avec le reste, AGD5).
OVERRIDES = {
    "land_rent": {"label": "Fermage et location de terrain", "purchase_account": "6131"},  # titre 5 : 6131 fermages
    "waste_tax": None,  # contribution (taxe), pas un achat soumis à TVA
    "insurance": {"label": "Prime d'assurance", "vat_rate_bp": None, "sale_account": None},  # exonérée de TVA
    "bank_service": {"vat_rate_bp": None},  # commissions bancaires en grande partie exonérées
    "fee": {"label": "Rémunération d'intermédiaire et honoraires"},
}
ATTRIBUTION = ("Catégories d'articles de référence d'Ekylibre SAS (jeu « variants » de Lexicon, "
               "https://lexicon.osfarm.org) et nomenclature onoma (https://github.com/ekylibre/onoma), licence "
               "CC-BY-SA 4.0 ; comptes rattachés au plan agri de Lyvre.")


def usages(onoma: Path) -> dict[str, str]:
    root = ET.parse(onoma).getroot()
    nomenclature = next(n for n in root.iter() if n.tag.endswith("nomenclature") and n.get("name") == "accounts")
    return {i.get("name"): i.get("fr_pcga2023") for i in nomenclature.iter()
            if i.tag.endswith("item") and i.get("fr_pcga2023") not in (None, "NONE")}


def in_chart(code: str | None, codes: set[str]) -> str | None:
    if not code:
        return None
    return next((code[:n] for n in range(len(code), 1, -1) if code[:n] in codes), None)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--csv", type=Path, default=CSV)
    parser.add_argument("--onoma", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    numbers = usages(args.onoma)
    chart = {a["code"]: a["label"] for a in json.loads((ROOT / "data" / "plan_comptable_agri.json").read_text("utf-8"))}
    codes = set(chart)
    items, skipped = [], []
    for row in csv.DictReader(args.csv.open(encoding="utf-8")):
        purchase = in_chart(numbers.get(row["charge_account"]), codes)
        sale = in_chart(numbers.get(row["product_account"]), codes)
        purchase = purchase if purchase and purchase.startswith(PURCHASE_PREFIXES) else None
        sale = sale if sale and sale.startswith(SALE_PREFIXES) else None
        if not purchase and not sale:
            skipped.append(row["reference_name"])
            continue
        rate = row["default_vat_rate"].strip()
        item = {"key": row["reference_name"], "label": row["fra"].replace(". ", ", ").strip(),
                "family": row["family"], "purchase_account": purchase, "sale_account": sale,
                "vat_rate_bp": round(float(rate) * 100) if rate else None, "vat_to_validate": True}
        if row["reference_name"] in OVERRIDES:
            change = OVERRIDES[row["reference_name"]]
            if change is None:
                skipped.append(row["reference_name"])
                continue
            item.update(change, corrected_by_lyvre=True)
        items.append(item)
    data = {"_comment": "Catégories d'articles agricoles (lot AG1.e) : compte d'achat (60 à 62) et/ou de vente (70) "
                        "du plan agri, taux de TVA proposé par Lexicon (vat_to_validate : à valider, AGD5). "
                        "Généré par scripts/build_agri_categories.py.",
            "_attribution": ATTRIBUTION, "categories": sorted(items, key=lambda i: i["label"])}
    args.out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(items)} catégories écrites ; écartées (ni achat 60-62 ni vente 70) : {len(skipped)}")


if __name__ == "__main__":
    main()
