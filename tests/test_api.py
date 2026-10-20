"""Blueprint /api/v1 : format d'erreur JSON, authentification, CSRF."""
import pytest

from app.api import ApiError


@pytest.fixture()
def client(app):
    app.config["LOGIN_DISABLED"] = True
    return app.test_client()


def _error(resp):
    body = resp.get_json()
    assert set(body) == {"error"}, body
    return body["error"]


def test_unknown_api_url_is_json_404(client):
    resp = client.get("/api/v1/nope")
    assert resp.status_code == 404 and resp.is_json
    assert _error(resp)["code"] == "not_found"


def test_wrong_method_is_json_405(client):
    resp = client.delete("/api/v1/session")
    assert resp.status_code == 405
    assert _error(resp)["code"] == "method_not_allowed"


def test_html_404_unchanged(client):
    resp = client.get("/nope")
    assert resp.status_code == 404 and not resp.is_json


def test_unauthenticated_api_call_gets_401_json(app):
    resp = app.test_client().get("/api/v1/session")
    assert resp.status_code == 401
    assert _error(resp)["code"] == "unauthenticated"
    assert "Location" not in resp.headers


def test_html_pages_still_redirect_to_login(app):
    resp = app.test_client().get("/entries/")
    assert resp.status_code == 302 and "/login" in resp.headers["Location"]


def test_session_endpoint(client):
    body = client.get("/api/v1/session").get_json()
    assert body == {"user": {"email": None, "is_admin": False}, "instance": None}


def test_api_error_and_json_body(app, client):
    from flask import jsonify
    from app.api import json_body

    def _t_validate():
        data = json_body()
        raise ApiError("validation_error", "Écriture déséquilibrée.", status=422,
                       fields={"lines[1].account_id": "Compte inconnu."} if data else None)

    app.add_url_rule("/api/v1/_t/validate", "_t_validate", _t_validate, methods=["POST"])
    app.add_url_rule("/api/v1/_t/ok", "_t_ok", lambda: jsonify(ok=True), methods=["POST"])
    from flask import render_template_string
    app.add_url_rule("/_t/token", "_t_token", lambda: render_template_string("{{ csrf_token() }}"))

    resp = client.post("/api/v1/_t/validate", json={"x": 1})
    assert resp.status_code == 422
    assert _error(resp) == {"code": "validation_error", "message": "Écriture déséquilibrée.",
                            "fields": {"lines[1].account_id": "Compte inconnu."}}

    resp = client.post("/api/v1/_t/validate", data="pas du json", content_type="text/plain")
    assert resp.status_code == 400 and _error(resp)["code"] == "bad_request"

    # CSRF : refus JSON sans jeton, accepté avec l'en-tête X-CSRFToken.
    app.config["WTF_CSRF_ENABLED"] = True
    resp = client.post("/api/v1/_t/ok", json={})
    assert resp.status_code == 400 and _error(resp)["code"] == "csrf_error"
    token = client.get("/_t/token").get_data(as_text=True)
    assert client.post("/api/v1/_t/ok", json={}, headers={"X-CSRFToken": token}).status_code == 200
