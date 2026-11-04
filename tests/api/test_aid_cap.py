"""Lot AG3.e : contrôle des aides avec les montants publiés par l'ASP (Lexicon, jeu cap_beneficiaries).

Lexicon est simulé (aucun appel réseau) ; SIREN fictif.
"""
from datetime import date

import pytest
import requests

from app.extensions import db
from app.models import Account, CapPublished, FiscalYear, Journal
from app.models.journal_entry import SOURCE_INVENTORY
from app.services import organization
from app.services.ledger import post_entry
from test_agri_fixtures import _agri_instance

SIREN = "123456782"


class _Response:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


@pytest.fixture()
def lexicon(monkeypatch, app):
    app.config["LEXICON_API_KEY"] = "lex_test0000_" + "x" * 32
    calls = []
    state = {"status": 200, "body": {"siren": SIREN, "cap-by-year": [
        {"year": 2025, "feaga": 18500.5, "feader": 1200, "cofinanced": 300, "total": 20000.5},
        {"year": 2024, "feaga": 17000, "feader": 0, "cofinanced": 0, "total": 17000}]}}

    def fake_get(url, timeout=None, headers=None, **_):
        calls.append((url, headers))
        return _Response(state["status"], state["body"])

    monkeypatch.setattr(requests, "get", fake_get)
    yield {"calls": calls, "state": state}
    app.config["LEXICON_API_KEY"] = ""


@pytest.fixture()
def farm(app, login_as):
    client = login_as(role="admin")
    _agri_instance()
    organization.get().siren = SIREN
    fy = FiscalYear(label="2025", start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
    db.session.add_all([fy, Journal(code="BQ", label="Banque"), Journal(code="OD", label="OD")])
    db.session.commit()
    return {"client": client, "fy": fy}


def _line(code, debit, credit):
    return {"account_id": Account.query.filter_by(code=code).one().id, "label": "essai", "debit_cents": debit,
            "credit_cents": credit}


def test_compare_with_published_amounts(farm, lexicon):
    client, fy = farm["client"], farm["fy"]
    bq, od = Journal.query.filter_by(code="BQ").one(), Journal.query.filter_by(code="OD").one()
    post_entry(fy.id, bq.id, date(2025, 10, 16), "VIR ASP", [_line("512", 1500000, 0), _line("745", 0, 1500000)])
    post_entry(fy.id, od.id, date(2025, 12, 31), "PAR", [_line("441", 300000, 0), _line("745", 0, 300000)],
               source=SOURCE_INVENTORY)                                     # aide à recevoir : exclue
    aid = client.post("/api/v1/aids", json={"scheme": "basic_income", "campaign": 2025, "requested_cents": 2000000}).get_json()["item"]
    client.post(f"/api/v1/aids/{aid['id']}/payments", json={"paid_on": "2025-10-16", "amount_cents": 1500000, "kind": "advance"})
    body = client.get("/api/v1/aids/cap-check?year=2025").get_json()["item"]
    url, headers = lexicon["calls"][0]
    assert url.endswith(f"/links/enterprises/{SIREN}.json") and headers["Authorization"].startswith("Bearer lex_")
    assert body["published"] == {"feaga_cents": 1850050, "feader_cents": 120000, "cofinanced_cents": 30000,
                                 "total_cents": 2000050}
    assert body["paid_cents"] == 1500000 and body["ledger_cents"] == 1500000
    assert body["gap_paid_cents"] == -500050 and body["years"] == [2025, 2024]
    client.get("/api/v1/aids/cap-check?year=2024")                          # depuis le cache
    assert len(lexicon["calls"]) == 1 and CapPublished.query.count() == 2
    resp = client.post("/api/v1/aids/cap-check", json={"year": 2025})
    assert resp.status_code == 200 and len(lexicon["calls"]) == 2
    other = client.get("/api/v1/aids/cap-check?year=2023").get_json()["item"]
    assert other["published"] is None and "Aucune aide publiée pour 2023" in other["message"]


def test_unknown_siren_and_refused_key(farm, lexicon):
    client = farm["client"]
    lexicon["state"].update(status=404, body={"error": {"status": 404}})
    body = client.get("/api/v1/aids/cap-check?year=2025").get_json()["item"]
    assert body["found"] is False and body["published"] is None and "Aucune aide publiée" in body["message"]
    lexicon["state"].update(status=401, body={"error": {"status": 401}})
    resp = client.post("/api/v1/aids/cap-check", json={"year": 2025}).get_json()
    assert "refuse la clé" in resp["item"]["message"] and resp["notices"][0]["level"] == "warning"


def test_not_configured_or_no_siren(farm, app):
    client = farm["client"]
    app.config["LEXICON_API_KEY"] = ""
    body = client.get("/api/v1/aids/cap-check?year=2025").get_json()["item"]
    assert body["configured"] is False and "pas configuré" in body["message"]
    app.config["LEXICON_API_KEY"] = "lex_test0000_" + "x" * 32
    organization.get().siren = None
    db.session.commit()
    body = client.get("/api/v1/aids/cap-check?year=2025").get_json()["item"]
    assert "SIREN" in body["message"]
    app.config["LEXICON_API_KEY"] = ""
    assert client.get("/api/v1/aids/cap-check?year=abc").status_code == 422


def test_accountant_cannot_refresh(app, login_as, lexicon):
    client = login_as(role="accountant")
    _agri_instance()
    assert client.post("/api/v1/aids/cap-check", json={"year": 2025}).status_code == 403
