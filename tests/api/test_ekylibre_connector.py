"""Lot AG11.a : connecteur Ekylibre (adaptateur, URL sûre, jeton sans mot de passe conservé, révocation,
instantané). Faux serveur : `requests.request` et la résolution DNS sont remplacés ; aucun appel réel."""
import json
from datetime import date, datetime
from decimal import Decimal

import pytest
import requests

from app.extensions import db
from app.models import EkylibreSnapshot, ExternalConnection
from app.services import ekylibre_client, ekylibre_sync, external_config, integrations
from app.services.ekylibre_client import EkylibreError

from test_agri_fixtures import _agri_instance

URL = "https://demo.ekylibre.test"
PLANTS = [
    {"id": 11, "name": "Blé parcelle Nord", "activity_id": 3, "activity_name": "Blé tendre", "net_surface_area":
     {"value": "25/2", "unit": "hectare"}, "production_started_on": "2025-10-01", "production_stopped_on": "2026-08-31",
     "dead_at": None},
    {"id": 12, "name": "Prairie", "activity_id": 5, "activity_name": "Prairie", "net_surface_area": "3500.0 square_meter",
     "production_started_on": "2026-01-01", "production_stopped_on": None},
]
INTERVENTIONS = [
    {"id": 101, "nature": "record", "procedure_name": "fertilizing", "name": "Épandage", "state": "done",
     "started_at": "2026-03-02T08:00:00.000+01:00", "stopped_at": "2026-03-02T11:00:00.000+01:00",
     "working_duration": 10800, "costing": {"total": 410.5, "inputs": 300.0, "doers": 60.5, "tools": 50.0, "receptions": 0.0},
     "parameters": [{"role": "target", "product_id": 11}, {"role": "tool", "product_id": 40},
                    {"role": "input", "product_id": 70}, {"role": "doer", "product_id": 80}]},
]
MATTERS = [{"id": 70, "name": "Ammonitrate", "variant_id": 9, "variety": "fertilizer", "population": 1.5, "unit_name": "t"}]


def _response(status=200, body=None, raw=None):
    r = requests.Response()
    r.status_code = status
    r._content = raw if raw is not None else (json.dumps(body).encode() if body is not None else b"")
    r._content_consumed = True
    return r


class FakeServer:
    def __init__(self):
        self.calls = []
        self.routes = {("POST", "/api/v2/tokens"): _response(body={"token": "tok-secret"}),
                       ("GET", "/api/v2/profile"): _response(body={"first_name": "Camille", "last_name": "Essai"}),
                       ("GET", "/api/v2/products/plants"): _response(body=PLANTS),
                       ("GET", "/api/v2/products/matters"): _response(body=MATTERS),
                       ("GET", "/api/v2/interventions"): _response(body=INTERVENTIONS),
                       ("DELETE", "/api/v2/tokens/tok-secret"): _response(body={"token": "tok-secret"})}

    def __call__(self, method, url, **kwargs):
        path = url.removeprefix(URL)
        self.calls.append((method, path, kwargs))
        if (method, path) in self.routes:  # une réponse en erreur est « fausse » : pas de `or`
            return self.routes[(method, path)]
        return _response(404, {"errors": ["not found"]})


@pytest.fixture()
def server(monkeypatch):
    fake = FakeServer()
    monkeypatch.setattr(ekylibre_client.requests, "request", fake)
    monkeypatch.setattr(ekylibre_client, "_resolve", lambda host: ["93.184.216.34"])
    return fake


@pytest.fixture()
def farm(app, login_as):
    client = login_as(role="admin")
    _agri_instance()
    external_config.set_enabled("ekylibre", True)
    return client


def test_adapter_parsing():
    plants = [ekylibre_client.production(p) for p in PLANTS]
    assert plants[0].surface_ha == Decimal("12.5000") and plants[0].activity_id == 3
    assert plants[0].started_on == date(2025, 10, 1) and plants[0].stopped_on == date(2026, 8, 31)
    assert plants[1].surface_ha == Decimal("0.3500") and plants[1].stopped_on is None
    assert ekylibre_client.surface_ha(12.5) == Decimal("12.5000")
    assert ekylibre_client.surface_ha("12.5 hectare") == Decimal("12.5000")
    with pytest.raises(EkylibreError):
        ekylibre_client.surface_ha("4 acre")
    i = ekylibre_client.intervention(INTERVENTIONS[0])
    assert i.targets == [11] and i.tools == [40] and i.working_seconds == 10800
    assert i.costs == {"inputs": Decimal("300.0"), "doers": Decimal("60.5"), "tools": Decimal("50.0"),
                       "receptions": Decimal("0.0")} and i.total_cost == Decimal("410.5")
    m = ekylibre_client.matter(MATTERS[0])
    assert (m.quantity, m.unit, m.variant_id) == (Decimal("1.5"), "t", 9)


