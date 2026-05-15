"""Helpers partagés pour le tri par date + filtre par mois sur les listes.

Convention des paramètres GET :
- `sort` : `asc` ou `desc` (défaut `desc`)
- `month` : chaîne `YYYY-MM` (ex. `2026-03`)

Le filtre mois est alimenté par les 12 mois de l'exercice comptable courant
(``FiscalYear.closed=False`` le plus récent), pour que le dropdown soit
identique sur toutes les listes.
"""
from datetime import date, datetime

from app.models import FiscalYear


MONTHS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


def parse_sort(arg, default="desc"):
    """Retourne 'asc' ou 'desc' à partir d'un query arg."""
    value = (arg or "").strip().lower()
    if value in ("asc", "desc"):
        return value
    return default


def parse_month(arg):
    """Parse 'YYYY-MM' → (year, month). Retourne None si invalide ou vide."""
    value = (arg or "").strip()
    if not value:
        return None
    try:
        dt = datetime.strptime(value, "%Y-%m")
        return dt.year, dt.month
    except ValueError:
        return None


def month_bounds(year, month):
    """Retourne (premier_jour, premier_jour_du_mois_suivant) — bornes [a, b)."""
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return start, end


def current_fiscal_year():
    """Renvoie l'exercice comptable de référence (ouvert le plus récent, sinon le plus récent tout court)."""
    fy = (
        FiscalYear.query.filter_by(closed=False)
        .order_by(FiscalYear.start_date.desc())
        .first()
    )
    if fy is not None:
        return fy
    return FiscalYear.query.order_by(FiscalYear.start_date.desc()).first()


def month_options_for_fy(fy=None):
    """Retourne la liste des mois de l'exercice comptable, format dropdown.

    Renvoie [{'value': 'YYYY-MM', 'label': 'mars 2026'}, ...] dans l'ordre
    chronologique. Si aucun exercice n'existe, retourne une liste vide.
    """
    if fy is None:
        fy = current_fiscal_year()
    if fy is None:
        return []
    options = []
    cur = date(fy.start_date.year, fy.start_date.month, 1)
    end = date(fy.end_date.year, fy.end_date.month, 1)
    while cur <= end:
        options.append({
            "value": cur.strftime("%Y-%m"),
            "label": f"{MONTHS_FR[cur.month - 1]} {cur.year}",
        })
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)
    return options


def apply_date_sort(query, column, sort):
    """Ajoute un ORDER BY column ASC/DESC sur la query (nullslast en DESC)."""
    if sort == "asc":
        return query.order_by(column.asc().nullsfirst())
    return query.order_by(column.desc().nullslast())


def apply_month_filter(query, column, year_month):
    """Filtre WHERE column >= start AND column < end. `year_month` = (year, month) ou None."""
    if not year_month:
        return query
    start, end = month_bounds(*year_month)
    return query.filter(column >= start, column < end)


def sort_and_filter_context(sort, month_value, fy=None):
    """Sucre syntaxique : prépare le dict de contexte à passer aux templates."""
    return {
        "current_sort": sort,
        "current_month": month_value or "",
        "month_options": month_options_for_fy(fy),
    }
