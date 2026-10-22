"""Coquille de la SPA : assets Vite (build, serveur de développement) et jeton CSRF en en-tête."""
import json

import pytest
from flask import render_template_string


@pytest.fixture()
def client(app):
    @app.route("/_t/post", methods=["POST"])
    def _t_post():
        return "ok"

    return app.test_client()


def test_post_without_csrf_token_is_rejected(app, client):
    app.config["WTF_CSRF_ENABLED"] = True
    assert client.post("/_t/post").status_code == 400


def test_post_with_csrf_header_is_accepted(app, client):
    app.config["WTF_CSRF_ENABLED"] = True
    # Jeton lié à la session du client (la SPA le reçoit de la coquille ou de /api/v1/session).
    app.add_url_rule("/_t/token", "_t_token", lambda: render_template_string("{{ csrf_token() }}"))
    token = client.get("/_t/token").get_data(as_text=True)
    assert client.post("/_t/post", headers={"X-CSRFToken": token}).status_code == 200


def test_unauthenticated_page_redirects_to_login(client):
    resp = client.get("/entries/")
    assert resp.status_code == 302 and "/login" in resp.headers["Location"]


def test_no_bootstrap_or_htmx_left():
    """CP final : plus de Bootstrap ni d'HTMX dans l'application servie."""
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "app"
    files = [p for p in root.rglob("*") if p.suffix in {".py", ".html", ".css", ".js"} and "dist" not in p.parts]
    offenders = [str(p.relative_to(root)) for p in files
                 if any(word in p.read_text(encoding="utf-8", errors="ignore").lower()
                        for word in ("bootstrap", "htmx", "hx-"))]
    assert offenders == []


# --- Assets Vite de la coquille SPA ---------------------------------------


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
    assert 'role="alert"' in html and "npm --prefix frontend run build" in html


def test_vite_assets_dev_server(app):
    from app.frontend import vite_assets

    app.config["VITE_DEV_SERVER"] = "http://localhost:5173/"
    with app.test_request_context():
        html = str(vite_assets())
    assert 'src="http://localhost:5173/static/dist/@vite/client"' in html
    assert 'src="http://localhost:5173/static/dist/src/main.tsx"' in html
    assert "@react-refresh" in html and "__vite_plugin_react_preamble_installed__" in html


