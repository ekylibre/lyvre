"""Construit `data/plan_comptable_agri.json` (référentiel `agri`) et `data/agri_pcga1986_map.json` (lot AG1.b,
`claudedocs/design_compta_agricole.md` § 2).

Plan agri = plan `societe` (PCG 2026, `data/plan_comptable_societe.json`) + comptes de l'art. 131-1 du titre 5
« Exploitations agricoles » du Recueil PCG 2026 (règlement ANC 2020-04 modifié par l'ANC 2024-07,
`doc/ref_compta/Recueil-PCG-Janvier-2026-2-.pdf`). En cas de numéro commun, le libellé du titre 5 l'emporte ;
les arbitrages (en-têtes, subdivisions 7571 / 7578, 6571 / 6578) sont dans
`data/regulatory/sources/agri_chart_decisions.yml`.

La correspondance PCGA 1986 → titre 5 (reprise des FEC des cabinets, jeu d'essai AG1.f, import AG10.6) vient de la
nomenclature `accounts` d'onoma (colonnes `fr_pcga` → `fr_pcga2023`, Ekylibre SAS, CC-BY-SA 4.0) : seules les
paires dont le numéro change sont écrites. Exécuté une fois, sorties versionnées et relues :

    .venv/bin/python scripts/build_agri_chart.py --onoma <dossier>/reference.xml
    (reference.xml : https://github.com/ekylibre/onoma, db/reference.xml)
"""
import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "doc" / "ref_compta" / "Recueil-PCG-Janvier-2026-2-.pdf"
SOCIETE = ROOT / "data" / "plan_comptable_societe.json"
DECISIONS = ROOT / "data" / "regulatory" / "sources" / "agri_chart_decisions.yml"
OUT = ROOT / "data" / "plan_comptable_agri.json"
MAP_OUT = ROOT / "data" / "agri_pcga1986_map.json"

ACCOUNT_TYPES = {"1": "EQUITY", "2": "ASSET", "3": "ASSET", "4": "TIERS", "5": "ASSET", "6": "EXPENSE", "7": "REVENUE"}
START = re.compile(r"^Art\. 131-1$")
END = re.compile(r"^Section 2 – Fonctionnement des comptes")
CODE_LINE = re.compile(r"^(\d{2,6})(?:\s+(.*))?$")
NOISE = re.compile(r"^(Version du .*|CLASSE \d .*|Art\. 131-1|Sous réserve des aménagements.*|est défini par le règlement.*)$")
FOOTNOTE = re.compile(r"\s*\(\d+\)$")
ATTRIBUTION = ("Plan de comptes : PCG 2026 et titre 5 « Exploitations agricoles » du Recueil des normes comptables "
               "(ANC, version du 1er janvier 2026). Correspondance PCGA 1986 : nomenclature onoma d'Ekylibre SAS "
               "(https://github.com/ekylibre/onoma), licence CC-BY-SA 4.0.")


def visual_lines(pdf_path: Path):
    """Lignes du texte reconstituées par position (le numéro et l'intitulé d'un compte sont des blocs séparés)."""
    import fitz  # PyMuPDF

    doc = fitz.open(pdf_path)
    started = False
    for page in doc:
        rows = {}
        for x0, y0, _x1, y1, word, *_ in page.get_text("words"):
            rows.setdefault(round((y0 + y1) / 6), []).append((x0, word))
        for key in sorted(rows):
            words = sorted(rows[key])
            line = " ".join(w for _, w in words)
            if not started:
                started = bool(START.match(line))
                continue
            if END.match(line):
                return
            yield line


def parse_title5(pdf_path: Path) -> dict[str, str]:
    accounts: dict[str, str] = {}
    current = None
    for line in visual_lines(pdf_path):
        if NOISE.match(line):
            continue
        match = CODE_LINE.match(line)
        if match:
            current = match.group(1)
            accounts[current] = (match.group(2) or "").strip()
        elif current is not None:  # suite de l'intitulé sur la ligne suivante
            accounts[current] = f"{accounts[current]} {line}".strip()
    if not accounts:
        raise SystemExit("Titre 5 introuvable dans le PDF (art. 131-1).")
    clean = {}
    for code, label in accounts.items():
        label = FOOTNOTE.sub("", re.sub(r"\s+", " ", label)).replace("’", "'").strip()
        label = label.replace("(sauf (C.U.M.A.)", "(sauf C.U.M.A.)")
        clean[code] = label
    return clean