def test_url_checks(monkeypatch):
    monkeypatch.setattr(ekylibre_client, "_resolve", lambda host: ["93.184.216.34"])
    assert ekylibre_client.check_url("https://demo.ekylibre.test/backend") == URL
    for bad in ("http://demo.ekylibre.test", "https://user:pw@demo.ekylibre.test", "ftp://x", ""):
        with pytest.raises(EkylibreError):
            ekylibre_client.check_url(bad)
    for private in ("10.0.0.5", "127.0.0.1", "169.254.169.254", "::1"):
        monkeypatch.setattr(ekylibre_client, "_resolve", lambda host, ip=private: [ip])
        with pytest.raises(EkylibreError, match="privé"):
            ekylibre_client.check_url(URL)


def test_http_errors(server):
    server.routes[("GET", "/api/v2/profile")] = _response(302)
    client = ekylibre_client.Client(URL, "camille@example.org", "tok")
    with pytest.raises(EkylibreError, match="redirige"):
        client.profile()
    server.routes[("GET", "/api/v2/profile")] = _response(401, {"message": "Unauthorized."})
    with pytest.raises(EkylibreError, match="refusés"):
        client.profile()
    server.routes[("GET", "/api/v2/products/plants")] = _response(body={"not": "a list"})
    with pytest.raises(EkylibreError, match="liste attendue"):
        client.productions()


def test_response_size_bounded(server, monkeypatch):
    monkeypatch.setattr(ekylibre_client, "MAX_BYTES", 100)
    server.routes[("GET", "/api/v2/products/plants")] = _response(raw=b"[" + b" " * 500 + b"]")
    with pytest.raises(EkylibreError, match="volumineuse"):
        ekylibre_client.Client(URL, "camille@example.org", "tok").productions()


def test_connect_check_revoke(farm, server):
    resp = farm.post("/api/v1/ekylibre/connect", json={"url": URL + "/", "email": "camille@example.org",
                                                       "password": "mot-de-passe"})
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert data["configured"] and data["url"] == URL and data["email"] == "camille@example.org"
    assert "connecté en tant que Camille Essai" in data["notices"][1]["message"]
    stored = {r.key: r.value for r in ExternalConnection.query.filter_by(service="ekylibre")}
    assert stored["token"] == "tok-secret" and "mot-de-passe" not in json.dumps(stored)
    assert "tok-secret" not in json.dumps(data)                              # jeton jamais renvoyé
    method, path, kwargs = server.calls[0]
    assert (method, path, kwargs["json"]) == ("POST", "/api/v2/tokens", {"email": "camille@example.org",
                                                                         "password": "mot-de-passe"})
    profile_call = next(c for c in server.calls if c[1] == "/api/v2/profile")
    assert profile_call[2]["headers"]["Authorization"] == "simple-token camille@example.org tok-secret"
    assert profile_call[2]["allow_redirects"] is False
    assert integrations.run_check("ekylibre").ok
    resp = farm.post("/api/v1/ekylibre/revoke")
    assert resp.status_code == 200 and not resp.get_json()["configured"]
    assert ("DELETE", "/api/v2/tokens/tok-secret") in [(m, p) for m, p, _ in server.calls]
    assert not external_config.get("ekylibre", "token")


def test_connect_refused(farm, server):
    server.routes[("POST", "/api/v2/tokens")] = _response(401, {"message": "Invalid email or password."})
    resp = farm.post("/api/v1/ekylibre/connect", json={"url": URL, "email": "x@example.org", "password": "faux"})
    assert resp.status_code == 422 and "refusés" in resp.get_json()["error"]["message"]
    assert not external_config.get("ekylibre", "token")


def test_sync_snapshot_roundtrip(farm, server):
    ekylibre_sync.connect(URL, "camille@example.org", "pw")
    result = ekylibre_sync.sync()
    assert result["counts"] == {"productions": 2, "interventions": 1, "matters": 1}
    plants, at = ekylibre_sync.snapshot("productions")
    assert isinstance(at, datetime) and plants[0].surface_ha == Decimal("12.5000") and plants[0].started_on == date(2025, 10, 1)
    interventions, _ = ekylibre_sync.snapshot("interventions")
    assert interventions[0].costs["inputs"] == Decimal("300.0") and interventions[0].targets == [11]
    assert interventions[0].started_at.year == 2026
    matters, _ = ekylibre_sync.snapshot("matters")
    assert matters[0].quantity == Decimal("1.5")
    # Échec en cours de lecture : aucun instantané partiel, l'ancien reste.
    server.routes[("GET", "/api/v2/products/matters")] = _response(500)
    server.routes[("GET", "/api/v2/products/plants")] = _response(body=PLANTS[:1])
    with pytest.raises(EkylibreError):
        ekylibre_sync.sync()
    db.session.rollback()
    assert EkylibreSnapshot.query.filter_by(kind="productions").one().count == 2
    state = farm.get("/api/v1/ekylibre").get_json()
    assert state["snapshots"]["interventions"]["count"] == 1


def test_not_agri(app, login_as):
    client = login_as(role="admin")
    assert client.get("/api/v1/ekylibre").status_code == 404
    assert not external_config.applies("ekylibre")
