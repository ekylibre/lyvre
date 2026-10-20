"""Configuration de la navigation principale.

Ce fichier décrit **l'intégralité** des menus et sous-menus de l'application.
L'affichage de chaque menu / sous-menu est piloté par le **plan comptable de
l'instance courante** (``Instance.chart``) via la clé ``charts`` :

    "charts": ["asso", "sci"]   # visible pour les deux plans comptables
    "charts": ["asso"]          # visible uniquement pour une association
    "charts": ["sci"]           # visible uniquement pour une SCI

Les menus communs sont déclarés pour les deux plans (``_ALL``) ; les
fonctionnalités propres à une association (adhérents, bénévolat, Stancer,
Odoo, indicateurs, tonnages) sont réservées au plan ``asso`` (``_ASSO``).
Il suffit d'éditer les listes ``charts`` ci-dessous pour ajuster le
paramétrage menu ⇄ plan comptable (aucun code à modifier ailleurs).

Structure d'une entrée de menu (niveau 1) :
    {
        "key":     identifiant stable du menu (pour d'éventuels overrides),
        "label":   libellé affiché,
        "charts":  plans comptables pour lesquels le menu apparaît,
        "admin_only": True,          # (optionnel) réservé aux administrateurs
        # -- lien simple --
        "endpoint": "blueprint.vue", # cible url_for()
        "active":   ["blueprint"],  # blueprints marquant l'onglet actif
        # -- OU menu déroulant --
        "active":   ["bp1", "bp2"], # blueprints marquant l'onglet actif
        "items":    [ ...sous-menus... ],
    }

Structure d'un sous-menu (items) :
    {"key": "...", "label": "...", "endpoint": "bp.vue", "charts": [...], "admin_only": bool}
    {"divider": True, "charts": [...]}   # séparateur horizontal
"""

from __future__ import annotations

# Tous les plans comptables connus (doit rester cohérent avec
# app.services.instance_provisioning.CHARTS et seed_accounts.CHARTS).
ALL_CHARTS = ("asso", "sci")
DEFAULT_CHART = "asso"

# Raccourci : visible pour tous les plans comptables.
_ALL = list(ALL_CHARTS)
# Raccourci : fonctionnalités propres à une association (adhérents, bénévolat,
# boutique/POS, indicateurs d'impact…), masquées pour une SCI.
_ASSO = ["asso"]


