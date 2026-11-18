"""Contenu public de Lyvre : sections générées du README et contrôles (site lyvre.org, lot L1).

Sources : `data/features.yml` (présentation, fonctionnalités, intégrations) et les versions publiées de
`data/changelog.yml` (jamais `next` ni `tech`). Le site (`site/`) relit les mêmes fichiers à sa
construction ; ce module ne produit que le README et vérifie que rien de privé n'est publié.

Liste noire : `data/public_denylist.sha256` contient des empreintes SHA-256 de termes normalisés
(minuscules, sans accents, mots séparés par une espace) ; le dépôt étant public, aucun terme n'y est
lisible. Un fichier local facultatif `.public-denylist` (ignoré par Git, un terme par ligne) est
contrôlé en plus.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
FEATURES_FILE = ROOT / "data" / "features.yml"
DENYLIST_FILE = ROOT / "data" / "public_denylist.sha256"
LOCAL_DENYLIST = ROOT / ".public-denylist"
IMAGES = ROOT / "doc" / "images"
SITE_URL = "https://lyvre.org"
DEMO_URL = "https://demo.lyvre.org"
NEWS_COUNT = 5
STRUCTURES = ("asso", "sci", "agri", "societe")
STATUSES = ("available", "soon")
MAX_NGRAM = 4


def load_features(path: Path = FEATURES_FILE) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for key in ("highlights", "audiences", "overview", "domains", "features", "integrations"):
        data.setdefault(key, [])
    return data


# ------------------------------------------------------------------ contrôles


def validate_features(features: dict, published: set[str]) -> list[str]:
    errors = []
    domains = {d.get("id") for d in features["domains"]}
    seen = set()
    for f in features["features"]:
        where = f"features.yml, fonctionnalité « {f.get('id')} »"
        if not f.get("id") or f["id"] in seen:
            errors.append(f"{where} : identifiant manquant ou en double.")
        seen.add(f.get("id"))
        if f.get("id") in domains:
            errors.append(f"{where} : même identifiant qu'un module (ancre en double sur le site).")
        if f.get("domain") not in domains:
            errors.append(f"{where} : domaine inconnu « {f.get('domain')} ».")
        if not (f.get("title") and f.get("text")):
            errors.append(f"{where} : titre et texte attendus.")
        if any(s not in STRUCTURES for s in f.get("structures") or []):
            errors.append(f"{where} : structures parmi {', '.join(STRUCTURES)}.")
        if f.get("status", "available") not in STATUSES:
            errors.append(f"{where} : état « available » ou « soon ».")
        if f.get("since") and str(f["since"]) not in published:
            errors.append(f"{where} : version « {f['since']} » non publiée.")
    for section in ("audiences", "overview", "features"):
        for item in features[section]:
            capture = item.get("capture")
            if capture and not (IMAGES / capture).is_file():
                errors.append(f"features.yml, {section} : capture « {capture} » absente de doc/images/.")
    for d in features["domains"]:
        for shot in d.get("captures") or []:
            if not (shot.get("file") and shot.get("alt")):
                errors.append(f"features.yml, module « {d.get('id')} » : capture sans fichier ou sans texte alternatif.")
            elif not (IMAGES / shot["file"]).is_file():
                errors.append(f"features.yml, module « {d.get('id')} » : capture « {shot['file']} » absente de doc/images/.")
    return errors


def normalize(text: str) -> list[str]:
    plain = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return re.findall(r"[a-z0-9]+", plain)


def fingerprint(term: str) -> str:
    return hashlib.sha256(" ".join(normalize(term)).encode()).hexdigest()


def denylist(path: Path = DENYLIST_FILE, local: Path = LOCAL_DENYLIST) -> set[str]:
    hashes = set()
    if path.exists():
        hashes |= {line.strip() for line in path.read_text(encoding="utf-8").splitlines()
                   if line.strip() and not line.startswith("#")}
    if local.exists():
        hashes |= {fingerprint(line) for line in local.read_text(encoding="utf-8").splitlines()
                   if line.strip() and not line.startswith("#")}
    return hashes


def denied(text: str, hashes: set[str]) -> bool:
    """Vrai si une suite de 1 à MAX_NGRAM mots du texte a une empreinte de la liste noire."""
    if not hashes:
        return False
    words = normalize(text)
    for n in range(1, MAX_NGRAM + 1):
        for i in range(len(words) - n + 1):
            if hashlib.sha256(" ".join(words[i:i + n]).encode()).hexdigest() in hashes:
                return True
    return False


def public_texts(features: dict, versions: list[dict]) -> list[tuple[str, str]]:
    """(origine, texte) de tout ce qui est publié sur le site ou le README."""
    out = [(f"features.yml › {key}", s) for key in features for s in _strings(features[key])]
    for v in versions:
        out.append((f"changelog {v['version']} › titre", str(v.get("title") or "")))
        out += [(f"changelog {v['version']}", e.get("text") or "") for e in v.get("entries") or []]
    return out


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def denylist_errors(texts: list[tuple[str, str]], hashes: set[str]) -> list[str]:
    return [f"{where} : contient un terme de la liste noire (texte public)." for where, text in texts
            if denied(text, hashes)]


# ------------------------------------------------------------------ sections du README


def _inline(text: str) -> str:
    """Markdown en ligne (gras, code) → HTML, pour les cellules de tableau HTML du README."""
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text.strip())
    return re.sub(r"`(.+?)`", r"<code>\1</code>", text)


def highlights_section(features: dict) -> str:
    width = f"{100 // max(len(features['highlights']), 1)}%"
    cells = "\n".join(f'    <td width="{width}" valign="top"><b>{h["emoji"]} {h["title"]}</b><br>'
                      f'<sub>{_inline(h["text"])}</sub></td>' for h in features["highlights"])
    return f"<table>\n  <tr>\n{cells}\n  </tr>\n</table>"


def audiences_section(features: dict) -> str:
    rows = []
    for i, a in enumerate(features["audiences"]):
        items = "\n".join(f"        <li>{_inline(p)}</li>" for p in a["points"])
        text = f'    <td valign="top">\n      <h3>{a["emoji"]} {a["title"]}</h3>\n      <ul>\n{items}\n      </ul>\n    </td>'
        if a.get("capture"):
            image = f'    <td valign="top"><img src="doc/images/{a["capture"]}" alt="{a.get("alt", a["title"])}"></td>'
            cells = [text, image] if i % 2 == 0 else [image, text]
        else:
            cells = [text.replace('<td valign="top">', '<td colspan="2" valign="top">', 1)]
        rows.append("  <tr>\n" + "\n".join(cells) + "\n  </tr>")
    return "<table>\n" + "\n".join(rows) + "\n</table>"


def overview_section(features: dict) -> str:
    items = features["overview"]
    rows = []
    for i in range(0, len(items), 2):
        cells = "\n".join(
            f'    <td width="50%"><img src="doc/images/{o["capture"]}" alt="{o["alt"]}"><br>'
            f'<sub><b>{o["title"]}</b> : {_inline(o["caption"])}</sub></td>' for o in items[i:i + 2])
        rows.append(f"  <tr>\n{cells}\n  </tr>")
    return "<table>\n" + "\n".join(rows) + "\n</table>"


def features_section(features: dict) -> str:
    blocks = []
    for d in features["domains"]:
        group = [f for f in features["features"] if f["domain"] == d["id"]]
        if not group:
            continue
        lines = [f"- **{f['title']}**{_suffix(f)} : {f['text'].strip()}" for f in group]
        blocks.append(f"<details>\n<summary><b>{d['emoji']} {d['title']}</b></summary>\n\n" + "\n".join(lines)
                      + "\n</details>")
    return "\n\n".join(blocks)


def _suffix(f: dict) -> str:
    return " *(à venir)*" if f.get("status") == "soon" else ""


def integrations_section(features: dict) -> str:
    rows = [f"| **{i['name']}** | {i['usage']} | {i['structures']} |" for i in features["integrations"]]
    return "| Service | Usage | Structures |\n|---|---|---|\n" + "\n".join(rows)


def news_section(versions: list[dict], structures: dict, count: int = NEWS_COUNT) -> str:
    lines = []
    for v in versions[:count]:
        d = v["date"]
        when = d.strftime("%d/%m/%Y") if isinstance(d, date) else str(d)
        lines.append(f"- **{v['version']} — {v.get('title', '')}** ({when})")
        entries = v.get("entries") or []
        picked = [e for e in entries if e["kind"] in ("action", "new")] or entries
        for e in picked[:3]:
            tag = f"[{structures[e['structure']]}] " if e.get("structure") else ""
            prefix = "⚠️ " if e["kind"] == "action" else ""
            lines.append(f"  - {prefix}{tag}{_first_sentence(e['text'])}")
    lines += ["", f"Toutes les versions : [CHANGELOG.md](CHANGELOG.md) · [{SITE_URL.removeprefix('https://')}/nouveautes]"
                  f"({SITE_URL}/nouveautes/)"]
    return "\n".join(lines)


def _first_sentence(text: str, limit: int = 200) -> str:
    """« Écran — ce qui change » réduit à sa première proposition, coupée sur un mot au-delà de `limit`."""
    text = " ".join(text.split())
    head, sep, rest = text.partition(" — ")
    if not sep or len(head) > 120:
        head, rest = "", text
    clause = re.split(r"(?<=[.;])\s", rest, maxsplit=1)[0].rstrip(" .;:,")
    out = f"{head} — {clause}" if head else clause
    if len(out) > limit:
        return out[:limit].rsplit(" ", 1)[0].rstrip(" ,;:(") + "…"
    return out + "."


SECTIONS = {
    "highlights": highlights_section,
    "audiences": audiences_section,
    "overview": overview_section,
    "features": features_section,
    "integrations": integrations_section,
}


def render_readme(text: str, features: dict, versions: list[dict], structures: dict) -> str:
    """Remplace le contenu entre `<!-- nom -->` et `<!-- /nom -->` pour chaque section connue."""
    rendered = {name: fn(features) for name, fn in SECTIONS.items()}
    rendered["news"] = news_section(versions, structures)
    for name, content in rendered.items():
        pattern = re.compile(rf"(<!-- {name} -->).*?(<!-- /{name} -->)", re.S)
        text = pattern.sub(lambda m, c=content: f"{m.group(1)}\n{c}\n{m.group(2)}", text)
    return text
