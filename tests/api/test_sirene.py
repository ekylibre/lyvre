"""Lot G3 : service Sirene (fiches, recherche, proposition, quota, cache, erreurs) et API, sans réseau :
les réponses de l'INSEE sont simulées à partir de tests/fixtures/sirene (données publiques)."""
import json
from pathlib import Path

import pytest
import requests

from app.extensions import db
from app.models import Entity
from app.services import nomenclatures, sirene

FIXTURES = Path(__file__).parents[1] / "fixtures" / "sirene"
KEY = "cle-de-test"


def _fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


UNIT, HEAD, POITIERS = (_fixture("unite_legale_120027016.json"), _fixture("etablissement_12002701600563.json"),
                        _fixture("etablissement_12002701600241.json"))


class FakeResponse:
    def __init__(self, status, body, headers=None):
        self.status_code, self._body, self.headers = status, body, headers or {}
        self.ok = status < 400
        self.text = json.dumps(body)

    def json(self):
        return self._body


@pytest.fixture()
def insee(app, monkeypatch, tmp_path):
    """Fausse API : routes de l'INSEE → réponses ; `calls` garde chaque appel (méthode, chemin, corps)."""
    app.config["SIRENE_API_KEY"] = KEY
    sirene._cache.clear()
    monkeypatch.setattr(sirene, "limiter", sirene.RateLimiter())
    (tmp_path / "categories_juridiques.json").write_text(json.dumps({"codes": {"7120": "Service central d'un ministère"}}))
    (tmp_path / "naf_rev2.json").write_text(json.dumps({"codes": {"8411Z": "Administration publique générale"}}))
    monkeypatch.setattr(nomenclatures, "DATA_DIR", tmp_path)
    nomenclatures._load.cache_clear()
    calls, routes = [], {}

    def request(method, url, params=None, json=None, headers=None, timeout=None):
        assert headers["X-INSEE-Api-Key-Integration"] == KEY and timeout == sirene.TIMEOUT
        path = url.split("/api-sirene/4", 1)[1]
        calls.append((method, path, json))
        answer = routes.get((method, path))
        if answer is None:
            return FakeResponse(404, {"code": "siren.not-exists", "libelle": "inexistant"})
        return answer(json) if callable(answer) else answer

    monkeypatch.setattr(sirene.requests, "request", request)
    routes[("GET", "/etat-courant/unites-legales/120027016")] = FakeResponse(200, UNIT)
    routes[("GET", "/etat-courant/etablissements/12002701600563")] = FakeResponse(200, HEAD)
    routes[("GET", "/etat-courant/etablissements/12002701600241")] = FakeResponse(200, POITIERS)
    yield calls, routes
    nomenclatures._load.cache_clear()


def _error(resp, status):
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()["error"]


def test_not_configured(login_as):
    client = login_as()
    assert client.get("/api/v1/session").get_json()["services"] == {"sirene": False}
    assert _error(client.get("/api/v1/sirene/proposal?siren=120027016"), 503)["code"] == "sirene_unavailable"


def test_vat_number_key():
    assert sirene.vat_number("120027016") == "FR" + f"{(12 + 3 * (120027016 % 97)) % 97:02d}" + "120027016"


def test_structure_proposal_from_siren(login_as, insee):
    calls, _ = insee
    client = login_as()
    assert client.get("/api/v1/session").get_json()["services"] == {"sirene": True}
    body = client.get("/api/v1/sirene/proposal?siren=120 027 016").get_json()
    assert body["proposal"] == {
        "name": "INSTITUT NATIONAL DE LA STATISTIQUE ET DES ETUDES ECONOMIQUES", "siren": "120027016",
        "siret": "12002701600563", "address_line1": "88 avenue Verdier", "address_line2": "IMMEUBLE WHITE",
        "postal_code": "92120", "city": "Montrouge", "country": "France", "legal_form": "Service central d'un ministère",
        "naf_code": "8411Z", "naf_nomenclature": "NAFRev2", "vat_number": sirene.vat_number("120027016"),
        "created_on": "1983-03-01"}  # lot AG1.a ; catégorie 7120 : pas de forme codée (legal_form_code absent)
    assert body["computed"] == ["vat_number"] and body["state"] == "active" and body["warnings"] == []
    assert body["labels"] == {"legal_form": "Service central d'un ministère", "naf": "Administration publique générale"}
    assert body["existing_entity"] is None
    assert KEY not in json.dumps(body)
    # Fiches en cache : la même demande ne rappelle pas l'INSEE.
    count = len(calls)
    client.get("/api/v1/sirene/proposal?siren=120027016")
    assert len(calls) == count == 2


def test_entity_proposal_from_siret_with_existing_entity(login_as, insee):
    client = login_as()
    db.session.add(Entity(name="INSEE", siret="12002701600563"))
    db.session.commit()
    body = client.get("/api/v1/sirene/proposal?siret=12002701600241&for=entity").get_json()
    assert body["proposal"]["siret"] == "12002701600241" and body["proposal"]["city"] == "Poitiers"
    assert body["proposal"]["person_kind"] == "company" and "legal_form" not in body["proposal"]
    assert body["existing_entity"]["name"] == "INSEE"


