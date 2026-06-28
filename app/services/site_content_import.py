"""Import optionnel des contenus du site Jekyll (`_data/*.yml`).

Backlog v2 : le rapport reste **découplé** du site (design §0, les blocs sont
édités dans l'app). Cet import est un simple **pré-remplissage** : il lit les
`_data/*.yml` du dépôt Jekyll et en génère du HTML dans les `ReportContent`
éditables de l'exercice. L'admin retouche ensuite librement ; un ré-import
n'écrase un bloc que si `overwrite=True`.

Source configurable via `SITE_DATA_PATH` (cf. `config.py`), au choix :
- **chemin local** vers le dossier `_data` (ex. dépôt cloné) ;
- **URL GitHub** du dépôt (ex. `https://github.com/<org>/<repo>/tree/main/`) :
  les fichiers sont lus à distance via `raw.githubusercontent.com`, ce qui
  permet de générer le rapport **hors localhost** sans clone.
"""
import os
import re

import requests
import yaml
from flask import current_app
from markupsafe import escape

from app.extensions import db
from app.models import ReportContent

HTTP_TIMEOUT = 10  # secondes

# https://github.com/<owner>/<repo>/tree/<branch>[/<subpath>]
_GITHUB_TREE_RE = re.compile(
    r"^https?://github\.com/([^/]+)/([^/]+)/tree/([^/]+)/?(.*)$"
)


def data_path():
    return current_app.config.get("SITE_DATA_PATH")


def _is_remote(p):
    return bool(p) and p.startswith(("http://", "https://"))


def available():
    """Source utilisable : dossier local existant, ou URL distante configurée.

    Pour une URL on ne fait **pas** d'appel réseau ici (évite de ralentir le
    rendu de la page d'édition) ; les erreurs réseau sont remontées à l'import.
    """
    p = data_path()
    if _is_remote(p):
        return True
    return bool(p) and os.path.isdir(p)


def _raw_data_base(p):
    """Base 'raw' du dossier `_data` pour une URL GitHub (ou raw déjà fournie).

    `…/tree/main/`            → `…raw…/main/_data`
    `…/tree/main/_data`       → `…raw…/main/_data`
    `https://raw…/main/_data` → inchangé (sans `_data` final dupliqué).
    """
    m = _GITHUB_TREE_RE.match(p)
    if m:
        owner, repo, branch, subpath = m.groups()
        base = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}"
        subpath = subpath.strip("/")
        if subpath:
            base += "/" + subpath
    else:
        base = p.rstrip("/")
    if not base.endswith("/_data"):
        base += "/_data"
    return base


def _raw_repo_base(p):
    """Base 'raw' de la racine du dépôt (pour les assets : logos, images)."""
    m = _GITHUB_TREE_RE.match(p)
    if m:
        owner, repo, branch, _sub = m.groups()
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}"
    base = p.rstrip("/")
    if base.endswith("/_data"):
        base = base[: -len("/_data")]
    return base


def _asset_url(path):
    """Résout un chemin d'asset du site (ex. `/assets/img/x.png`) en URL absolue.

    Renvoie `None` si non résoluble (chemin vide, ou source locale dont les
    fichiers ne sont pas servis par l'app)."""
    if not path:
        return None
    path = str(path).strip()
    if path.startswith(("http://", "https://")):
        return path
    p = data_path() or ""
    if not _is_remote(p):
        return None
    return _raw_repo_base(p) + "/" + path.lstrip("/")


def _read_raw(filename):
    """Contenu brut d'un fichier de données ; None si absent (local)."""
    p = data_path() or ""
    if _is_remote(p):
        url = f"{_raw_data_base(p)}/{filename}"
        resp = requests.get(url, timeout=HTTP_TIMEOUT)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.text
    path = os.path.join(p, filename)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _load(filename):
    """Charge une liste depuis un fichier de données ; [] si absent/non-liste."""
    raw = _read_raw(filename)
    if raw is None:
        return []
    data = yaml.safe_load(raw)
    return data if isinstance(data, list) else []


