"""Socle HTMX : rendu de fragments, notifications HX-Trigger, redirections, CSRF."""
import json

import pytest
from flask import flash, redirect, render_template_string

from app.frontend import render_page

HX = {"HX-Request": "true"}


@pytest.fixture()
def client(app):
    """Routes de test sans authentification (le hook tenant ne fait rien
    pour un utilisateur anonyme)."""
    @app.route("/_t/page")
    def _t_page():
        return render_page("_t_full.html", "_t_part.html")

    @app.route("/_t/flash")
    def _t_flash():
        flash("Écriture créée.", "success")
        flash("Attention", "warning")
        return "fragment"

    @app.route("/_t/flash-with-trigger")
    def _t_flash_with_trigger():
        flash("OK", "success")
        return "fragment", 200, {"HX-Trigger": "refreshList"}

    @app.route("/_t/redirect")
    def _t_redirect():
        flash("Après redirection", "info")
        return redirect("/_t/target")

    @app.route("/_t/post", methods=["POST"])
    def _t_post():
        return "ok"

    return app.test_client()


@pytest.fixture(autouse=True)
def _templates(app):
    from jinja2 import ChoiceLoader, DictLoader

    env = app.jinja_env
    env.loader = ChoiceLoader([
        DictLoader({
            "_t_part.html": "<table id='part'></table>",
            "_t_full.html": "<html><body>{% include '_t_part.html' %}</body></html>",
        }),
        env.loader,
    ])


def test_render_page_full_without_htmx(client):
    body = client.get("/_t/page").get_data(as_text=True)
    assert body.startswith("<html>") and "id='part'" in body


def test_render_page_fragment_with_htmx(client):
    body = client.get("/_t/page", headers=HX).get_data(as_text=True)
    assert body == "<table id='part'></table>"


def test_render_page_boosted_request_gets_full_page(client):
    body = client.get("/_t/page", headers={**HX, "HX-Boosted": "true"}).get_data(as_text=True)
    assert body.startswith("<html>")


def test_flash_messages_sent_as_toast_trigger(client):
    resp = client.get("/_t/flash", headers=HX)
    trigger = json.loads(resp.headers["HX-Trigger"])
    assert trigger["toast"] == [
        {"level": "success", "message": "Écriture créée."},
        {"level": "warning", "message": "Attention"},
    ]
    # En-tête ASCII uniquement (valeurs d'en-tête HTTP latin-1).
    resp.headers["HX-Trigger"].encode("ascii")


def test_flash_messages_consumed_by_htmx_response(client):
    client.get("/_t/flash", headers=HX)
    with client.session_transaction() as sess:
        assert not sess.get("_flashes")


def test_existing_trigger_header_is_kept(client):
    trigger = json.loads(client.get("/_t/flash-with-trigger", headers=HX).headers["HX-Trigger"])
    assert "refreshList" in trigger
    assert trigger["toast"][0]["message"] == "OK"


def test_no_trigger_without_htmx(client):
    resp = client.get("/_t/flash")
    assert "HX-Trigger" not in resp.headers
    with client.session_transaction() as sess:
        assert sess.get("_flashes")  # restent pour la prochaine page complète


def test_redirect_becomes_hx_redirect(client):
    resp = client.get("/_t/redirect", headers=HX)
    assert resp.status_code == 200
    assert resp.headers["HX-Redirect"].endswith("/_t/target")
    assert "Location" not in resp.headers
    assert resp.get_data() == b""
    with client.session_transaction() as sess:
        assert sess.get("_flashes")  # affichés sur la page de destination


def test_redirect_unchanged_without_htmx(client):
    resp = client.get("/_t/redirect")
    assert resp.status_code == 302


def test_unauthenticated_htmx_request_redirects_to_login(client):
    resp = client.get("/entries/", headers=HX)
    assert resp.status_code == 200
    assert "/login" in resp.headers["HX-Redirect"]


def test_htmx_post_without_csrf_token_is_rejected(app, client):
    app.config["WTF_CSRF_ENABLED"] = True
    assert client.post("/_t/post", headers=HX).status_code == 400


def test_htmx_post_with_csrf_header_is_accepted(app, client):
    app.config["WTF_CSRF_ENABLED"] = True
    # Récupère un jeton lié à la session du client via une page rendant csrf_token().
    app.add_url_rule("/_t/token", "_t_token", lambda: render_template_string("{{ csrf_token() }}"))
    token = client.get("/_t/token").get_data(as_text=True)
    assert client.post("/_t/post", headers={**HX, "X-CSRFToken": token}).status_code == 200


def test_base_layout_has_csrf_meta_toasts_and_progress(app):
    from flask import render_template

    with app.test_request_context():
        flash("Bonjour", "success")
        html = render_template("base.html", nav_menus=[])
    assert '<meta name="csrf-token" content="' in html
    assert 'id="toast-zone"' in html and 'id="toast-template"' in html
    assert "text-bg-success" in html and "Bonjour" in html
    assert 'id="htmx-progress"' in html
    assert 'class="alert alert-' not in html  # les flashes passent par les toasts
