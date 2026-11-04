"""Lot AG2.e : remboursement forfaitaire agricole (3520).

Ventes 2026 (comptes 70) :
- Laiterie (SIREN : assujettie) : lait 7012 10 000 € (classe high, proposée par la catégorie), fromages 7013 1 000 €
  (catégorie « produits transformés » : exclue) ;
- particulier : lait 7012 2 000 € (client non assujetti : exclu) ;
- négociant de l'UE : légumes 7011 5 000 € (sans classe → à choisir : low).
→ forfait = 10 000 × 5,59 % + 5 000 × 4,43 % = 559 + 221,50 = 780,50 → 781 €.
"""
from datetime import date

import pytest

from app.extensions import db
from app.models import (
    Account, Associate, Entity, FiscalYear, Instance, Journal, JournalEntry, RfaClaim, SimpleCategory,
)
from app.services import rfa
from app.services.ledger import post_entry

CODES = ("411", "512", "7011", "7012", "7013", "44583", "741", "455")


def _setup(bookkeeping="double"):
    inst = Instance.query.filter_by(slug="test").one()
    inst.chart, inst.bookkeeping = "agri", bookkeeping
    accounts = {code: Account(code=code, label=f"Compte {code}", account_type="TIERS") for code in CODES}
    years = {y: FiscalYear(label=str(y), start_date=date(y, 1, 1), end_date=date(y, 12, 31)) for y in (2025, 2026, 2027)}
    db.session.add_all([*accounts.values(), *years.values(), Journal(code="VT", label="Ventes"), Journal(code="OD", label="OD")])
    db.session.flush()
    db.session.add_all([
        SimpleCategory(code="ventes_produits_animaux", label="Lait, œufs", kind="income", account_id=accounts["7012"].id),
        SimpleCategory(code="ventes_transformes", label="Transformés", kind="income", account_id=accounts["7013"].id)])
    entities = {"dairy": Entity(name="Laiterie", siren="123456789"), "private": Entity(name="Particulier"),
                "eu": Entity(name="Négoce UE", vat_regime="eu")}
    db.session.add_all(entities.values())
    db.session.commit()
    return {"accounts": accounts, "years": years, "entities": entities}


def _sale(data, day, entity, account, cents):
    acc = data["accounts"]
    post_entry(data["years"][day.year].id, Journal.query.filter_by(code="VT").one().id, day, "vente", [
        {"account_id": acc["411"].id, "label": "client", "debit_cents": cents, "credit_cents": 0,
         "entity_id": data["entities"][entity].id},
        {"account_id": acc[account].id, "label": "vente", "debit_cents": 0, "credit_cents": cents}])


def _year(data):
    _sale(data, date(2026, 3, 1), "dairy", "7012", 1000000)
    _sale(data, date(2026, 4, 1), "dairy", "7013", 100000)
    _sale(data, date(2026, 5, 1), "private", "7012", 200000)
    _sale(data, date(2026, 6, 1), "eu", "7011", 500000)


@pytest.fixture()
def farm(app, login_as):
    client = login_as()
    data = _setup()
    _year(data)
    return {"client": client, **data}


def test_forfait_by_rate_class_and_buyer(farm):
    client = farm["client"]
    body = client.get("/api/v1/rfa/2026").get_json()
    assert body["unclassified_cents"] == 500000 and body["problems"]          # légumes sans classe : bloquant
    acc = farm["accounts"]["7011"]
    assert client.put(f"/api/v1/rfa/accounts/{acc.id}/rate", json={"rfa_rate": "low"}).status_code == 200
    body = client.get("/api/v1/rfa/2026").get_json()
    assert (body["high_base_cents"], body["low_base_cents"]) == (1000000, 500000)
    assert body["excluded_cents"] == 100000 and body["non_eligible_cents"] == 200000
    assert body["amount_cents"] == 78100 and body["problems"] == []
    clients = {c["name"]: c for c in body["clients"]}
    assert clients["Laiterie"]["buyer"] == "professional" and clients["Laiterie"]["buyer_guessed"] is True
    assert clients["Particulier"]["eligible"] is False and clients["Négoce UE"]["buyer"] == "eu"
    assert "Attestation d'achats manquante." in clients["Laiterie"]["issues"]
    assert clients["Négoce UE"]["issues"] == []                              # pas d'attestation pour l'UE


def test_attestation_checks_and_buyer_override(farm):
    client = farm["client"]
    dairy, private = farm["entities"]["dairy"], farm["entities"]["private"]
    resp = client.post(f"/api/v1/rfa/2026/attestations/{dairy.id}", json={"amount_cents": 900000, "received_on": "2027-01-10"})
    assert resp.status_code == 201
    clients = {c["name"]: c for c in client.get("/api/v1/rfa/2026").get_json()["clients"]}
    assert any("différente" in i for i in clients["Laiterie"]["issues"])
    client.post(f"/api/v1/rfa/2026/attestations/{dairy.id}", json={"amount_cents": 1005000})  # écart < 1 %
    clients = {c["name"]: c for c in client.get("/api/v1/rfa/2026").get_json()["clients"]}
    assert clients["Laiterie"]["issues"] == []
    assert client.put(f"/api/v1/rfa/buyers/{private.id}", json={"rfa_buyer": "professional"}).status_code == 200
    body = client.get("/api/v1/rfa/2026").get_json()
    assert body["high_base_cents"] == 1200000
    assert client.put(f"/api/v1/rfa/buyers/{private.id}", json={"rfa_buyer": "autre"}).status_code == 422