def _txt(v):
    """Texte échappé, espaces normalisés (les YAML multi-lignes deviennent une ligne)."""
    return escape(" ".join(str(v or "").split()))


def _link(name, link):
    name = _txt(name)
    if link:
        return f'<a href="{escape(link)}">{name}</a>'
    return f"<strong>{name}</strong>"


# --- générateurs HTML par bloc -------------------------------------------


def _render_partners(items):
    cards = []
    for it in items:
        desc = _txt(it.get("description"))
        img = _asset_url(it.get("image"))
        logo = (f'<img class="partner-logo" src="{escape(img)}" alt="">'
                if img else "")
        cards.append(
            f'<div class="partner-item">{logo}'
            f'<div class="partner-body">{_link(it.get("name"), it.get("link"))}'
            f"<p>{desc}</p></div></div>"
        )
    return '<div class="partner-grid">' + "".join(cards) + "</div>"


def _render_team(items):
    cards = []
    for it in items:
        role = _txt(it.get("content"))
        img = _asset_url(it.get("image"))
        photo = (f'<img class="team-photo" src="{escape(img)}" alt="">'
                 if img else "")
        cards.append(
            f'<div class="team-item">{photo}'
            f'<div class="team-body"><strong>{_txt(it.get("name"))}</strong>'
            + (f'<span class="team-role">{role}</span>' if role else "")
            + "</div></div>"
        )
    return '<div class="team-grid">' + "".join(cards) + "</div>"


def _render_missions(items):
    blocks = []
    for it in items:
        blocks.append(
            f"<p><strong>{_txt(it.get('name'))}</strong> — {_txt(it.get('description'))}</p>"
        )
    return "".join(blocks)


def _render_services(items):
    blocks = []
    for it in items:
        blocks.append(
            f"<p><strong>{_txt(it.get('name'))}</strong> — {_txt(it.get('description'))}</p>"
        )
    return "".join(blocks)


# (block_key, titre par défaut, fichier yml, générateur)
MAPPING = [
    ("partenaires", "Partenaires & coopération", "partners.yml", _render_partners),
    ("gouvernance", "Gouvernance", "infos.yml", _render_team),
    ("intro_reemploi", "Nos missions", "missions.yml", _render_missions),
    ("intro_boutique", "Nos services", "services.yml", _render_services),
]


def preview():
    """Liste des blocs importables (pour l'UI).

    `count` n'est calculé que pour une source **locale** (pas d'appel réseau
    au rendu de la page) ; il vaut `None` pour une source distante.
    """
    remote = _is_remote(data_path())
    out = []
    for block_key, title, filename, _render in MAPPING:
        count = None if remote else len(_load(filename))
        out.append({"block_key": block_key, "title": title,
                    "filename": filename, "count": count})
    return out


def import_site_content(fy, overwrite=False):
    """Pré-remplit les `ReportContent` de l'exercice depuis les `_data/*.yml`.

    Retour : `{"imported": [...keys], "skipped": [...keys], "errors": [...]}`.
    `skipped` = bloc déjà rempli et `overwrite=False`, ou fichier vide.
    """
    if not available():
        return {"imported": [], "skipped": [], "errors": ["Source _data du site introuvable."]}

    existing = {
        c.block_key: c
        for c in ReportContent.query.filter_by(fiscal_year_id=fy.id).all()
    }
    imported, skipped, errors = [], [], []

    for block_key, title, filename, render in MAPPING:
        try:
            items = _load(filename)
        except (yaml.YAMLError, requests.RequestException, OSError) as e:
            errors.append(f"{filename} : {e}")
            continue
        if not items:
            skipped.append(block_key)
            continue

        row = existing.get(block_key)
        if row is not None and (row.body_html or "").strip() and not overwrite:
            skipped.append(block_key)
            continue

        body = render(items)
        if row is None:
            row = ReportContent(fiscal_year_id=fy.id, block_key=block_key)
            db.session.add(row)
            existing[block_key] = row
        if not (row.title or "").strip():
            row.title = title
        row.body_html = body
        imported.append(block_key)

    db.session.commit()
    return {"imported": imported, "skipped": skipped, "errors": errors}
