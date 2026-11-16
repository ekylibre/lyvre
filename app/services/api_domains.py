"""Domaines métier d'une clé d'API (lot AK1, claudedocs/design_api_mcp_aiffel.md § 4).

Chaque module de `app/api` relève d'un domaine (lecture par GET) ou de `None` : jamais ouvert à une clé.
Le classement est **exhaustif** (test `test_api_keys.py::test_every_api_module_is_classified`) : une route
nouvelle n'est pas ouverte par oubli. `ENDPOINT_DOMAINS` l'emporte sur le module (modules mixtes).
"""
from __future__ import annotations

ALL_CHARTS = ("asso", "sci", "societe", "agri")

# clé → (libellé, description, plans comptables, écriture possible en v1)
DOMAINS: dict[str, tuple[str, str, tuple[str, ...], bool]] = {
    "accounting": ("Comptabilité", "Écritures, comptes, balance, grand livre, éditions, analytique", ALL_CHARTS, True),
    "bank": ("Banque", "Comptes bancaires, transactions, relevés, rapprochement, trésorerie", ALL_CHARTS, False),
    "purchases": ("Achats", "Factures d'achat, règlements, relevés de coopérative", ALL_CHARTS, True),
    "sales": ("Ventes", "Devis, factures, avoirs, encaissements, reçus", ALL_CHARTS, False),
    "parties": ("Tiers", "Fournisseurs, clients, adhérents, associés, baux", ALL_CHARTS, True),
    "tax": ("TVA et fiscal", "Déclarations de TVA, résultat fiscal, MSA, paramètres réglementaires", ALL_CHARTS, False),
    "assets": ("Immobilisations et stocks", "Immobilisations, amortissements, stocks", ALL_CHARTS, False),
    "agronomy": ("Agronomie", "Aides, activités et campagnes", ("agri",), False),
    "agenda": ("Échéancier", "Échéances, fiches, listes de contrôle", ALL_CHARTS, False),
    "documents": ("Documents", "Consultation des pièces", ALL_CHARTS, False),
}

MODULE_DOMAINS: dict[str, str | None] = {
    "access": None, "activity_report": "accounting", "agenda": "agenda", "aids": "agronomy", "analytic": "accounting",
    "assets": "assets", "assistant": None, "associate_expenses": "purchases", "associates": "parties",
    "bank_accounts": "bank", "bank_statements": "bank", "brevo": None, "budgets": "accounting",
    "calculators": None, "cash": "bank", "cash_forecast": "bank", "chart": "accounting", "checklists": "agenda",
    "coop_statements": "purchases", "data_import": None, "documents": "documents", "ekylibre": None,
    "entities": "parties", "entries": "accounting", "ereporting": "sales", "fiscal_years": "accounting",
    "impact": "accounting", "imports": None, "instances": None, "integrations": None, "journals": "accounting",
    "leases": "parties", "lettering": "accounting", "lookups": None, "members": "parties", "msa": "tax",
    "notifications": None, "odoo": None, "organization": None, "payouts": "sales", "products": "accounting",
    "projects": "accounting", "purchases": "purchases", "receipts": "sales", "reconciliation": "bank",
    "regulatory": "tax", "reports": "accounting", "rfa": "purchases", "rules": "bank", "sales": "sales",
    "search": None, "session": None, "share_movements": "parties", "simple_categories": "accounting",
    "simple_operations": "accounting", "simple_reports": "accounting", "sirene": "parties", "stock": "assets",
    "subscriptions": "sales", "task_types": "accounting", "tax_profiles": "tax", "tax_result": "tax",
    "users": None, "vat_books": "tax", "vat_returns": "tax", "work_times": "accounting",
    "api_keys": None,
    "agent": None,        # outils d'agent : clé seulement, domaine contrôlé par outil (app/api_auth.py)
}

# Modules mixtes : domaine par endpoint.
ENDPOINT_DOMAINS: dict[str, str | None] = {
    "api.accounts": "accounting",
    "api.entities": "parties",
}


def available(chart: str | None) -> list[str]:
    """Domaines proposés pour une structure de ce plan comptable."""
    return [key for key, (_l, _d, charts, _w) in DOMAINS.items() if chart in charts]


def writable(key: str) -> bool:
    return key in DOMAINS and DOMAINS[key][3]


def options(chart: str | None) -> list[dict]:
    return [{"key": key, "label": DOMAINS[key][0], "description": DOMAINS[key][1], "writable": DOMAINS[key][3]}
            for key in available(chart)]


def label(key: str) -> str:
    return DOMAINS.get(key, (key,))[0]


def domain_of(endpoint: str | None, view_module: str | None) -> str | None:
    """Domaine d'un endpoint de l'API, ou None (fermé aux clés)."""
    if endpoint in ENDPOINT_DOMAINS:
        return ENDPOINT_DOMAINS[endpoint]
    if not view_module or not view_module.startswith("app.api."):
        return None
    return MODULE_DOMAINS.get(view_module.rsplit(".", 1)[1])
