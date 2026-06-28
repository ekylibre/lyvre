"""Logo de la structure (commun à tous les exercices) pour le rapport d'activité.

Stocké à un emplacement fixe ``instance/uploads/branding/logo.<ext>`` (pas de
table dédiée : un seul logo par structure/tenant). S'il est présent, le rapport
l'utilise sur la couverture et les pieds de page ; sinon il retombe sur le
pictogramme SVG par défaut.
"""
import glob
import os

from flask import current_app

BRAND_DIR = os.path.join("uploads", "branding")
ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif"}


def _absdir():
    return os.path.join(current_app.instance_path, BRAND_DIR)


def logo_relpath():
    """Chemin du logo relatif à `instance/` (ou None s'il n'y en a pas)."""
    matches = sorted(glob.glob(os.path.join(_absdir(), "logo.*")))
    if not matches:
        return None
    return os.path.relpath(matches[0], current_app.instance_path)


def logo_abspath():
    rel = logo_relpath()
    return os.path.join(current_app.instance_path, rel) if rel else None


def logo_src(pdf=False):
    """URL d'affichage du logo selon le mode de rendu (None si absent).

    - HTML : endpoint Flask `logo_file` ;
    - PDF (weasyprint) : chemin `file://` lu sur le disque."""
    rel = logo_relpath()
    if not rel:
        return None
    if pdf:
        return "file://" + os.path.join(current_app.instance_path, rel)
    from flask import url_for
    return url_for("activity_report.logo_file")


def save_logo(file):
    """Enregistre le logo uploadé (remplace l'existant). Lève ValueError si ext. invalide."""
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        raise ValueError(
            "Format non supporté (png, jpg, svg, webp, gif attendus)."
        )
    absdir = _absdir()
    os.makedirs(absdir, exist_ok=True)
    for old in glob.glob(os.path.join(absdir, "logo.*")):
        os.remove(old)
    file.save(os.path.join(absdir, "logo" + ext))


def delete_logo():
    for old in glob.glob(os.path.join(_absdir(), "logo.*")):
        try:
            os.remove(old)
        except OSError:
            pass