def test_attestation_with_file(farm):
    client = farm["client"]
    dairy = farm["entities"]["dairy"]
    import io
    import json
    resp = client.post(f"/api/v1/rfa/2026/attestations/{dairy.id}", content_type="multipart/form-data", data={
        "payload": json.dumps({"amount_cents": 1000000}), "attachment": (io.BytesIO(b"%PDF-1.4 test"), "attestation.pdf")})
    assert resp.status_code == 201, resp.get_json()
    item = resp.get_json()["item"]
    assert item["has_file"] is True
    assert client.get(f"/api/v1/rfa/attestations/{item['id']}/file").data.startswith(b"%PDF")
    assert client.delete(f"/api/v1/rfa/attestations/{item['id']}").status_code == 200


def test_declare_entry_cancel_and_refund(farm):
    client = farm["client"]
    acc = farm["accounts"]["7011"]
    assert client.post("/api/v1/rfa/2026/declare", json={"declared_on": "2027-01-15"}).status_code == 409  # sans classe
    client.put(f"/api/v1/rfa/accounts/{acc.id}/rate", json={"rfa_rate": "low"})
    assert client.post("/api/v1/rfa/2026/declare", json={"declared_on": "2026-12-15"}).status_code == 422  # trop tôt
    resp = client.post("/api/v1/rfa/2026/declare", json={"declared_on": "2027-01-15"})
    assert resp.status_code == 201, resp.get_json()
    claim = RfaClaim.query.one()
    assert (claim.amount_cents, claim.high_base_cents, claim.low_base_cents) == (78100, 1000000, 500000)
    lines = {l.account.code: (l.debit_cents, l.credit_cents) for l in claim.entry.lines}
    assert lines == {"44583": (78100, 0), "741": (0, 78100)} and claim.entry.entry_date == date(2027, 1, 15)
    dairy = farm["entities"]["dairy"]
    assert client.post(f"/api/v1/rfa/2026/attestations/{dairy.id}", json={"amount_cents": 1}).status_code == 409  # figées
    entry_id = claim.entry_id
    assert client.delete("/api/v1/rfa/2026/declare").status_code == 200
    assert RfaClaim.query.count() == 0 and db.session.get(JournalEntry, entry_id) is None
    client.post("/api/v1/rfa/2026/declare", json={"declared_on": "2027-01-15"})
    assert client.post("/api/v1/rfa/2026/refunded", json={"refunded_on": "2027-03-01"}).status_code == 200
    assert client.delete("/api/v1/rfa/2026/declare").status_code == 409


def test_simple_bookkeeping_has_no_entry(app, login_as):
    client = login_as()
    data = _setup("simple")
    _year(data)
    client.put(f"/api/v1/rfa/accounts/{data['accounts']['7011'].id}/rate", json={"rfa_rate": "excluded"})
    resp = client.post("/api/v1/rfa/2026/declare", json={"declared_on": "2027-02-01"})
    assert resp.status_code == 201, resp.get_json()
    claim = RfaClaim.query.one()
    assert claim.entry_id is None and claim.amount_cents == 55900
    assert not any("Partie double" in w for w in client.get("/api/v1/rfa/2026").get_json()["warnings"])


def test_threshold_multiplied_by_gaec_associates(farm):
    _sale(farm, date(2025, 6, 1), "dairy", "7012", 8000000)    # 80 000 € en 2025, 18 000 € en 2026 → 49 000 €
    data = rfa.compute(2026, today=date(2027, 1, 2))
    assert data["threshold"]["average_cents"] == 4900000 and data["threshold"]["over"] is True
    from app.services import organization
    org = organization.get()
    org.legal_form_code = "GAEC"
    for name in ("A", "B"):
        entity = Entity(name=f"Associé {name}")
        account = Account(code=f"4551{name}", label=f"Associé {name}", account_type="TIERS")
        db.session.add_all([entity, account])
        db.session.flush()
        db.session.add(Associate(entity_id=entity.id, account_id=account.id))
    db.session.commit()
    data = rfa.compute(2026, today=date(2027, 1, 2))
    assert data["threshold"]["factor"] == 2 and data["threshold"]["over"] is False


def test_exports_and_chart_guard(farm):
    client = farm["client"]
    assert client.get("/rfa/2026.xlsx").data[:2] == b"PK"
    assert client.get("/rfa/2026.pdf").data[:4] == b"%PDF"
    Instance.query.filter_by(slug="test").one().chart = "societe"
    db.session.commit()
    assert client.get("/api/v1/rfa/2026").status_code == 404
