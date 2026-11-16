"""Jeu d'essai fictif à partir de FEC réels de cabinets agricoles (lot AG1.f, claudedocs/design_compta_agricole.md
§ 10 ; besoins claudedocs/compta_agri.md § 10, exigences JE1 à JE4).

Exécuté **sur la machine du développeur**, sur des fichiers réels qui ne sont ni copiés ni versionnés ; seule la
sortie (tests/fixtures/agri/) l'est. Ce script ne contient aucune donnée réelle : les dossiers sources se donnent
en argument.

    .venv/bin/python -m scripts.agri_fixtures.anonymize \
        --A <FEC> --B <FEC exercice 1> <FEC exercice 2> --C <FEC> --C-ateliers <export .ISA> [--out tests/fixtures/agri]

Pour chaque exploitation fictive (``FARMS``) :
1. lecture des FEC (fec_import.parse) ;
2. numérotation PCGA 1986 → plan agri (``agri_chart.map_pcga1986``) ; sous-comptes de culture repliés, la
   production reconnue (vocabulary.CROPS) gardée dans le libellé ; tiers (40, 41, 455, 467) renumérotés ;
3. tout texte remplacé : intitulés du plan, gabarits (« Fournisseur 001 », « Coopérative ou négoce A »),
   pièces renumérotées ; lettrage non repris ;
4. montants × un coefficient par dossier (graine fixe), arrondis au centime, chaque écriture rééquilibrée ;
5. dates décalées d'un nombre entier d'années ;
6. **contrôle de fuite** : aucun mot (4 lettres et plus) ni nombre (6 chiffres et plus) des champs texte d'origine
   ne doit subsister hors du vocabulaire autorisé ; sinon le script échoue sans rien écrire ;
7. ``expected.json`` : agrégats calculés sur le fichier produit, indépendamment des états de Lyvre, à relire par
   l'expert-comptable (AGD5).
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.services import agri_chart  # noqa: E402
from app.services.fec_import import parse  # noqa: E402
from scripts.agri_fixtures.vocabulary import GENERIC, JOURNALS, crop_of, family_or_crop, plain, tokens  # noqa: E402

OUT = ROOT / "tests" / "fixtures" / "agri"
PLAN = {a["code"]: a["label"] for a in json.loads((ROOT / "data" / "plan_comptable_agri.json").read_text("utf-8"))}
# Compte sans correspondance : autre charge ou autre produit pour les classes 6 et 7 (le résultat ne change pas),
# compte d'attente sinon ; compté et signalé dans profile.json.
FALLBACK = {"6": "658", "7": "758", "": "471"}
HEADER = ["JournalCode", "JournalLib", "EcritureNum", "EcritureDate", "CompteNum", "CompteLib", "CompAuxNum",
          "CompAuxLib", "PieceRef", "PieceDate", "EcritureLib", "Debit", "Credit", "EcritureLet", "DateLet",
          "ValidDate", "Montantdevise", "Idevise"]
# Champs texte de l'original dont aucun mot ne doit subsister (contrôle de fuite).
SOURCE_TEXT = ("journal_label", "account_label", "aux", "aux_label", "piece", "label", "number")


@dataclass
class Farm:
    """Exploitation fictive : profil, décalage ; les fichiers sources se donnent en argument (aucun nom réel ici)."""
    key: str
    label: str
    profile: dict
    year_shift: int = -1
    seed: int = 0


FARMS = [
    Farm("A_earl_porcs_rs", "EARL des Pins (fictive)",
         {"legal_form_code": "EARL", "income_tax": "IR", "ba_regime": "simplified",
          "description": "Élevage porcin et maïs, réel simplifié, exercice 01/02 → 31/01"}, seed=11),
    Farm("B_scea_legumes_rn", "SCEA du Ruisseau (fictive)",
         {"legal_form_code": "SCEA", "income_tax": "IR", "ba_regime": "normal",
          "description": "Légumes de plein champ et semences sous contrat, réel normal, deux exercices consécutifs"},
         seed=23),
    Farm("C_gaec_ateliers", "GAEC des Trois Chênes (fictif)",
         {"legal_form_code": "GAEC", "income_tax": "IR", "ba_regime": "simplified",
          "description": "Grandes cultures et légumes, 3 associés, ateliers analytiques (export Isacompta)"},
         seed=37),
]


# ------------------------------------------------------------------ correspondances

def tiers_kind(code: str) -> str | None:
    if code.startswith("40"):
        return "supplier"
    if code.startswith("41"):
        return "customer"
    if code.startswith("455"):
        return "associate"
    if code.startswith("467"):
        return "debtor"
    return None


COLLECTIVE = {"supplier": "401", "customer": "411", "associate": "4551", "debtor": "467"}
AUX_PREFIX = {"supplier": "F", "customer": "C", "associate": "A", "debtor": "D"}


class Renamer:
    """Numéros et libellés génériques, stables au sein d'une exploitation."""

    def __init__(self):
        self.aux: dict[tuple, tuple[str, str]] = {}
        self.counts = defaultdict(int)
        self.journals: dict[str, tuple[str, str]] = {}
        self.unmapped = defaultdict(int)

    def account(self, code: str, aux: str) -> tuple[str, str, str, str]:
        """(CompteNum, CompteLib, CompAuxNum, CompAuxLib) fictifs."""
        kind = tiers_kind(code)
        if kind:
            key = (kind, code, aux)
            if key not in self.aux:
                self.counts[kind] += 1
                n = self.counts[kind]
                self.aux[key] = (f"{AUX_PREFIX[kind]}{n:03d}", GENERIC[kind].format(n=n))
            collective = COLLECTIVE[kind]
            aux_num, aux_label = self.aux[key]
            return collective, PLAN.get(collective, collective), aux_num, aux_label
        target = agri_chart.map_pcga1986(code)
        if target is None:  # ancien 791 (transferts de charges, supprimés par le PCG 2026)… : compté, signalé
            self.unmapped[agri_chart.normalize(code)] += 1
            target = FALLBACK.get(code[:1], FALLBACK[""])
        return target, PLAN[target], "", ""

    def journal(self, code: str, entries_accounts: set[str]) -> tuple[str, str]:
        if code not in self.journals:
            if code in JOURNALS:
                self.journals[code] = (code, JOURNALS[code])
            elif any(a.startswith("512") for a in entries_accounts):
                n = 1 + sum(1 for c, _ in self.journals.values() if c.startswith("B"))
                self.journals[code] = (f"B{n}", GENERIC["bank"].format(n=n))
            else:
                n = sum(1 for c, _ in self.journals.values() if c.startswith("K"))
                letter = chr(ord("A") + n)
                self.journals[code] = (f"K{letter}", GENERIC["cooperative"].format(letter=letter))
        return self.journals[code]


