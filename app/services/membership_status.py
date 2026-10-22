"""Calculs métier sur le statut d'adhésion.

Fonctions pures dérivant la « date anniversaire » (échéance) et le statut d'un
adhérent à partir des deux dates de dernière adhésion :
- ``last_ha`` : dernière commande HelloAsso de type Membership (datetime ou None)
- ``last_pos`` : dernière commande Odoo POS avec un article d'adhésion (datetime ou None)

Réutilisées par la vue liste, les exports (CSV/XLSX) et la relance email.
"""
from datetime import date, datetime, timedelta

MEMBERSHIP_DAYS = 365
EXPIRING_SOON_DAYS = 30

# Gravité croissante : rouge (expiré) < orange (bientôt) < vert (à jour).
STATUS_ORDER = {"red": 0, "orange": 1, "green": 2}

def _as_date(value):
    """Normalise un datetime/date/None en date (ou None)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value


def member_birthday(last_ha, last_pos, today=None):
    """Date d'échéance de l'adhésion = dernière adhésion + 365 jours.

    - Aucune adhésion connue           -> date du jour.
    - Au moins une adhésion connue      -> date la plus récente + 365 jours.
    """
    today = today or date.today()
    candidates = [_as_date(d) for d in (last_ha, last_pos) if d is not None]
    if not candidates:
        return today
    return max(candidates) + timedelta(days=MEMBERSHIP_DAYS)


def member_status(last_ha, last_pos, today=None):
    """Retourne ``{"status", "color", "label"}``.

    ``status`` (présence de données d'adhésion) :
        - HA et POS absents        -> "?"
        - HA absent, POS présent   -> "asha"
        - sinon (HA présent)       -> "ok"

    ``color`` (échéance vs aujourd'hui), avec ``b = member_birthday`` :
        - b <= today               -> "red"   (échéance atteinte/dépassée)
        - today < b <= today+30j   -> "orange" (expire bientôt)
        - b > today+30j            -> "green" (à jour)
    """
    today = today or date.today()
    birthday = member_birthday(last_ha, last_pos, today)

    if last_ha is None and last_pos is None:
        status = "?"
    elif last_ha is None:
        status = "asha"
    else:
        status = "ok"

    if birthday <= today:
        color = "red"
    elif birthday <= today + timedelta(days=EXPIRING_SOON_DAYS):
        color = "orange"
    else:
        color = "green"

    return {
        "status": status,
        "color": color,
        "label": status,
    }


def build_member_rows(members_list, last_ha, last_pos, today=None):
    """Construit la liste de dicts enrichis (source unique liste/export/relance)."""
    today = today or date.today()
    rows = []
    for e in members_list:
        ha = last_ha.get(e.id)
        pos = last_pos.get(e.id)
        birthday = member_birthday(ha, pos, today)
        status = member_status(ha, pos, today)
        rows.append({
            "entity": e,
            "name": e.name,
            "email": e.email,
            "is_member": e.is_member,
            "is_benevole": e.is_benevole,
            "notes": e.notes,
            "last_ha": ha,
            "last_pos": pos,
            "birthday": birthday,
            "status": status["status"],
            "color": status["color"],
            "label": status["label"],
        })
    return rows


def sort_member_rows(rows, sort_by="name", sort="asc"):
    """Trie les rows en mémoire sur Nom, Date anniversaire ou Statut."""
    keys = {
        "name": lambda r: (r["name"] or "").lower(),
        "birthday": lambda r: r["birthday"],
        "status": lambda r: (STATUS_ORDER[r["color"]], (r["name"] or "").lower()),
    }
    key = keys.get(sort_by, keys["name"])
    return sorted(rows, key=key, reverse=(sort == "desc"))
