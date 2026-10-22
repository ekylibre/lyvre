"""Ancienne adresse de l'écran des intégrations (« Connexions externes ») : redirection vers la
page de la SPA. Écrans : SPA ; API : app/api/integrations.py."""
from flask import Blueprint, redirect, url_for

legacy_bp = Blueprint(
    "external_connections", __name__, url_prefix="/configuration/external-connections"
)


@legacy_bp.route("/")
def index_redirect():
    return redirect(url_for("integrations.index"), code=301)