def _shift(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year + years)
    except ValueError:  # 29 février
        return day.replace(year=day.year + years, day=28)


def _scale(entries, coefficient: Decimal) -> list[list[tuple[int, int]]]:
    """Montants × coefficient au centime, chaque écriture rééquilibrée sur sa plus grosse ligne."""
    scaled_entries = []
    for entry in entries:
        scaled = [(int((Decimal(l.debit) * coefficient).quantize(1, ROUND_HALF_UP)),
                   int((Decimal(l.credit) * coefficient).quantize(1, ROUND_HALF_UP))) for l in entry.lines]
        gap = sum(d - c for d, c in scaled)
        if gap:
            index = max(range(len(scaled)), key=lambda i: max(scaled[i]))
            d, c = scaled[index]
            scaled[index] = (d - gap, c) if d else (d, c + gap)
        scaled_entries.append(scaled)
    return scaled_entries


def _label(entry, rows) -> str:
    """Libellé générique de l'écriture : intitulé du plus gros compte de charge ou de produit (à défaut
    d'immobilisation ou de stock), et production reconnue."""
    if entry.journal == "AN":
        return GENERIC["opening"]
    sized = [(row, max(line.debit, line.credit)) for row, line in zip(rows, entry.lines)]
    candidates = ([x for x in sized if x[0][0][:1] in "67"]
                  or [x for x in sized if x[0][0][:2] in ("20", "21", "23", "24", "31", "33", "35")])
    main = max(candidates, key=lambda x: x[1])[0] if candidates else None
    crop = crop_of(*(l.account_label for l in entry.lines), *(l.label for l in entry.lines))
    if main is None:
        if any(r[0].startswith("512") for r in rows):
            return GENERIC["receipt"] if any(r[0].startswith("411") for r in rows) else GENERIC["payment"]
        return GENERIC["vat"] if any(r[0].startswith("445") for r in rows) else GENERIC["unknown"]
    return f"{PLAN[main[0]]} — {crop}" if crop else PLAN[main[0]]


def _amount(cents: int) -> str:
    return f"{cents // 100},{cents % 100:02d}"


