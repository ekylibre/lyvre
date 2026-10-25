"""Lot B1 : intégration Brevo (associations seulement), client (débit, 429, IP non autorisée, clé
refusée), test de l'intégration, listes et attributs. Sans réseau : l'API Brevo est simulée."""
import json

import pytest
import requests

from app.extensions import db
from app.models import Instance
from app.services import brevo_attributes, brevo_client, external_config, integrations

KEY = "xkeysib-cle-de-test"
IP_REFUSED = {"message": "We have detected you are using an unrecognised IP address 2a01:db8::1. If you performed "
                         "this action make sure to add the new IP address in this link: https://app.brevo.com/security"}


class FakeResponse:
    def __init__(self, status, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body, headers or {}
        self.ok = status < 400
        self.content = b"" if body is None else json.dumps(body).encode()

    def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body


@pytest.fixture()
def brevo(app, monkeypatch):
    """Fausse API : `routes[(méthode, chemin)]` → réponse ou fonction(body) ; `calls` garde les appels."""
    monkeypatch.setattr(brevo_client, "MIN_INTERVAL", 0)
    monkeypatch.setattr(brevo_client.time, "sleep", lambda _s: None)
    calls = []
    routes = {
        ("GET", "/account"): FakeResponse(200, {"companyName": "Asso test", "plan": [{"type": "free"}]}),
        ("GET", "/contacts/lists"): FakeResponse(200, {"lists": [{"id": 12, "name": "Adhérents (Lyvre)", "uniqueSubscribers": 3}]}),
        ("GET", "/contacts/attributes"): FakeResponse(200, {"attributes": [
            {"name": "PRENOM", "category": "normal", "type": "text"}, {"name": "NOM", "category": "normal", "type": "text"},
            {"name": "DATE_ADH", "category": "normal", "type": "date"}, {"name": "EMAIL", "category": "transactional"}]}),
    }

    def request(method, url, params=None, json=None, headers=None, timeout=None):
        assert headers["api-key"] == KEY
        path = url.split("/v3", 1)[1]
        calls.append((method, path, json))
        answer = routes.get((method, path))
        if answer is None:
            return FakeResponse(404, {"message": "not found"})
        return answer(json) if callable(answer) else answer

    monkeypatch.setattr(brevo_client.requests, "request", request)
    return calls, routes


@pytest.fixture()
def admin(login_as):
    client = login_as(role="admin")
    external_config.set_many("brevo", {"api_key": KEY, "list_id": "12"})
    external_config.set_enabled("brevo", True)
    return client


def _error(resp, status):
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()["error"]


def test_brevo_is_for_associations_only(instance):
    assert external_config.applies("brevo", "asso") and not external_config.applies("brevo", "sci")
    assert ("brevo", "api_key") in external_config.SECRET_KEYS


def test_check_reports_account_list_and_missing_attributes(admin, brevo):
    result = integrations.run_check("brevo")
    assert result.ok, result.message
    assert "Compte Brevo « Asso test » (offre free) accessible." in result.message
    assert "Liste « Adhérents (Lyvre) » (3 contacts)." in result.message
    assert "Attributs à créer : LYVRE_STATUT, LYVRE_ECHEANCE, LYVRE_BENEVOLE." in result.message
    assert KEY not in result.message


def test_check_unknown_list(admin, brevo):
    external_config.set_many("brevo", {"api_key": KEY, "list_id": "99"})
    result = integrations.run_check("brevo")
    assert not result.ok and "Liste n° 99 introuvable" in result.message


@pytest.mark.parametrize("status, body, code, text", [
    (401, IP_REFUSED, "ip_not_allowed", "L'adresse IP du serveur (2a01:db8::1) n'est pas autorisée dans Brevo"),
    (401, {"message": "Key not found"}, "invalid_key", "Clé API refusée par Brevo"),
    (500, {"message": "boom"}, "unavailable", "HTTP 500"),
])
def test_errors_are_explained(admin, brevo, status, body, code, text):
    _calls, routes = brevo
    routes[("GET", "/account")] = FakeResponse(status, body)
    with pytest.raises(brevo_client.BrevoError) as exc:
        brevo_client.Client.from_config().account()
    assert exc.value.code == code and text in exc.value.message
    assert text in integrations.run_check("brevo").message


def test_429_waits_then_retries(admin, brevo, monkeypatch):
    _calls, routes = brevo
    answers = iter([FakeResponse(429, {}, {"x-sib-ratelimit-reset": "2"}), FakeResponse(200, {"companyName": "Asso"})])
    routes[("GET", "/account")] = lambda _body: next(answers)
    slept = []
    monkeypatch.setattr(brevo_client.time, "sleep", slept.append)
    assert brevo_client.Client.from_config().account()["companyName"] == "Asso"
    assert slept == [2.0]


def test_network_failure(admin, monkeypatch):
    def down(*_a, **_k):
        raise requests.ConnectionError("down")
    monkeypatch.setattr(brevo_client.requests, "request", down)
    with pytest.raises(brevo_client.BrevoError) as exc:
        brevo_client.Client.from_config().lists()
    assert exc.value.code == "unavailable"


def test_lists_and_attributes_routes(admin, brevo):
    calls, _routes = brevo
    body = admin.get("/api/v1/brevo/lists").get_json()
    assert body == {"items": [{"value": "12", "label": "Adhérents (Lyvre)", "contacts": 3}], "selected": "12"}
    items = {a["name"]: a for a in admin.get("/api/v1/brevo/attributes").get_json()["items"]}
    assert items["PRENOM"]["present"] and items["PRENOM"]["shared"]
    assert not items["LYVRE_STATUT"]["present"] and not items["LYVRE_STATUT"]["shared"]

    created = []
    def create(body):
        created.append(body)
        return FakeResponse(201, None)
    for name in ("LYVRE_STATUT", "LYVRE_ECHEANCE", "LYVRE_BENEVOLE"):
        brevo[1][("POST", f"/contacts/attributes/normal/{name}")] = create
    resp = admin.post("/api/v1/brevo/attributes")
    assert resp.status_code == 200, resp.get_json()
    assert created == [{"type": "text"}, {"type": "date"}, {"type": "boolean"}]
    assert "LYVRE_STATUT, LYVRE_ECHEANCE, LYVRE_BENEVOLE" in resp.get_json()["notices"][0]["message"]
    assert all(c[0] == "GET" or c[1].startswith("/contacts/attributes/normal/") for c in calls)  # aucun contact touché


def test_routes_without_key_or_for_a_sci(login_as, brevo):
    client = login_as(role="admin")
    assert _error(client.get("/api/v1/brevo/lists"), 409)["code"] == "brevo_not_configured"
    Instance.query.filter_by(slug="test").one().chart = "sci"
    db.session.commit()
    assert _error(client.get("/api/v1/brevo/lists"), 403)["code"] == "association_only"


def test_attribute_creation_reserved_to_instance_admin(login_as, brevo):
    client = login_as()  # trésorier
    external_config.set_many("brevo", {"api_key": KEY, "list_id": "12"})
    assert client.post("/api/v1/brevo/attributes").status_code == 403


def test_missing_attributes_helper():
    assert brevo_attributes.missing([{"name": n, "category": "normal"} for n in brevo_attributes.EXPECTED]) == []
    assert brevo_attributes.missing([{"name": "PRENOM", "category": "transactional"}])[0] == "PRENOM"
