"""Fonctions réservées aux associations : reçus fiscaux, adhérents, bénévolat, comptabilité
simplifiée, indicateurs, fonds dédiés, Brevo. Le menu les masque déjà pour une autre structure (SCI) ;
cette garde refuse aussi une adresse saisie à la main : 403 `association_only` pour l'API,
404 pour les pages. Les données déjà en base ne sont ni modifiées ni supprimées.
"""
from flask import abort, current_app, request

# Modules de l'API (app/api/<module>.py) dont toutes les routes sont réservées.
ASSOCIATION_ONLY_MODULES = {"receipts", "members", "work_times", "task_types", "simple_operations",
                            "simple_categories", "simple_reports", "activity_report", "impact", "brevo"}
# Comptabilité simplifiée : ouverte aussi aux exploitations agricoles (micro-BA, lot AG1.b).
SIMPLE_MODULES = {"simple_operations", "simple_categories", "simple_reports"}
SIMPLE_PAGES = ("simple_categories.", "simple_operations.", "simple_reports.")
SIMPLE_CHARTS = {"asso", "agri"}
# Routes isolées dans un module commun.
ASSOCIATION_ONLY_ENDPOINTS = {"api.helloasso_sync", "api.tiers_update_odoo_note",
                              "exports.receipts_signature", "exports.receipt_pdf", "exports.receipts_summary_xlsx",
                              "entities.members_export", "entities.members_csv"}
ASSOCIATION_ONLY_PREFIXES = ("api.fiscal_years_dedicated_fund",)
# Pages (SPA et vues HTML) : préfixe de l'endpoint.
ASSOCIATION_ONLY_PAGES = ("receipts.", "simple_categories.", "simple_operations.", "simple_reports.",
                          "work_times.", "impact.", "activity_report.", "entities.members")


def is_simple_bookkeeping(endpoint: str | None) -> bool:
    """Route de la comptabilité simplifiée (recettes et dépenses, catégories, états)."""
    if not endpoint:
        return False
    if endpoint.startswith("api."):
        view = current_app.view_functions.get(endpoint)
        return view is not None and view.__module__.rsplit(".", 1)[-1] in SIMPLE_MODULES
    return endpoint.startswith(SIMPLE_PAGES)


def is_association_only(endpoint: str | None) -> bool:
    if not endpoint:
        return False
    if endpoint in ASSOCIATION_ONLY_ENDPOINTS or endpoint.startswith(ASSOCIATION_ONLY_PREFIXES):
        return True
    if endpoint.startswith("api."):
        view = current_app.view_functions.get(endpoint)
        return view is not None and view.__module__.rsplit(".", 1)[-1] in ASSOCIATION_ONLY_MODULES
    return endpoint.startswith(ASSOCIATION_ONLY_PAGES)


def register_association_guard(app):
    """À enregistrer après la sélection de l'instance (app.tenant), qui la précède donc."""
    from app.api import error_response
    from app.tenant import current_chart, current_instance, is_association

    @app.before_request
    def _association_only():
        if current_instance() is None or is_association() or not is_association_only(request.endpoint):
            return None
        if current_chart() in SIMPLE_CHARTS and is_simple_bookkeeping(request.endpoint):
            return None
        if request.endpoint.startswith("api."):
            return error_response("association_only", "Fonction réservée aux associations.", 403)
        abort(404)