def build_fec(entries, renamer: Renamer, coefficient: Decimal, years: int) -> tuple[list[list[str]], dict]:
    rows_out, numbers = [], defaultdict(int)
    for entry, amounts in zip(entries, _scale(entries, coefficient)):
        accounts = [renamer.account(l.account, l.aux) for l in entry.lines]
        journal, journal_label = renamer.journal(entry.journal, {l.account for l in entry.lines})
        numbers[journal] += 1
        number = f"{journal}{numbers[journal]:06d}"
        day = _shift(entry.day, years)
        label = _label(entry, accounts)
        for (account, account_label, aux, aux_label), (debit, credit) in zip(accounts, amounts):
            rows_out.append([journal, journal_label, number, day.strftime("%Y%m%d"), account, account_label, aux,
                             aux_label, number, day.strftime("%Y%m%d"), label, _amount(debit), _amount(credit),
                             "", "", "", "", "EUR"])
    return rows_out, {"unmapped": dict(renamer.unmapped)}


# ------------------------------------------------------------------ contrôles

def source_tokens(entries, filenames: list[str]) -> set[str]:
    found = set()
    for entry in entries:
        for line in entry.lines:
            for name in SOURCE_TEXT:
                found |= tokens(str(getattr(line, name, "") or ""))
    for name in filenames:
        found |= tokens(Path(name).stem)
    return found


def allowed_tokens() -> set[str]:
    allowed = set()
    for label in PLAN.values():
        allowed |= tokens(label)
    for text in (*GENERIC.values(), *JOURNALS.values()):
        allowed |= tokens(text)
    from scripts.agri_fixtures.vocabulary import CROPS, FAMILIES
    for _pattern, label in (*CROPS, *FAMILIES):
        allowed |= tokens(label)
    return {t for t in allowed if not t.isdigit()}


def leaks(rows: list[list[str]], source: set[str]) -> set[str]:
    produced = set()
    for row in rows:
        for index in (1, 2, 5, 6, 7, 8, 10):  # champs texte produits
            produced |= tokens(row[index])
    return (produced & source) - allowed_tokens()


def expected(rows: list[list[str]]) -> dict:
    """Agrégats du fichier produit (centimes), calculés sans les états de Lyvre."""
    def cents(text):
        euros, _, cts = text.partition(",")
        return int(euros) * 100 + int(cts or 0)

    by_prefix = defaultdict(lambda: [0, 0])
    total_debit = total_credit = 0
    for row in rows:
        debit, credit = cents(row[11]), cents(row[12])
        total_debit += debit
        total_credit += credit
        code = row[4]
        for n in range(1, len(code) + 1):
            by_prefix[code[:n]][0] += debit
            by_prefix[code[:n]][1] += credit

    def net_credit(*prefixes):
        return sum(by_prefix[p][1] - by_prefix[p][0] for p in prefixes)

    classes = {c: by_prefix[c][0] - by_prefix[c][1] for c in "1234567"}
    return {
        "_comment": "Agrégats du FEC fictif (centimes), calculés directement sur le fichier, à relire par l'expert-comptable.",
        "lines": len(rows), "total_debit_cents": total_debit, "total_credit_cents": total_credit,
        "class_net_debit_cents": classes,
        "result_cents": net_credit("7") - (by_prefix["6"][0] - by_prefix["6"][1]),
        "lines_cents": {
            "ventes_animaux_7014": net_credit("7014"), "ventes_70": net_credit("70"),
            "subventions_74": net_credit("74"), "production_stockee_71": net_credit("71"),
            "achats_animaux_60117": -net_credit("60117"), "fermages_6131": -net_credit("6131"),
            "msa_646": -net_credit("646"), "dotations_6811": -net_credit("6811"),
            "biens_vivants_24": -net_credit("24"), "stocks_3": -net_credit("3"),
        },
    }


# ------------------------------------------------------------------ ateliers (export Isacompta)

ANA = re.compile(r"^ANA\s+(\d+)\s+(.+)$")
QUANTITY = re.compile(r"\s{2,}(ha|tete|tête|kg|unité)\s+(\d+\.\d+)", re.I)


