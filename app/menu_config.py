"""Configuration de la navigation principale.

Ce fichier décrit **l'intégralité** des menus et sous-menus de l'application.
L'affichage de chaque menu / sous-menu est piloté par le **plan comptable de
l'instance courante** (``Instance.chart``) via la clé ``charts`` :

    "charts": ["asso", "sci", "societe", "agri"]  # visible pour tous les plans comptables
    "charts": ["asso"]                    # visible uniquement pour une association
    "charts": ["sci"]                     # visible uniquement pour une SCI

Les menus communs sont déclarés pour tous les plans (``_ALL``) ; les
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
ALL_CHARTS = ("asso", "sci", "societe", "agri")
DEFAULT_CHART = "asso"

# Raccourci : visible pour tous les plans comptables.
_ALL = list(ALL_CHARTS)
# Raccourci : fonctionnalités propres à une association (adhérents, bénévolat,
# boutique/POS, indicateurs d'impact…), masquées pour une SCI ou une société.
_ASSO = ["asso"]
# Comptabilité simplifiée (recettes et dépenses) : associations et exploitations au micro-BA (lot AG1.b).
_SIMPLE_CHARTS = ["asso", "agri"]


BOOKKEEPING_MODES = ("double", "simple")
_DOUBLE = ["double"]   # écrans de partie double (débit / crédit), masqués en comptabilité simplifiée
_SIMPLE = ["simple"]   # écrans de la comptabilité simplifiée


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
        "active": ["accounts", "journals", "fiscal_years", "vat_returns", "rfa", "agenda", "products", "entries", "reports", "projects", "budgets", "budget_tracking",
                   "lettering", "assets"],
        "items": [
            {"key": "entries", "label": "Écritures", "endpoint": "entries.index", "charts": _ALL, "bookkeeping": _DOUBLE},
            {"divider": True, "charts": _ALL},
            {"key": "balance", "label": "Balance", "endpoint": "reports.balance", "charts": _ALL, "bookkeeping": _DOUBLE},
            {"key": "grand_livre", "label": "Grand livre", "endpoint": "reports.grand_livre", "charts": _ALL, "bookkeeping": _DOUBLE},
            {"key": "lettering", "label": "Lettrage", "endpoint": "lettering.index", "charts": _ALL, "bookkeeping": _DOUBLE},
            {"key": "bilan", "label": "Bilan", "endpoint": "reports.bilan", "charts": _ALL, "bookkeeping": _DOUBLE},
            {"key": "compte_resultat", "label": "Compte de résultat", "endpoint": "reports.compte_resultat", "charts": _ALL, "bookkeeping": _DOUBLE},
            {"key": "sig", "label": "Soldes intermédiaires", "endpoint": "reports.sig", "charts": ["agri"], "bookkeeping": _DOUBLE},
            {"key": "assets", "label": "Immobilisations", "endpoint": "assets.index", "charts": _ALL},
            {"key": "projects", "label": "Projets", "endpoint": "projects.index", "charts": _ALL},
            {"key": "budgets", "label": "Budget", "endpoint": "budgets.index", "charts": _ALL},
            {"key": "budget_tracking", "label": "Suivi budgétaire", "endpoint": "budgets.tracking", "charts": _ALL},
            {"divider": True, "charts": _ALL},
            {"key": "accounts", "label": "Plan comptable", "endpoint": "accounts.index", "charts": _ALL, "bookkeeping": _DOUBLE},
            {"key": "journals", "label": "Journaux", "endpoint": "journals.index", "charts": _ALL, "bookkeeping": _DOUBLE},
            {"key": "fiscal_years", "label": "Exercices", "endpoint": "fiscal_years.index", "charts": _ALL},
            {"key": "vat_returns", "label": "Déclarations de TVA", "endpoint": "vat_returns.index", "charts": _ALL,
             "feature": "vat_returns", "bookkeeping": _DOUBLE},
            {"key": "agenda", "label": "Échéancier", "endpoint": "agenda.index", "charts": ["agri"]},
            {"key": "rfa", "label": "Remboursement forfaitaire", "endpoint": "rfa.index", "charts": ["agri"]},
            {"key": "products", "label": "Catalogue", "endpoint": "products.index", "charts": _ALL, "bookkeeping": _DOUBLE},
        ],
    },
    # --------------------------------------------------------------------- Banque
    {
        "key": "banque",
        "label": "Banque",
        "charts": _ALL,
        "active": ["imports.ofx", "bank_accounts", "reconciliation", "payouts", "cash_forecast"],
        "items": [
            {"key": "bank_accounts", "label": "Comptes et caisses", "endpoint": "bank_accounts.index", "charts": _ALL},
            {"key": "reconciliation", "label": "Rapprochement", "endpoint": "reconciliation.index", "charts": _ALL, "bookkeeping": _DOUBLE},
            {"key": "cash_forecast", "label": "Prévisionnel", "endpoint": "cash_forecast.index", "charts": _ALL},
            {"divider": True, "charts": _ALL, "feature": "stancer"},
            # Intégration Stancer activée (interrupteur de l'instance), quelle que soit la structure.
            {"key": "payouts", "label": "Versements Stancer", "endpoint": "payouts.index", "charts": _ALL,
             "feature": "stancer"},
        ],
    },
    # ------------------------------------------------- Recettes et dépenses (mode simple)
    {
        "key": "simple_operations",
        "label": "Recettes et dépenses",
        "charts": _SIMPLE_CHARTS,
        "bookkeeping": _SIMPLE,
        "endpoint": "simple_operations.index",
        "active": ["simple_operations"],
    },
    {
        "key": "simple_reports",
        "label": "États",
        "charts": _SIMPLE_CHARTS,
        "bookkeeping": _SIMPLE,
        "endpoint": "simple_reports.index",
        "active": ["simple_reports"],
    },
    # ---------------------------------------------------------------------- Dons
    {
        "key": "donations",
        "label": "Dons",
        "charts": _ASSO,
        "active": ["receipts"],
        "items": [
            {"key": "receipts", "label": "Reçus fiscaux", "endpoint": "receipts.index", "charts": _ASSO},
        ],
    },
    # -------------------------------------------------------------------- Achats
    {
        "key": "purchases",
        "label": "Achats",
        "charts": _ALL,
        "bookkeeping": _DOUBLE,   # comptabilité d'engagement (401)
        "active": ["purchases", "subscriptions"],
        "items": [
            {"key": "purchases_list", "label": "Factures d'achat", "endpoint": "purchases.index", "charts": _ALL},
            {"key": "subscriptions", "label": "Abonnements", "endpoint": "subscriptions.index", "charts": _ALL},
        ],
    },
    # -------------------------------------------------------------------- Ventes
    {
        "key": "sales",
        "label": "Ventes",
        "charts": _ALL,
        "bookkeeping": _DOUBLE,   # journal VE, comptes clients 411
        "active": ["sales", "leases", "rent_indices"],
        "items": [
            {"key": "sales_list", "label": "Factures, avoirs et devis", "endpoint": "sales.index", "charts": _ALL},
            {"key": "sales_due", "label": "À émettre", "endpoint": "sales.due", "charts": _ALL},
            {"key": "sales_recurring", "label": "Factures récurrentes", "endpoint": "sales.recurring", "charts": _ALL},
            {"key": "leases", "label": "Baux et quittances", "endpoint": "leases.index", "charts": _ALL},
            {"key": "rent_indices", "label": "Indices de loyer", "endpoint": "rent_indices.index", "charts": _ALL},
        ],
    },
    # ------------------------------------------------------------------- Associés
    {
        "key": "associates",
        "label": "Associés",
        "charts": _ALL,
        "feature": "associates",  # option de l'instance (Instance.has_associates)
        "active": ["associates", "share_movements", "associate_expenses"],
        "items": [
            {"key": "associates_list", "label": "Associés", "endpoint": "associates.index", "charts": _ALL},
            {"key": "share_movements", "label": "Registre des parts", "endpoint": "share_movements.index",
             "charts": _ALL},
            {"key": "associate_expenses", "label": "Notes de frais", "endpoint": "associate_expenses.index",
             "charts": _ALL, "bookkeeping": _DOUBLE},
            {"divider": True, "charts": _ALL},
            {"key": "associates_import", "label": "Importer (CSV)", "endpoint": "associates.import_csv",
             "charts": _ALL, "admin_only": True},
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
        "charts": _ALL,
        "feature": "odoo",  # intégration Odoo activée
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
            {"key": "reprise", "label": "Reprise d'historique", "endpoint": "imports.reprise", "charts": _ALL,
             "admin_only": True, "bookkeeping": _DOUBLE},
            {"key": "eco_import", "label": "Import de tonnages", "endpoint": "activity_report.eco", "charts": _ASSO, "admin_only": True},
        ],
    },
    # ----------------------------------------------------------------- Configuration
    {
        "key": "configuration",
        "label": "Configuration",
        "charts": _ALL,
        "admin_only": True,
        "active": ["organization", "integrations", "access", "receipts_settings", "simple_categories", "account_roles",
                   "lease_templates"],
        "items": [
            {"key": "organization", "label": "Structure", "endpoint": "organization.index", "charts": _ALL},
            {"key": "receipts_settings", "label": "Reçus fiscaux", "endpoint": "receipts.settings", "charts": _ASSO},
            {"key": "simple_categories", "label": "Catégories", "endpoint": "simple_categories.index", "charts": _SIMPLE_CHARTS,
             "bookkeeping": _SIMPLE},
            {"key": "account_roles", "label": "Comptes par défaut", "endpoint": "account_roles.index", "charts": _ALL,
             "bookkeeping": _DOUBLE},
            {"key": "lease_templates", "label": "Modèles de bail", "endpoint": "lease_templates.index", "charts": _ALL},
            {"key": "integrations", "label": "Intégrations", "endpoint": "integrations.index", "charts": _ALL},
            {"key": "access", "label": "Accès", "endpoint": "access.index", "charts": _ALL},
        ],
    },
]


def _visible(entry: dict, chart: str, is_admin: bool, bookkeeping: str = "double",
             features: frozenset = frozenset()) -> bool:
    """Une entrée est visible si le plan comptable et le mode de tenue correspondent, si
    l'option qu'elle demande (`feature`) est active et, le cas échéant, si l'utilisateur est
    administrateur."""
    if entry.get("feature") and entry["feature"] not in features:
        return False
    if chart not in entry.get("charts", ALL_CHARTS):
        return False
    if bookkeeping not in entry.get("bookkeeping", BOOKKEEPING_MODES):
        return False
    if entry.get("admin_only") and not is_admin:
        return False
    return True


def _clean_items(items: list[dict], chart: str, is_admin: bool, bookkeeping: str = "double",
                 features: frozenset = frozenset()) -> list[dict]:
    """Filtre les sous-menus par plan comptable / droits, puis nettoie les
    séparateurs orphelins (en tête, en fin, ou consécutifs)."""
    kept: list[dict] = []
    for item in items:
        if not _visible(item, chart, is_admin, bookkeeping, features):
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


def build_nav(chart: str | None = None, is_admin: bool = False, bookkeeping: str | None = None,
              features=()) -> list[dict]:
    """Retourne l'arborescence des menus visibles pour ``chart``, le mode de tenue et les options
    actives de l'instance (``features`` : {"associates"}…).

    Les menus déroulants sans aucun sous-menu visible sont masqués.
    """
    chart = (chart or DEFAULT_CHART).strip().lower()
    bookkeeping = bookkeeping if bookkeeping in BOOKKEEPING_MODES else "double"
    features = frozenset(features)
    nav: list[dict] = []
    for menu in MENUS:
        if not _visible(menu, chart, is_admin, bookkeeping, features):
            continue
        if "items" in menu:
            items = _clean_items(menu["items"], chart, is_admin, bookkeeping, features)
            if not items:
                continue  # dropdown vide → masqué
            nav.append({**menu, "items": items})
        else:
            nav.append(menu)
    return nav
