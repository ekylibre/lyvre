"""Socle HTMX : rendu de fragments, notifications HX-Trigger, redirections, CSRF."""
import json
import re

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


# --- Îlots React : assets Vite et macro island (phase D) --------------------


@pytest.fixture()
def manifest(tmp_path, monkeypatch):
    import app.frontend as frontend

    path = tmp_path / "manifest.json"
    monkeypatch.setattr(frontend, "_manifest_path", lambda: str(path))
    monkeypatch.setitem(frontend._manifest_cache, "mtime", None)
    return path


def test_vite_assets_production_reads_manifest(app, manifest):
    from app.frontend import vite_assets

    manifest.write_text(json.dumps({
        "src/main.tsx": {"file": "assets/main-abc.js", "css": ["assets/main-abc.css"],
                         "imports": ["_vendor.js"], "isEntry": True},
        "_vendor.js": {"file": "assets/vendor-xyz.js"},
    }))
    with app.test_request_context():
        html = str(vite_assets())
    assert '<script type="module" src="/static/dist/assets/main-abc.js"></script>' in html
    assert '<link rel="stylesheet" href="/static/dist/assets/main-abc.css">' in html
    assert '<link rel="modulepreload" href="/static/dist/assets/vendor-xyz.js">' in html


def test_vite_assets_reloads_manifest_after_new_build(app, manifest):
    import os
    from app.frontend import vite_assets

    manifest.write_text(json.dumps({"src/main.tsx": {"file": "assets/v1.js"}}))
    with app.test_request_context():
        assert "v1.js" in str(vite_assets())
        manifest.write_text(json.dumps({"src/main.tsx": {"file": "assets/v2.js"}}))
        os.utime(manifest, (1, 1))  # mtime différent
        assert "v2.js" in str(vite_assets())


def test_vite_assets_missing_build_shows_error(app, manifest):
    from app.frontend import vite_assets

    with app.test_request_context():
        html = str(vite_assets())
    assert "alert-danger" in html and "npm --prefix frontend run build" in html


def test_vite_assets_dev_server(app):
    from app.frontend import vite_assets

    app.config["VITE_DEV_SERVER"] = "http://localhost:5173/"
    with app.test_request_context():
        html = str(vite_assets())
    assert 'src="http://localhost:5173/static/dist/@vite/client"' in html
    assert 'src="http://localhost:5173/static/dist/src/main.tsx"' in html
    assert "@react-refresh" in html and "__vite_plugin_react_preamble_installed__" in html


def test_island_macro_escapes_props(app):
    from flask import render_template_string

    with app.test_request_context():
        html = render_template_string(
            '{% from "_island.html" import island %}{{ island("entry-form", props) }}',
            props={"label": 'Dupont "&" fils <b>', "amount": 1250},
        )
    m = re.search(r'data-island="entry-form" data-props="([^"]*)"', html)
    assert m, html
    # Attribut sûr : aucun guillemet ni balise brute, JSON restitué à l'identique.
    from html import unescape
    assert json.loads(unescape(m.group(1))) == {"label": 'Dupont "&" fils <b>', "amount": 1250}
    assert "<b>" not in m.group(1)
