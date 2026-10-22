"""Actions, formulaires et imports envoyés en HTMX (hx-boost) dans la zone de contenu."""
import io
import json
import re
from datetime import date
from pathlib import Path

import pytest

from app.extensions import db
from app.models import BankAccount, Account, Purchase

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


def _purchase(session, number="F-1"):
    p = Purchase(source="manual", invoice_number=number, issue_date=date(2026, 10, 1), total_cents=1000)
    session.add(p)
    session.commit()
    return p


def test_redirect_after_action_becomes_hx_location(client, session):
    p = _purchase(session)

    resp = client.post(f"/purchases/{p.id}/delete", headers=HX_CONTENT)
    assert resp.status_code == 200 and resp.get_data() == b""
    loc = _location(resp)
    assert loc == {"path": "/purchases/", "target": "#page-content", "select": "#page-content",
                   "swap": "outerHTML show:none"}
    assert Purchase.query.count() == 0

    # Le message flash part avec la requête suivante (chargement HX-Location).
    follow = client.get(loc["path"], headers={"HX-Request": "true", "HX-Target": "page-content"})
    toast = json.loads(follow.headers["HX-Trigger"])["toast"]
    assert toast[0]["level"] == "success" and "supprimée" in toast[0]["message"]
    assert "Facture F-1 supprimée" not in follow.get_data(as_text=True)  # pas rendu dans la page


def test_redirect_outside_content_zone_stays_hx_redirect(client, session):
    p = _purchase(session)
    resp = client.post(f"/purchases/{p.id}/delete", headers={"HX-Request": "true"})
    assert resp.headers["HX-Redirect"] == "/purchases/"
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


# --- imports ----------------------------------------------------------------


def test_ofx_import_form_is_boosted_with_progress(client):
    html = client.get("/imports/ofx").get_data(as_text=True)
    form = re.search(r'<form method="post" enctype="multipart/form-data"[^>]*>', html).group(0)
    assert 'hx-boost="true"' in form and 'hx-target="#page-content"' in form
    assert "data-upload-progress" in html


def test_ofx_import_error_returns_page_and_toast(client, session):
    acc = Account(code="512", label="Banque")
    session.add(acc)
    session.flush()
    ba = BankAccount(label="Courant", account_id=acc.id)
    session.add(ba)
    session.commit()
    resp = client.post("/imports/ofx", headers=HX_CONTENT, content_type="multipart/form-data",
                       data={"bank_account_id": ba.id, "ofx_file": (io.BytesIO(b"pas un ofx"), "x.ofx")})
    assert resp.status_code == 200
    assert 'id="page-content"' in resp.get_data(as_text=True)
    toast = json.loads(resp.headers["HX-Trigger"])["toast"]
    assert toast[0]["level"] == "danger" and "OFX" in toast[0]["message"]


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
    assert len(forms) >= 20
    offenders = [str(p) for p, tag in forms if "onsubmit" in tag]
    assert offenders == []


def test_delete_actions_keep_a_confirmation():
    tags = [tag for _p, tag in _boosted_forms() if "delete" in tag]
    assert tags and all("confirm=" in tag for tag in tags)


def test_rendered_confirmation_is_escaped(client, session):
    _purchase(session, number='F "spéciale"')
    html = client.get("/purchases/").get_data(as_text=True)
    assert 'hx-confirm="Supprimer la facture F &#34;spéciale&#34; ?"' in html
