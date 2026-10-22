"""Actions, formulaires et imports envoyés en HTMX (hx-boost) dans la zone de contenu."""
import json
import re
from pathlib import Path

import pytest


TEMPLATES = Path(__file__).resolve().parent.parent / "app" / "templates"
# Requête émise par un formulaire hx_submit / un lien hx_nav (cible = zone de contenu).
HX_CONTENT = {"HX-Request": "true", "HX-Boosted": "true", "HX-Target": "page-content"}


@pytest.fixture()
def client(app):
    app.config["LOGIN_DISABLED"] = True
    return app.test_client()


def _location(resp):
    return json.loads(resp.headers["HX-Location"])


# --- redirections ---------------------------------------------------------


def test_redirect_after_action_becomes_hx_location(login_as):
    client = login_as(is_admin=True)
    # Désactivation d'une intégration : message puis retour à sa fiche.
    resp = client.post("/configuration/integrations/odoo/enabled", data={"enabled": ""}, headers=HX_CONTENT)
    assert resp.status_code == 200 and resp.get_data() == b""
    loc = _location(resp)
    assert loc == {"path": "/configuration/integrations/odoo", "target": "#page-content",
                   "select": "#page-content", "swap": "outerHTML show:none"}

    # Le message flash part avec la requête suivante (chargement HX-Location).
    follow = client.get(loc["path"], headers={"HX-Request": "true", "HX-Target": "page-content"})
    toast = json.loads(follow.headers["HX-Trigger"])["toast"]
    assert toast[0]["level"] == "success" and "Odoo" in toast[0]["message"]


def test_redirect_outside_content_zone_stays_hx_redirect(login_as):
    resp = login_as(is_admin=True).post("/configuration/integrations/odoo/enabled", data={"enabled": ""},
                                        headers={"HX-Request": "true"})
    assert resp.headers["HX-Redirect"] == "/configuration/integrations/odoo"
    assert "HX-Location" not in resp.headers


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


# --- garde-fous sur les templates -----------------------------------------


def _boosted_forms():
    for path in TEMPLATES.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"<form\b[^>]*>", text, flags=re.S):
            if "hx_submit(" in m.group(0):
                yield path.relative_to(TEMPLATES), m.group(0)


def test_boosted_forms_do_not_rely_on_onsubmit_confirm():
    """HTMX ignore ``onsubmit="return confirm()"`` : utiliser hx_submit(confirm=...)."""
    forms = list(_boosted_forms())
    assert forms
    offenders = [str(p) for p, tag in forms if "onsubmit" in tag]
    assert offenders == []
