"""Version de Lyvre et historique des nouveautés (lot R1).

Source unique : `data/changelog.yml`. Le numéro de version est celui de la première version publiée
(schéma calendaire `AAAA.MM.N`) ; il n'est écrit nulle part ailleurs à la main (`CHANGELOG.md`,
`frontend/package.json` et le badge du README sont générés par `scripts/release.py build`). Le
commit déployé vient de `APP_COMMIT` (argument de construction de l'image), vide s'il est inconnu.
"""
from __future__ import annotations

import os
import re
from datetime import date
from functools import cache
from pathlib import Path

import yaml

CHANGELOG_FILE = Path(__file__).resolve().parents[1] / "data" / "changelog.yml"
VERSION_PATTERN = re.compile(r"^(\d{4})\.(\d{2})\.(\d+)$")
KINDS = {"action": "Action requise", "new": "Nouveautés", "improved": "Améliorations", "fixed": "Corrections"}
STRUCTURES = {"asso": "Associations", "sci": "SCI", "societe": "Sociétés"}


class ChangelogError(ValueError):
    pass


def load(path: Path = CHANGELOG_FILE) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data.setdefault("next", [])
    data.setdefault("versions", [])
    return data


@cache
def _data() -> dict:
    return load()


def version() -> str:
    versions = _data()["versions"]
    return versions[0]["version"] if versions else "0.0.0"


def commit() -> str:
    return (os.environ.get("APP_COMMIT") or "").strip()[:12]


def info() -> dict:
    return {"version": version(), "commit": commit()}


def published() -> list[dict]:
    """Versions publiées pour la page « Nouveautés » : sans `next` ni précisions techniques."""
    return [{"version": v["version"], "date": _iso(v["date"]), "title": v.get("title") or "",
             "entries": [{k: e[k] for k in ("kind", "structure", "text") if e.get(k)} for e in v.get("entries") or []]}
            for v in _data()["versions"]]


def _iso(value) -> str:
    return value.isoformat() if isinstance(value, date) else str(value)


# ------------------------------------------------------------------ contrôles et numérotation


def parse(number: str) -> tuple[int, int, int]:
    match = VERSION_PATTERN.match(str(number))
    if not match:
        raise ChangelogError(f"Version « {number} » : format AAAA.MM.N attendu.")
    year, month, n = (int(g) for g in match.groups())
    if not 1 <= month <= 12 or n < 1:
        raise ChangelogError(f"Version « {number} » : mois ou numéro invalide.")
    return year, month, n


def next_version(previous: str | None, today: date) -> str:
    """Numéro suivant : même mois → N + 1, sinon `AAAA.MM.1` du mois courant."""
    if previous:
        year, month, n = parse(previous)
        if (year, month) == (today.year, today.month):
            return f"{year}.{month:02d}.{n + 1}"
        if (year, month) > (today.year, today.month):
            raise ChangelogError(f"La dernière version ({previous}) est postérieure au mois courant.")
    return f"{today.year}.{today.month:02d}.1"


def validate(data: dict) -> list[str]:
    """Erreurs du fichier (vide si tout est bon)."""
    errors = []
    seen = []
    for v in data.get("versions") or []:
        number = v.get("version")
        try:
            key = parse(number)
        except ChangelogError as exc:
            errors.append(str(exc))
            continue
        if not isinstance(v.get("date"), date):
            errors.append(f"{number} : date AAAA-MM-JJ attendue.")
        elif (v["date"].year, v["date"].month) != key[:2]:
            errors.append(f"{number} : la date {v['date']} n'est pas dans le mois de la version.")
        if seen and key >= seen[-1]:
            errors.append(f"{number} : les versions doivent être de la plus récente à la plus ancienne.")
        seen.append(key)
        if not v.get("title"):
            errors.append(f"{number} : titre manquant.")
        errors += _entry_errors(v.get("entries") or [], number)
    errors += _entry_errors(data.get("next") or [], "next")
    return errors


def _entry_errors(entries: list, where: str) -> list[str]:
    errors = []
    for i, e in enumerate(entries, 1):
        if e.get("kind") not in KINDS:
            errors.append(f"{where}, entrée {i} : type parmi {', '.join(KINDS)}.")
        if e.get("structure") not in (None, *STRUCTURES):
            errors.append(f"{where}, entrée {i} : structure « asso » ou « sci ».")
        if not (e.get("text") or "").strip():
            errors.append(f"{where}, entrée {i} : texte manquant.")
    return errors


# ------------------------------------------------------------------ CHANGELOG.md


def markdown(data: dict) -> str:
    lines = ["# Changelog — Lyvre", "",
             "<!-- Fichier généré à partir de data/changelog.yml : ne pas le modifier à la main,",
             "     lancer `python scripts/release.py build`. -->", "",
             "Versions au format calendaire `AAAA.MM.N` (année, mois, numéro dans le mois). Les mêmes",
             "nouveautés s'affichent dans l'application (menu utilisateur › Nouveautés).", ""]
    for v in data.get("versions") or []:
        d = v["date"]
        lines += [f"## {v['version']} — {v.get('title', '')} ({d.strftime('%d/%m/%Y') if isinstance(d, date) else d})", ""]
        entries = v.get("entries") or []
        for kind, label in KINDS.items():
            group = [e for e in entries if e.get("kind") == kind]
            if not group:
                continue
            lines += [f"### {'⚠️ ' if kind == 'action' else ''}{label}", ""]
            for e in group:
                tag = f"[{STRUCTURES[e['structure']]}] " if e.get("structure") else ""
                tech = f" — *{e['tech'].strip()}*" if e.get("tech") else ""
                lines.append(f"- {tag}{e['text'].strip()}{tech}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"
