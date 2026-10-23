"""Module « Associés », lot A2 : registre des parts (mouvements, règles par type, situation et capital
à une date, prévisualisation, pièce jointe)."""
import io
import json
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, FiscalYear, Instance, Journal
from app.models.associate import ShareMovement
from app.services import associates
from app.services.ledger import post_entry


@pytest.fixture()
def admin(app, login_as, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "instance_path", str(tmp_path))
    client = login_as(role="admin")
    Instance.query.one().has_associates = True
    db.session.add(Account(code="455", label="Associés - Comptes courants", account_type="TIERS"))
    db.session.commit()
    return client


def _ids(*names):
    return [associates.create({"new_name": n}).id for n in names]


def _post(client, kind, day, lines, nominal=None, **extra):
    body = {"kind": kind, "movement_date": day, "lines": [
        {"associate_id": a, "nature": n, "parts": p} for a, n, p in lines], **extra}
    if nominal is not None:
        body["nominal"] = nominal
    return client.post("/api/v1/share-movements", json=body)


def _parts(client, at=None):
    url = "/api/v1/share-movements" + (f"?at={at}" if at else "")
    meta = client.get(url).get_json()["meta"]
    return {row["name"]: row["parts"] for row in meta["situation"]}, meta["capital"]


def test_constitution_then_donation_with_usufruct_reserved(admin):
    parent, child1, child2 = _ids("Parent", "Enfant 1", "Enfant 2")
    created = _post(admin, "subscription", "2019-07-29", [(parent, "full", 1000)], nominal="10")
    assert created.status_code == 201, created.get_json()
    # US3 : donation de la nue-propriété de 300 parts, le parent garde l'usufruit.
    donation = _post(admin, "donation", "2020-01-15", [
        (parent, "full", -300), (parent, "usufruct", 300), (child1, "bare", 150), (child2, "bare", 150)])
    assert donation.status_code == 201, donation.get_json()

    parts, capital = _parts(admin)
    assert parts["Parent"] == {"full": 700, "usufruct": 300, "bare": 0}
    assert parts["Enfant 1"] == {"full": 0, "usufruct": 0, "bare": 150}
    assert capital["parts"] == 1000 and capital["nominal_cents"] == 1000 and capital["capital_cents"] == 1000000
    # Le compte 101 vaut 0 : écart signalé, pas bloquant.
    assert any("101" in w for w in capital["warnings"])

    # US9 : situation avant la donation.
    parts, capital = _parts(admin, "2019-12-31")
    assert parts["Parent"] == {"full": 1000, "usufruct": 0, "bare": 0} and parts["Enfant 1"]["bare"] == 0

    # Réunion de l'usufruit sur la tête du premier enfant (décès de l'usufruitier, simplifié).
    reunion = _post(admin, "reunion", "2024-05-01", [(parent, "usufruct", -150), (child1, "bare", -150),
                                                      (child1, "full", 150)])
    assert reunion.status_code == 201, reunion.get_json()
    parts, capital = _parts(admin)
    assert parts["Enfant 1"] == {"full": 150, "usufruct": 0, "bare": 0} and capital["parts"] == 1000
    assert not any("usufruit" in w for w in capital["warnings"])


def test_capital_matches_ledger(admin):
    (alone,) = _ids("Seul")
    capital_account = Account(code="101", label="Capital", account_type="EQUITY")
    bank = Account(code="512", label="Banque", account_type="BANK")
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    journal = Journal(code="OD", label="OD")
    db.session.add_all([capital_account, bank, fy, journal])
    db.session.commit()
    post_entry(fy.id, journal.id, date(2026, 1, 2), "Capital", [
        {"account_id": bank.id, "debit_cents": 100000, "credit_cents": 0},
        {"account_id": capital_account.id, "debit_cents": 0, "credit_cents": 100000}])
    _post(admin, "opening", "2026-01-01", [(alone, "full", 100)], nominal="10,00")
    _, capital = _parts(admin)
    assert capital["capital_cents"] == capital["ledger_cents"] == 100000 and capital["warnings"] == []


