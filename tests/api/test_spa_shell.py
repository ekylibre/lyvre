"""Coquille de la SPA : pages de app/spa_routes.json servies aux mêmes URL."""
from flask import url_for

from app import spa


def test_routes_file_is_valid():
    routes = spa.load_routes()
    endpoints = [r["endpoint"] for r in routes]
    assert len(endpoints) == len(set(endpoints))
    assert all(r["rule"].startswith("/") for r in routes)


def test_spa_endpoints_keep_their_url_for_names(app):
    with app.test_request_context():
        assert url_for("auth.login") == "/login"
        assert url_for("auth.select_instance") == "/select-instance"
    for route in spa.load_routes():
        assert app.view_functions[route["endpoint"]].__name__ == "spa_shell"
        rules = [r for r in app.url_map.iter_rules() if r.rule == route["rule"] and "GET" in r.methods]
        assert [r.endpoint for r in rules] == [route["endpoint"]]  # aucune autre page GET


def test_public_page_serves_shell(app):
    resp = app.test_client().get("/login")
    page = resp.get_data(as_text=True)
    assert resp.status_code == 200 and '<div id="root"></div>' in page
    assert 'name="csrf-token"' in page and "bootstrap" not in page


def test_private_page_requires_login(app):
    resp = app.test_client().get("/select-instance")
    assert resp.status_code == 302 and resp.headers["Location"].startswith("/login")


def test_private_page_for_logged_user(login_as):
    client = login_as()
    assert '<div id="root"></div>' in client.get("/select-instance").get_data(as_text=True)


def test_logout_link_still_works(login_as):
    client = login_as()
    resp = client.get("/logout")
    assert resp.status_code == 302 and resp.headers["Location"] == "/login"