def test_closed_establishment_falls_back_to_head_office(insee):
    _calls, routes = insee
    routes[("GET", "/etat-courant/etablissements/12002701600241")] = FakeResponse(200, {**POITIERS, "etatEtablissement": "3"})
    result = sirene.proposal(siret="12002701600241", for_entity=True)
    assert result.values["siret"] == "12002701600563" and result.state == "active"
    assert result.warnings == ["Établissement fermé : le siège est proposé."]


def test_ceased_unit_and_partial_diffusion(insee):
    _calls, routes = insee
    routes[("GET", "/etat-courant/unites-legales/120027016")] = FakeResponse(
        200, {**UNIT, "etatUniteLegale": "4", "statutDiffusionUniteLegale": "P"})
    result = sirene.proposal(siren="120027016")
    assert result.state == "ceased" and "address_line1" not in result.values
    assert "Diffusion partielle" in result.warnings[0]


def test_individual_entrepreneur_name():
    assert sirene.unit_name({"siren": "1", "prenomUsuelUniteLegale": "Jeanne", "nomUniteLegale": "MARTIN"}) == \
        "Jeanne MARTIN"


def test_search_by_name_two_calls(login_as, insee):
    calls, routes = insee
    routes[("POST", "/etat-courant/unites-legales/multicritere")] = FakeResponse(200, {"items": [{"item": UNIT}]})
    routes[("POST", "/etat-courant/etablissements/multicritere")] = lambda body: FakeResponse(
        200, {"items": [{"item": POITIERS if body.get("codePostalEtablissement") else HEAD}]})
    client = login_as()
    items = client.get("/api/v1/sirene/search?q=institut statistique").get_json()["items"]
    assert items == [{"siren": "120027016", "siret": "12002701600563",
                      "name": "INSTITUT NATIONAL DE LA STATISTIQUE ET DES ETUDES ECONOMIQUES",
                      "legal_form": "Service central d'un ministère", "postal_code": "92120", "city": "Montrouge",
                      "head_office": True, "active": True}]
    assert [c[1] for c in calls] == ["/etat-courant/unites-legales/multicritere", "/etat-courant/etablissements/multicritere"]
    assert calls[0][2]["denominationUniteLegale"] == ["institut statistique"] and calls[1][2]["etablissementSiege"] is True

    items = client.get("/api/v1/sirene/search?q=institut statistique&postal_code=86000").get_json()["items"]
    assert items[0]["city"] == "Poitiers" and items[0]["head_office"] is False
    assert calls[-1][2]["codePostalEtablissement"] == ["86000"] and calls[-1][2]["siren"] == ["120027016"]


def test_search_by_number(insee):
    (candidate,) = sirene.search("120 027 016 00241")
    assert candidate["siret"] == "12002701600241" and candidate["city"] == "Poitiers"


def test_errors(login_as, insee):
    _calls, routes = insee
    client = login_as()
    assert _error(client.get("/api/v1/sirene/proposal?siren=120027017"), 422)["code"] == "validation_error"  # clé
    assert _error(client.get("/api/v1/sirene/proposal?siren=732829320"), 404)["code"] == "not_found"
    routes[("GET", "/etat-courant/unites-legales/552100554")] = FakeResponse(500, {"message": "boom"})
    assert _error(client.get("/api/v1/sirene/proposal?siren=552100554"), 503)["message"] == \
        "Sirene ne répond pas : réessayez plus tard."
    assert _error(client.get("/api/v1/sirene/search?q=a"), 422)["code"] == "validation_error"


def test_network_failure(insee, monkeypatch):
    def down(*_args, **_kwargs):
        raise requests.ConnectionError("down")
    monkeypatch.setattr(sirene.requests, "request", down)
    with pytest.raises(sirene.SireneError) as exc:
        sirene.legal_unit("552100554")
    assert exc.value.code == "unavailable"


def test_insee_429_gives_busy(login_as, insee):
    _calls, routes = insee
    routes[("GET", "/etat-courant/unites-legales/552100554")] = FakeResponse(429, {}, {"x-rate-limit-reset": "0"})
    error = _error(login_as().get("/api/v1/sirene/proposal?siren=552100554"), 429)
    assert error["code"] == "sirene_busy" and error["retry_after"] >= 1


def test_rate_limiter_windows():
    now = [0.0]
    limiter = sirene.RateLimiter(clock=lambda: now[0])
    for _ in range(30):
        limiter.acquire()
    with pytest.raises(sirene.SireneError) as exc:
        limiter.acquire()
    assert exc.value.code == "busy" and exc.value.retry_after == 60
    now[0] = 60.0
    limiter.acquire()  # la minute est passée
    hourly = sirene.RateLimiter(limits=((30, 60), (2000, 3600)), clock=lambda: now[0])
    hourly.calls.extend(float(t) for t in range(2000))
    now[0] = 3000.0
    with pytest.raises(sirene.SireneError) as exc:
        hourly.acquire()
    assert exc.value.retry_after == 600


def test_busy_before_calling_insee(login_as, insee, monkeypatch):
    calls, _ = insee
    limiter = sirene.RateLimiter(limits=((1, 60),))
    monkeypatch.setattr(sirene, "limiter", limiter)
    client = login_as()
    client.get("/api/v1/sirene/proposal?siren=120027016")  # 1er appel : unité légale ; le siège dépasse le quota
    assert len(calls) == 1


def test_accountant_can_read(login_as, insee):
    assert login_as(role="accountant").get("/api/v1/sirene/proposal?siren=120027016").status_code == 200
