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
    {"key": "...", "label": "...", "items": [...]}   # sous-menu de 3e niveau (lot NV1)

Icônes (lot NV1) : "icon" = nom d'icône Lucide (kebab-case) ; "pictogram" = pictogramme agric,
affiché seulement en pastille (cartes, en-têtes de page).
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
        "icon": "layout-dashboard",
        "label": "Tableau de bord",
        "charts": _ALL,
        "endpoint": "dashboard.index",
        "active": ["dashboard"],
    },
    # --------------------------------------------------------------------- Compta
    # Lot NV1 (claudedocs/design_navigation.md § 2) : saisie et éditions au premier niveau, puis trois sous-menus.
    {
        "key": "compta",
        "label": "Compta",
        "icon": "calculator",
        "charts": _ALL,
        "active": ["accounts", "journals", "fiscal_years", "vat_returns", "rfa", "ereporting", "aids", "stock", "tax_result",
                   "msa", "products", "entries", "reports", "lettering", "assets"],
        "items": [
            {"key": "entries", "label": "Écritures", "icon": "notebook-pen", "endpoint": "entries.index", "charts": _ALL,
             "bookkeeping": _DOUBLE},
            {"key": "lettering", "label": "Lettrage", "icon": "link", "endpoint": "lettering.index", "charts": _ALL,
             "bookkeeping": _DOUBLE},
            {"key": "editions", "label": "Éditions comptables", "icon": "file-chart-column", "charts": _ALL,
             "bookkeeping": _DOUBLE, "items": [
                {"key": "balance", "label": "Balance", "icon": "scale", "endpoint": "reports.balance", "charts": _ALL},
                {"key": "grand_livre", "label": "Grand livre", "icon": "book-text", "endpoint": "reports.grand_livre",
                 "charts": _ALL},
                {"key": "bilan", "label": "Bilan", "icon": "landmark", "endpoint": "reports.bilan", "charts": _ALL},
                {"key": "compte_resultat", "label": "Compte de résultat", "icon": "chart-line",
                 "endpoint": "reports.compte_resultat", "charts": _ALL},
                {"key": "sig", "label": "Soldes intermédiaires", "icon": "chart-no-axes-column", "endpoint": "reports.sig",
                 "charts": ["agri"]},
            ]},
            {"key": "fixed_and_stock", "label": "Immobilisations et stocks", "icon": "warehouse", "charts": _ALL, "items": [
                {"key": "assets", "label": "Immobilisations", "icon": "building-2", "endpoint": "assets.index", "charts": _ALL},
                {"key": "stock", "label": "Inventaire de clôture", "icon": "boxes", "pictogram": "silo",
                 "endpoint": "stock.index", "charts": ["agri"], "bookkeeping": _DOUBLE},
            ]},
            {"divider": True, "charts": _ALL},
            {"key": "tax_social", "label": "Fiscal et social", "icon": "landmark", "charts": _ALL, "items": [
                {"key": "vat_returns", "label": "Déclarations de TVA", "icon": "receipt-text", "endpoint": "vat_returns.index",
                 "charts": _ALL, "feature": "vat_returns", "bookkeeping": _DOUBLE},
                {"key": "rfa", "label": "Remboursement forfaitaire", "icon": "hand-coins", "endpoint": "rfa.index",
                 "charts": ["agri"]},
                {"key": "ereporting", "label": "E-reporting B2C", "icon": "send", "endpoint": "ereporting.index",
                 "charts": ["agri"]},
                {"key": "tax_result", "label": "Résultat fiscal", "icon": "scale", "endpoint": "tax_result.index",
                 "charts": ["agri"], "bookkeeping": _DOUBLE},
                {"key": "msa", "label": "Cotisations MSA", "icon": "heart-pulse", "pictogram": "farmer", "endpoint": "msa.index",
                 "charts": ["agri"], "bookkeeping": _DOUBLE},
                {"key": "aids", "label": "Aides et subventions", "icon": "sprout", "pictogram": "plots-telepac",
                 "endpoint": "aids.index", "charts": ["agri"]},
            ]},
            {"key": "accounting_settings", "label": "Paramètres comptables", "icon": "settings-2", "charts": _ALL, "items": [
                {"key": "accounts", "label": "Plan comptable", "icon": "list-tree", "endpoint": "accounts.index",
                 "charts": _ALL, "bookkeeping": _DOUBLE},
                {"key": "journals", "label": "Journaux", "icon": "book-open", "endpoint": "journals.index", "charts": _ALL,
                 "bookkeeping": _DOUBLE},
                {"key": "fiscal_years", "label": "Exercices", "icon": "calendar-range", "endpoint": "fiscal_years.index",
                 "charts": _ALL},
                {"key": "products", "label": "Catalogue", "icon": "package", "endpoint": "products.index", "charts": _ALL,
                 "bookkeeping": _DOUBLE},
            ]},
        ],
    },
    # -------------------------------------------------------------------- Gestion (lot NV1)
    {
        "key": "gestion",
        "label": "Gestion",
        "icon": "briefcase",
        "charts": _ALL,
        "active": ["projects", "budgets", "budget_tracking", "agenda", "activities", "analytic", "activity_margins"],
        "items": [
            {"key": "projects", "label": "Projets", "icon": "folder-kanban", "endpoint": "projects.index", "charts": _ALL},
            {"key": "budgets", "label": "Budget", "icon": "piggy-bank", "endpoint": "budgets.index", "charts": _ALL},
            {"key": "budget_tracking", "label": "Suivi budgétaire", "icon": "gauge", "endpoint": "budgets.tracking",
             "charts": _ALL},
            {"divider": True, "charts": ["agri"]},
            {"key": "agenda", "label": "Échéancier", "icon": "calendar-clock", "endpoint": "agenda.index", "charts": ["agri"]},
            {"key": "activities", "label": "Activités", "icon": "tractor", "pictogram": "farm", "endpoint": "activities.index",
             "charts": ["agri"]},
            {"key": "analytic", "label": "Ventilation analytique", "icon": "split", "endpoint": "analytic.index",
             "charts": ["agri"]},
            {"key": "activity_margins", "label": "Marges par activité", "icon": "trending-up",
             "endpoint": "activities.margins", "charts": ["agri"]},
        ],
    },
    # --------------------------------------------------------------------- Banque
    {
        "key": "banque",
        "icon": "landmark",
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
        "icon": "wallet",
        "label": "Recettes et dépenses",
        "charts": _SIMPLE_CHARTS,
        "bookkeeping": _SIMPLE,
        "endpoint": "simple_operations.index",
        "active": ["simple_operations"],
    },
    {
        "key": "simple_reports",
        "icon": "chart-line",
        "label": "États",
        "charts": _SIMPLE_CHARTS,
        "bookkeeping": _SIMPLE,
        "endpoint": "simple_reports.index",
        "active": ["simple_reports"],
    },
    # ---------------------------------------------------------------------- Dons
    {
        "key": "donations",
        "icon": "heart",
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
        "icon": "shopping-cart",
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
        "icon": "receipt",
        "label": "Ventes",
        "charts": _ALL,
        "bookkeeping": _DOUBLE,   # journal VE, comptes clients 411
        "active": ["sales", "leases", "rent_indices"],
        "items": [
            {"key": "sales_list", "label": "Factures, avoirs et devis", "endpoint": "sales.index", "charts": _ALL},
            {"key": "sales_due", "label": "À émettre", "endpoint": "sales.due", "charts": _ALL},
            {"key": "sales_recurring", "label": "Factures récurrentes", "endpoint": "sales.recurring", "charts": _ALL},
            {"key": "cooperatives", "label": "Coopératives", "icon": "warehouse", "pictogram": "barn", "charts": ["agri"],
             "items": [
                {"key": "sales_self_billed", "label": "Autofactures reçues", "icon": "file-input",
                 "endpoint": "sales.self_billed", "charts": ["agri"]},
                {"key": "sales_coop_statements", "label": "Décomptes de coopérative", "icon": "scroll-text",
                 "endpoint": "sales.coop_statements", "charts": ["agri"]},
            ]},
            {"key": "leases", "label": "Baux et quittances", "icon": "key-round", "endpoint": "leases.index", "charts": _ALL},
            {"key": "rent_indices", "label": "Indices de loyer", "icon": "chart-line", "endpoint": "rent_indices.index",
             "charts": _ALL},
        ],
    },
    # ------------------------------------------------------------------- Associés
    {
        "key": "associates",
        "icon": "users",
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
        "icon": "handshake",
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
        "icon": "store",
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
        "icon": "chart-no-axes-column",
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
        "icon": "file-up",
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
    # ----------------------------------------------------------------- Outils (lot AG12, AGD29)
    {
        "key": "tools",
        "icon": "wrench",
        "label": "Outils",
        "charts": _ALL,
        "active": ["tools"],
        "items": [
            {"key": "calculators", "label": "Calculettes", "endpoint": "tools.index", "charts": _ALL},
        ],
    },
    # ----------------------------------------------------------------- Configuration
    {
        "key": "configuration",
        "icon": "settings",
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
    """Filtre les sous-menus par plan comptable / droits (récursif, lot NV1), puis nettoie les
    séparateurs orphelins (en tête, en fin, ou consécutifs). Un sous-menu vide est retiré ; un
    sous-menu qui n'a plus qu'une entrée est remplacé par cette entrée."""
    kept: list[dict] = []
    for item in items:
        if not _visible(item, chart, is_admin, bookkeeping, features):
            continue
        if "items" in item:
            children = _clean_items(item["items"], chart, is_admin, bookkeeping, features)
            entries = [c for c in children if not c.get("divider")]
            if not entries:
                continue
            item = entries[0] if len(entries) == 1 else {**item, "items": children}
        if item.get("divider"):
            # pas de séparateur en tête ni deux séparateurs de suite
            if not kept or kept[-1].get("divider"):
                continue
        kept.append(item)
    # retire un éventuel séparateur en fin de liste
    while kept and kept[-1].get("divider"):
        kept.pop()
    return kept


def endpoints(entries: list[dict] | None = None):
    """Tous les endpoints déclarés (tous niveaux), pour les tests de cohérence."""
    for entry in MENUS if entries is None else entries:
        if entry.get("endpoint"):
            yield entry["endpoint"]
        if "items" in entry:
            yield from endpoints(entry["items"])


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