def load_decisions(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    pending = [k for section in ("labels", "pcga1986_overrides") for k, v in (data.get(section) or {}).items()
               if v.get("status") != "decided"]
    pending += [e["code"] for e in data.get("extra") or [] if e.get("status") != "decided"]
    if pending:
        raise SystemExit(f"Arbitrages en attente dans {path.name} : {', '.join(pending)}")
    return data


def build_chart(title5: dict[str, str], decisions: dict) -> tuple[list[dict], dict]:
    chart = {a["code"]: dict(a) for a in json.loads(SOCIETE.read_text(encoding="utf-8"))}
    report = {"added": [], "relabelled": []}
    for code, label in title5.items():
        if code in chart:
            if chart[code]["label"] != label and label:
                report["relabelled"].append((code, chart[code]["label"], label))
                chart[code]["label"] = label
        else:
            chart[code] = {"code": code, "label": label, "account_type": ACCOUNT_TYPES[code[0]], "is_header": False}
            report["added"].append(code)
    for code, decision in (decisions.get("labels") or {}).items():
        entry = chart.setdefault(code, {"code": code, "label": "", "account_type": ACCOUNT_TYPES[code[0]],
                                        "is_header": False})
        entry["label"] = decision["label"]
    for extra in decisions.get("extra") or []:
        chart[extra["code"]] = {"code": extra["code"], "label": extra["label"],
                                "account_type": ACCOUNT_TYPES[extra["code"][0]], "is_header": False}
        report["added"].append(extra["code"])
    missing = [code for code, a in chart.items() if not a["label"]]
    if missing:
        raise SystemExit(f"Comptes sans libellé : {', '.join(missing)}")
    return sorted(chart.values(), key=lambda a: (a["code"][0], a["code"])), report


def build_map(onoma_path: Path, decisions: dict, codes: set[str]) -> dict:
    root = ET.parse(onoma_path).getroot()
    nomenclature = next(n for n in root.iter() if n.tag.endswith("nomenclature") and n.get("name") == "accounts")
    pairs: dict[str, set[str]] = {}
    for item in nomenclature.iter():
        if not item.tag.endswith("item"):
            continue
        old = item.get("fr_pcga") or item.get("fr_pcg82")
        new = item.get("fr_pcga2023")
        if old and new and "NONE" not in (old, new):
            pairs.setdefault(old, set()).add(new)
    ambiguous = {old: sorted(new) for old, new in pairs.items() if len(new) > 1}
    if ambiguous:
        raise SystemExit(f"Correspondances ambiguës : {ambiguous}")
    mapping = {old: next(iter(new)) for old, new in pairs.items() if next(iter(new)) != old}
    for old, decision in (decisions.get("pcga1986_overrides") or {}).items():
        if decision["target"] == old:
            mapping.pop(old, None)
        else:
            mapping[old] = decision["target"]
    # onoma détaille parfois plus que le plan officiel (603111, 70140…) : cible rabattue sur le compte existant
    # du préfixe le plus long.
    # Sans compte parent (797 : le PCG 2026 n'a plus de transferts de charges) : correspondance retirée et listée,
    # l'import la signale pour un choix manuel.
    resolved, unmapped = {}, {}
    for old, target in list(mapping.items()):
        if target not in codes:
            parent = next((target[:n] for n in range(len(target) - 1, 1, -1) if target[:n] in codes), None)
            if parent is None:
                unmapped[old] = target
                del mapping[old]
                continue
            resolved[old] = f"{target} → {parent}"
            mapping[old] = parent
    mapping = {old: new for old, new in mapping.items() if new != old}
    return {"_comment": "Ancien plan comptable agricole (PCGA 1986) → plan agri (titre 5) : numéros qui changent. "
                        "Un code absent garde son numéro ; à défaut le préfixe le plus long s'applique "
                        "(app/services/agri_chart.map_pcga1986).",
            "_attribution": ATTRIBUTION, "resolved_to_parent": dict(sorted(resolved.items())),
            "unmapped": dict(sorted(unmapped.items())),
            "map": dict(sorted(mapping.items()))}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pdf", type=Path, default=PDF)
    parser.add_argument("--onoma", type=Path, required=True, help="db/reference.xml du dépôt ekylibre/onoma")
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--map-out", type=Path, default=MAP_OUT)
    args = parser.parse_args()
    decisions = load_decisions(DECISIONS)
    title5 = parse_title5(args.pdf)
    chart, report = build_chart(title5, decisions)
    mapping = build_map(args.onoma, decisions, {a["code"] for a in chart})
    args.out.write_text(json.dumps(chart, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.map_out.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Titre 5 : {len(title5)} comptes lus ; plan agri : {len(chart)} comptes ({len(report['added'])} ajoutés).")
    for code, old, new in report["relabelled"]:
        print(f"  libellé remplacé {code} : « {old} » → « {new} »")
    print(f"Correspondance PCGA 1986 : {len(mapping['map'])} numéros ; cibles rabattues sur un parent : "
          f"{len(mapping['resolved_to_parent'])} ; sans correspondance : {mapping['unmapped'] or 'aucune'}")


if __name__ == "__main__":
    main()