MENUS = [
    # -------------------------------------------------------------- Tableau de bord
    {
        "key": "dashboard",
        "label": "Tableau de bord",
        "charts": _ALL,
        "endpoint": "dashboard.index",
        "active": ["dashboard"],
    },
    # --------------------------------------------------------------------- Compta
    {
        "key": "compta",
        "label": "Compta",
        "charts": _ALL,
        "active": ["accounts", "journals", "fiscal_years", "entries", "reports"],
        "items": [
            {"key": "entries", "label": "Écritures", "endpoint": "entries.index", "charts": _ALL},
            {"divider": True, "charts": _ALL},
            {"key": "balance", "label": "Balance", "endpoint": "reports.balance", "charts": _ALL},
            {"key": "grand_livre", "label": "Grand livre", "endpoint": "reports.grand_livre", "charts": _ALL},
            {"key": "bilan", "label": "Bilan", "endpoint": "reports.bilan", "charts": _ALL},
            {"key": "compte_resultat", "label": "Compte de résultat", "endpoint": "reports.compte_resultat", "charts": _ALL},
            {"divider": True, "charts": _ALL},
            {"key": "accounts", "label": "Plan comptable", "endpoint": "accounts.index", "charts": _ALL},
            {"key": "journals", "label": "Journaux", "endpoint": "journals.index", "charts": _ALL},
            {"key": "fiscal_years", "label": "Exercices", "endpoint": "fiscal_years.index", "charts": _ALL},
        ],
    },
    # --------------------------------------------------------------------- Banque
    {
        "key": "banque",
        "label": "Banque",
        "charts": _ALL,
        "active": ["imports.ofx", "bank_accounts", "reconciliation", "payouts"],
        "items": [
            {"key": "bank_accounts", "label": "Comptes bancaires", "endpoint": "bank_accounts.index", "charts": _ALL},
            {"key": "reconciliation", "label": "Rapprochement", "endpoint": "reconciliation.index", "charts": _ALL},
            {"divider": True, "charts": _ALL},
            {"key": "payouts", "label": "Versements Stancer", "endpoint": "payouts.index", "charts": _ASSO},
        ],
    },
    # ---------------------------------------------------------------------- Tiers
    {
        "key": "tiers",
        "label": "Tiers",
        "charts": _ALL,
        "active": ["entities", "rules", "work_times"],
        "items": [
            {"key": "entities", "label": "Entités", "endpoint": "entities.index", "charts": _ALL},
            {"key": "members", "label": "Adhérents", "endpoint": "entities.members", "charts": _ASSO},
            {"key": "work_times", "label": "Temps de travaux", "endpoint": "work_times.index", "charts": _ASSO},
            {"divider": True, "charts": _ALL},
            {"key": "rules", "label": "Règles de catégorisation", "endpoint": "rules.index", "charts": _ALL},
        ],
    },
    # ----------------------------------------------------------------------- Odoo
    {
        "key": "odoo",
        "label": "Odoo",
        "charts": _ASSO,
        "active": ["orders", "customer_invoices"],
        "items": [
            {"key": "orders", "label": "Commandes POS", "endpoint": "orders.index", "charts": _ALL},
            {"key": "customer_invoices", "label": "Factures clients", "endpoint": "customer_invoices.index", "charts": _ALL},
        ],
    },
    # ----------------------------------------------------------------- Indicateurs
    {
        "key": "indicateurs",
        "label": "Indicateurs",
        "charts": _ASSO,
        "active": ["impact", "activity_report"],
        "items": [
            {"key": "impact", "label": "Visibilité & Impact", "endpoint": "impact.index", "charts": _ALL},
            {"key": "activity_report", "label": "Rapport d'activité", "endpoint": "activity_report.index", "charts": _ALL},
        ],
    },
    # ------------------------------------------------------------- Imports/Exports
    {
        "key": "imports",
        "label": "Imports/Exports",
        "charts": _ALL,
        "active": ["imports"],
        "items": [
            {"key": "ofx", "label": "Fichier OFX", "endpoint": "imports.ofx", "charts": _ALL},
            {"key": "eco_import", "label": "Import de tonnages", "endpoint": "activity_report.eco", "charts": _ASSO, "admin_only": True},
        ],
    },
    # ----------------------------------------------------------------- Configuration
    {
        "key": "configuration",
        "label": "Configuration",
        "charts": _ALL,
        "admin_only": True,
        "active": ["external_connections"],
        "items": [
            {"key": "external_connections", "label": "Connexions externes", "endpoint": "external_connections.index", "charts": _ALL},
        ],
    },
]


def _visible(entry: dict, chart: str, is_admin: bool) -> bool:
    """Une entrée est visible si le plan comptable correspond et, le cas
    échéant, si l'utilisateur est administrateur."""
    if chart not in entry.get("charts", ALL_CHARTS):
        return False
    if entry.get("admin_only") and not is_admin:
        return False
    return True


def _clean_items(items: list[dict], chart: str, is_admin: bool) -> list[dict]:
    """Filtre les sous-menus par plan comptable / droits, puis nettoie les
    séparateurs orphelins (en tête, en fin, ou consécutifs)."""
    kept: list[dict] = []
    for item in items:
        if not _visible(item, chart, is_admin):
            continue
        if item.get("divider"):
            # pas de séparateur en tête ni deux séparateurs de suite
            if not kept or kept[-1].get("divider"):
                continue
        kept.append(item)
    # retire un éventuel séparateur en fin de liste
    while kept and kept[-1].get("divider"):
        kept.pop()
    return kept


def build_nav(chart: str | None = None, is_admin: bool = False) -> list[dict]:
    """Retourne l'arborescence des menus visibles pour ``chart``.

    Les menus déroulants sans aucun sous-menu visible sont masqués.
    """
    chart = (chart or DEFAULT_CHART).strip().lower()
    nav: list[dict] = []
    for menu in MENUS:
        if not _visible(menu, chart, is_admin):
            continue
        if "items" in menu:
            items = _clean_items(menu["items"], chart, is_admin)
            if not items:
                continue  # dropdown vide → masqué
            nav.append({**menu, "items": items})
        else:
            nav.append(menu)
    return nav