@pytest.mark.parametrize("kind, lines, message", [
    ("subscription", [(0, "full", -10)], "reçues"),
    ("reduction", [(0, "full", 10)], "cédées"),
    ("transfer", [(0, "full", -10), (1, "full", 5)], "autant de parts"),
    ("donation", [(0, "full", -10), (1, "bare", 10)], "Démembrement"),
    ("donation", [(0, "full", -10)], "capital ne change pas"),
    ("transfer", [(0, "full", -2000), (1, "full", 2000)], "aurait -1000"),
])
def test_movement_rules(admin, kind, lines, message):
    ids = _ids("A", "B")
    _post(admin, "subscription", "2020-01-01", [(ids[0], "full", 1000)], nominal="1")
    resp = _post(admin, kind, "2021-01-01", [(ids[i], n, p) for i, n, p in lines], nominal="1")
    assert resp.status_code == 422 and message in resp.get_json()["error"]["message"], resp.get_json()


def test_field_errors(admin):
    resp = admin.post("/api/v1/share-movements", json={"kind": "subscription", "lines": [
        {"associate_id": 999, "nature": "x", "parts": 0}]})
    fields = resp.get_json()["error"]["fields"]
    assert resp.status_code == 422
    assert {"movement_date", "nominal", "lines.0.associate_id", "lines.0.nature", "lines.0.parts"} <= set(fields)


def test_later_movement_protects_earlier_one(admin):
    a, b = _ids("A", "B")
    first = _post(admin, "subscription", "2020-01-01", [(a, "full", 100)], nominal="1").get_json()["item"]
    _post(admin, "transfer", "2021-01-01", [(a, "full", -100), (b, "full", 100)])
    # Un mouvement antérieur à la cession ne peut pas retirer les parts cédées ensuite.
    late = _post(admin, "transfer", "2020-06-01", [(a, "full", -50), (b, "full", 50)])
    assert late.status_code == 422 and "01/01/2021" in late.get_json()["error"]["message"]
    blocked = admin.delete(f"/api/v1/share-movements/{first['id']}")
    assert blocked.status_code == 409 and "Suppression impossible" in blocked.get_json()["error"]["message"]
    # Modifier la souscription à la hausse reste possible.
    edit = admin.patch(f"/api/v1/share-movements/{first['id']}", json={
        "kind": "subscription", "movement_date": "2020-01-01", "nominal": "1",
        "lines": [{"associate_id": a, "nature": "full", "parts": 120}]})
    assert edit.status_code == 200, edit.get_json()
    assert _parts(admin)[0]["A"]["full"] == 20


def test_preview_without_saving(admin):
    a, b = _ids("A", "B")
    _post(admin, "subscription", "2020-01-01", [(a, "full", 100)], nominal="1")
    resp = admin.post("/api/v1/share-movements/preview", json={
        "kind": "transfer", "movement_date": "2021-01-01",
        "lines": [{"associate_id": a, "nature": "full", "parts": -25}, {"associate_id": b, "nature": "full", "parts": 25}]})
    body = resp.get_json()
    assert resp.status_code == 200 and body["total_parts"] == 100
    assert {r["name"]: r["parts"]["full"] for r in body["rows"]} == {"A": 75, "B": 25}
    assert ShareMovement.query.count() == 1


def test_attachment_and_filter_by_associate(admin):
    a, b = _ids("A", "B")
    payload = {"kind": "subscription", "movement_date": "2020-01-01", "nominal": "1",
               "lines": [{"associate_id": a, "nature": "full", "parts": 10}]}
    resp = admin.post("/api/v1/share-movements", data={
        "payload": json.dumps(payload), "attachment": (io.BytesIO(b"%PDF-1.4 statuts"), "statuts.pdf")},
        content_type="multipart/form-data")
    assert resp.status_code == 201, resp.get_json()
    item = resp.get_json()["item"]
    assert item["attachment"]["name"] == "statuts.pdf"
    movement = ShareMovement.query.one()
    assert movement.attachment_path.startswith("parts/2020/01/")
    assert admin.get(item["attachment"]["url"]).data == b"%PDF-1.4 statuts"
    assert len(admin.get(f"/api/v1/share-movements?associate_id={a}").get_json()["items"]) == 1
    assert admin.get(f"/api/v1/share-movements?associate_id={b}").get_json()["items"] == []
    assert admin.delete(f"/api/v1/share-movements/{movement.id}").status_code == 200


def test_treasurer_reads_only(app, login_as):
    client = login_as(role="treasurer")
    Instance.query.one().has_associates = True
    db.session.add(Account(code="455", label="455", account_type="TIERS"))
    db.session.commit()
    (a,) = _ids("A")
    assert client.get("/api/v1/share-movements").status_code == 200
    assert _post(client, "subscription", "2020-01-01", [(a, "full", 1)], nominal="1").status_code == 403