def ateliers(path: Path) -> list[dict]:
    """Ateliers analytiques (code, libellé, unité, surface) des enregistrements ANA ; libellés réduits au
    vocabulaire des productions (aucun autre texte n'est repris)."""
    items = []
    text = path.read_bytes().decode("cp850", errors="replace").replace("\x85", "\n")
    for raw in text.splitlines():
        match = ANA.match(raw.strip())
        if not match:
            continue
        code, rest = match.groups()
        quantity = QUANTITY.search(rest)
        label = rest[:quantity.start()] if quantity else re.split(r"\s{2,}", rest.strip())[0]
        generic = family_or_crop(label) or f"Atelier {code}"
        unit = quantity.group(1) if quantity else None
        surface = float(quantity.group(2)) if quantity else None
        items.append({"code": code, "label": generic, "level": len(code), "unit": (unit or "").lower() or None,
                      "quantity": surface})
    return items


# ------------------------------------------------------------------ programme

def run(sources: dict[str, list[Path]], ateliers_files: dict[str, Path], out: Path) -> None:
    for farm in FARMS:
        if not sources.get(farm.key[0]):
            continue
        rng = random.Random(farm.seed)
        coefficient = Decimal(str(round(rng.uniform(0.8, 1.25), 3)))
        renamer = Renamer()
        files, fiscal_years, all_rows, source_words = [], [], [], set()
        for path in sources[farm.key[0]]:  # un fichier par exercice, dans l'ordre chronologique
            entries, problems = parse(path.read_bytes())
            if problems:
                raise SystemExit(f"{farm.key} : {len(problems)} anomalie(s) dans un fichier source.")
            rows, report = build_fec(entries, renamer, coefficient, farm.year_shift)
            source_words |= source_tokens(entries, [path.name])
            days = sorted(r[3] for r in rows)
            start = _shift(min(e.day for e in entries).replace(day=1), farm.year_shift)
            closing = re.search(r"FEC(\d{8})", path.name, re.I)
            if closing is None:
                raise SystemExit(f"{farm.key} : date de clôture absente du nom du fichier (FECAAAAMMJJ).")
            end = _shift(date(int(closing.group(1)[:4]), int(closing.group(1)[4:6]), int(closing.group(1)[6:])),
                         farm.year_shift)
            name = f"{farm.key[0]}_FEC{end:%Y%m%d}.txt"
            files.append({"file": name, "rows": rows, "report": report})
            fiscal_years.append({"file": name, "start": start.isoformat(), "end": end.isoformat(),
                                 "first_entry": f"{days[0][:4]}-{days[0][4:6]}-{days[0][6:]}"})
            all_rows += rows
        found = leaks(all_rows, source_words)
        if found:
            raise SystemExit(f"{farm.key} : fuite de {len(found)} mot(s) d'origine ; rien n'est écrit.")
        target = out / farm.key
        target.mkdir(parents=True, exist_ok=True)
        for item in files:
            content = "\t".join(HEADER) + "\r\n" + "".join("\t".join(r) + "\r\n" for r in item["rows"])
            (target / item["file"]).write_text(content, encoding="utf-8")
        profile = {"label": farm.label, **farm.profile, "fiscal_years": fiscal_years,
                   "associates": renamer.counts["associate"], "coefficient": str(coefficient),
                   "unmapped": {k: v for f in files for k, v in f["report"]["unmapped"].items()}}
        (target / "profile.json").write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", "utf-8")
        (target / "expected.json").write_text(json.dumps(
            {f["file"]: expected(f["rows"]) for f in files}, ensure_ascii=False, indent=2) + "\n", "utf-8")
        if ateliers_files.get(farm.key[0]):
            path = ateliers_files[farm.key[0]]
            items = ateliers(path)
            found = {t for item in items for t in tokens(item["label"])} & (source_words | source_tokens([], [path.name]))
            found -= allowed_tokens()
            if found:
                raise SystemExit(f"{farm.key} : fuite dans les ateliers ; rien n'est écrit.")
            (target / "ateliers.json").write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", "utf-8")
        print(f"{farm.key} : {len(all_rows)} lignes, {len(files)} exercice(s), coefficient {coefficient}, "
              f"sans correspondance : {profile['unmapped'] or 'aucun'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for key in ("A", "B", "C"):
        parser.add_argument(f"--{key}", type=Path, nargs="+", default=[],
                            help=f"FEC réel(s) de l'exploitation {key}, un par exercice (non versionnés)")
    parser.add_argument("--C-ateliers", dest="c_ateliers", type=Path, help="export Isacompta (.ISA) : ateliers")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    run({"A": args.A, "B": args.B, "C": args.C}, {"C": args.c_ateliers} if args.c_ateliers else {}, args.out)


if __name__ == "__main__":
    main()
