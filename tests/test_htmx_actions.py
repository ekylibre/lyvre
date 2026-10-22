"""Redirections HTMX vers la connexion et configuration HTMX de base.html (retirées en phase I)."""
import json
import re

# Requête émise par un formulaire hx_submit / un lien hx_nav (cible = zone de contenu).
HX_CONTENT = {"HX-Request": "true", "HX-Boosted": "true", "HX-Target": "page-content"}


# --- redirections ---------------------------------------------------------


def test_redirect_to_login_is_full_page_even_from_content_zone(app):
    client = app.test_client()  # authentification active
    resp = client.get("/entries/", headers=HX_CONTENT)
    assert "/login" in resp.headers["HX-Redirect"]
    assert "HX-Location" not in resp.headers


def test_htmx_config_swaps_422(app):
    from flask import render_template

    with app.test_request_context():
        html = render_template("base.html", nav_menus=[])
    meta = re.search(r"<meta name=\"htmx-config\" content='([^']+)'>", html).group(1)
    handling = json.loads(meta)["responseHandling"]
    codes = [h["code"] for h in handling]
    assert codes.index("422") < codes.index("[45]..")
    assert next(h for h in handling if h["code"] == "422")["swap"] is True
