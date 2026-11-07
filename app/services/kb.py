"""Fiches de méthode de la base documentaire (lot CG4, claudedocs/design_fiabilisation_cegara.md § 7 ;
format de doc/base_documentaire/02_corpus_fiches.md § 2.3).

Une fiche est un fichier Markdown à en-tête YAML, rangé dans `data/kb/fiches/<référentiel>/<ID>.md`, avec les sections
« Résumé », « Exemple », « Référence » et « Dans le logiciel ». Chargeur générique (D-CG4.1) : seules les fiches du
référentiel `agri` (identifiants `MA-xx`) sont livrées pour l'instant. Une fiche au statut `brouillon` n'est pas chargée.

Règles vérifiées par `validate()` : clés obligatoires, identifiant égal au nom du fichier, sections, longueur, au moins un
lien vers une source primaire, paramètres datés et fiches d'échéances cités existants, aucun texte de guide de tiers
(règle AGD16). Les montants, seuils et taux ne s'écrivent pas dans la fiche : elle cite la clé du paramètre daté.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

KB_DIR = Path(__file__).resolve().parents[2] / "data" / "kb" / "fiches"
ID_PATTERNS = {"agri": re.compile(r"^MA-\d\d$")}
REQUIRED = ("id", "titre", "referentiels", "articles", "liens", "statut", "verifie_le", "verifie_par", "risque")
SECTIONS = ("Résumé", "Exemple", "Référence", "Dans le logiciel")
STATUSES = ("brouillon", "a_confirmer", "publie")
RISKS = ("aucun", "attention", "expert")
MAX_WORDS = 700
PRIMARY_DOMAINS = ("legifrance.gouv.fr", "bofip.impots.gouv.fr", "impots.gouv.fr", "msa.fr", "service-public.fr",
                   "service-public.gouv.fr", "agriculture.gouv.fr", "eur-lex.europa.eu", "anc.gouv.fr",
                   "franceagrimer.fr")
FORBIDDEN = re.compile(r"\bCEGA(RA|O)\b", re.IGNORECASE)
_FRONT = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def _parse(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    match = _FRONT.match(text)
    if not match:
        return {"_path": path, "_error": "en-tête YAML absent (--- … ---)"}
    head = yaml.safe_load(match.group(1)) or {}
    if not isinstance(head, dict):
        return {"_path": path, "_error": "en-tête YAML invalide"}
    return {**head, "body": match.group(2).strip(), "_path": path}


def _load(base: Path = KB_DIR) -> list[dict]:
    return [_parse(p) for p in sorted(base.glob("*/*.md"))]


def validate(fiches: list[dict] | None = None) -> list[str]:
    """Problèmes des fiches (liste vide : base valide)."""
    from app.services import deadlines, reg_params

    fiches = _load() if fiches is None else fiches
    known_params = {p.key for p in reg_params.file_params()}
    known_deadlines = {f["id"] for f in deadlines.fiches()}
    problems, seen = [], set()
    for f in fiches:
        where = str(f.get("_path", f.get("id", "?")))
        if f.get("_error"):
            problems.append(f"{where} : {f['_error']}")
            continue
        missing = [k for k in REQUIRED if f.get(k) in (None, "", [])]
        if missing:
            problems.append(f"{where} : clé(s) manquante(s) {', '.join(missing)}")
        fid = str(f.get("id", ""))
        refs = f.get("referentiels") or []
        if fid in seen:
            problems.append(f"{where} : identifiant {fid} en double")
        seen.add(fid)
        if "_path" in f and Path(f["_path"]).stem != fid:
            problems.append(f"{where} : le nom du fichier doit être {fid}.md")
        if not any(ID_PATTERNS.get(r, re.compile(".")).match(fid) for r in refs):
            problems.append(f"{where} : identifiant {fid} non conforme au référentiel {refs}")
        if f.get("statut") not in STATUSES:
            problems.append(f"{where} : statut inconnu")
        if f.get("risque") not in RISKS:
            problems.append(f"{where} : risque inconnu")
        body = f.get("body", "")
        for section in SECTIONS:
            if not re.search(rf"^## {re.escape(section)}\s*$", body, re.MULTILINE):
                problems.append(f"{where} : section « {section} » absente")
        words = len(re.findall(r"\w+", body))
        if words > MAX_WORDS:
            problems.append(f"{where} : {words} mots (au plus {MAX_WORDS})")
        links = [str(l) for l in f.get("liens") or []]
        if not any(l.startswith("https://") and any(d in l for d in PRIMARY_DOMAINS) for l in links):
            problems.append(f"{where} : aucun lien vers une source primaire")
        for key in f.get("parametres") or []:
            if key not in known_params:
                problems.append(f"{where} : paramètre daté inconnu {key}")
        for key in re.findall(r"\[([a-z_]+(?:\.[a-z0-9_]+)+)\]", body):
            if key not in known_params:
                problems.append(f"{where} : paramètre cité inconnu [{key}]")
        for key in f.get("echeances") or []:
            if key not in known_deadlines:
                problems.append(f"{where} : fiche d'échéance inconnue {key}")
        if FORBIDDEN.search(body) or FORBIDDEN.search(str(f.get("liens"))):
            problems.append(f"{where} : texte ou source d'un guide de tiers (règle AGD16)")
    return problems


@lru_cache(maxsize=4)
def method_fiches(referentiel: str = "agri") -> tuple[dict, ...]:
    """Fiches chargées du référentiel (hors brouillons), triées par identifiant."""
    fiches = [f for f in _load() if not f.get("_error") and referentiel in (f.get("referentiels") or [])
              and f.get("statut") != "brouillon"]
    return tuple(sorted(({k: v for k, v in f.items() if k != "_path"} for f in fiches), key=lambda f: f["id"]))


def corpus_text(referentiel: str = "agri") -> str:
    """Texte déterministe des fiches pour le corpus de l'assistant."""
    out = []
    for f in method_fiches(referentiel):
        status = "publiée" if f["statut"] == "publie" else "à confirmer"
        out.append(f"### [{f['id']}] {f['titre']} — {status}, vérifiée le {f['verifie_le']} ; "
                   f"articles : {'; '.join(f.get('articles') or [])}\n{f['body']}")
    return "\n\n".join(out)
