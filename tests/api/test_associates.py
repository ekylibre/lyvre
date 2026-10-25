"""Module « Associés », lot A1 : option de l'instance, menu, associés et comptes courants 4551…"""
from datetime import date

from app.extensions import db
from app.menu_config import build_nav
from app.models import Account, Associate, Entity, FiscalYear, Instance, Journal
from app.models.associate import ShareMovement, ShareMovementLine
from app.services import associates
from app.services.ledger import post_entry


def _labels(nav):
    return {menu["label"] for menu in nav}


def _enable(on=True):
    Instance.query.one().has_associates = on
    db.session.commit()


def _accounts():
    db.session.add_all([Account(code="455", label="Associés - Comptes courants", account_type="TIERS"),
                        Account(code="512", label="Banque", account_type="BANK")])
    db.session.commit()


def test_menu_follows_the_instance_option():
    assert "Associés" not in _labels(build_nav("sci", is_admin=True))
    assert "Associés" in _labels(build_nav("sci", is_admin=True, features={"associates"}))
    assert "Associés" in _labels(build_nav("asso", is_admin=False, features={"associates"}))


def test_session_and_disabled_api(app, login_as):
    client = login_as(role="admin")
    body = client.get("/api/v1/session").get_json()
    assert body["instance"]["has_associates"] is False and "Associés" not in _labels(body["nav"])
    resp = client.get("/api/v1/associates")
    assert resp.status_code == 404 and resp.get_json()["error"]["code"] == "feature_disabled"
    _enable()
    body = client.get("/api/v1/session").get_json()
    assert "Associés" in _labels(body["nav"])


def test_option_set_from_structure_page_with_warning(app, login_as):
    client = login_as(role="admin")
    Instance.query.one().chart = "sci"  # une association n'a pas d'associés (option ignorée)
    db.session.commit()
    _accounts()
    org = client.get("/api/v1/organization").get_json()["item"]
    assert org["has_associates"] is False and org["associate_interest_rate"] == "0"
    saved = client.put("/api/v1/organization", json={"name": "SCI", "has_associates": True,
                                                     "associate_interest_rate": "1,5"})
    assert saved.status_code == 200, saved.get_json()
    assert saved.get_json()["item"]["has_associates"] is True
    assert saved.get_json()["item"]["associate_interest_rate"] == "1,5"
    assert Instance.query.one().has_associates
    bad = client.put("/api/v1/organization", json={"name": "SCI", "associate_interest_rate": "25"})
    assert bad.status_code == 422 and "associate_interest_rate" in bad.get_json()["error"]["fields"]

    # Désactivation avec un compte courant non soldé : avertissement, pas de refus.
    associate = associates.create({"new_name": "Lola"})
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    journal = Journal(code="OD", label="Opérations diverses")
    db.session.add_all([fy, journal])
    db.session.commit()
    bank = Account.query.filter_by(code="512").one()
    post_entry(fy.id, journal.id, date(2026, 3, 1), "Apport", [
        {"account_id": bank.id, "debit_cents": 50000, "credit_cents": 0},
        {"account_id": associate.account_id, "debit_cents": 0, "credit_cents": 50000}])
    off = client.put("/api/v1/organization", json={"name": "SCI", "has_associates": False})
    notices = off.get_json()["notices"]
    assert off.status_code == 200 and notices[-1]["level"] == "warning" and "Lola" in notices[-1]["message"]
    assert not Instance.query.one().has_associates


def test_sci_instance_created_with_the_option(app, login_as, monkeypatch):
    from app.api import instances as api_instances
    monkeypatch.setattr(api_instances, "provision_sqlite_database", lambda url, chart: None)
    client = login_as(is_admin=True, role="admin")
    for slug, chart, expected in (("une-sci", "sci", True), ("une-asso", "asso", False)):
        created = client.post("/api/v1/instances", json={"slug": slug, "label": slug, "chart": chart})
        assert created.status_code == 201, created.get_json()
        assert Instance.query.filter_by(slug=slug).one().has_associates is expected


def test_create_list_update_delete(app, login_as):
    client = login_as(role="admin")
    _enable()
    _accounts()
    db.session.add(Entity(name="Alain Martin", entity_type="AUTRE"))
    db.session.commit()
    pascal = Entity.query.one()

    created = client.post("/api/v1/associates", json={"entity_id": str(pascal.id)})
    assert created.status_code == 201, created.get_json()
    assert created.get_json()["item"]["account_code"] == "4551001"
    account = Account.query.filter_by(code="4551001").one()
    assert account.account_type == "TIERS" and account.parent.code == "455"
    assert account.label == "Compte courant — Alain Martin"

    # Nouveau tiers créé à la volée, compte suivant ; un homonyme existant serait repris.
    second = client.post("/api/v1/associates", json={"new_name": "Agnès Martin", "interest_rate": "2"})
    assert second.get_json()["item"]["account_code"] == "4551002"
    assert second.get_json()["item"]["interest_rate"] == "2"
    assert Entity.query.filter_by(name="Agnès Martin").one().entity_type == "AUTRE"

    errors = [
        ({"entity_id": str(pascal.id)}, "entity_id"),           # déjà associé
        ({"new_name": "X", "account_code": "4551002"}, "account_code"),  # compte pris
        ({"new_name": "Y", "account_code": "401"}, "account_code"),      # pas un 455
        ({"new_name": "Z", "interest_rate": "30"}, "interest_rate"),
        ({}, "entity_id"),
    ]
    for body, field in errors:
        resp = client.post("/api/v1/associates", json=body)
        assert resp.status_code == 422 and field in resp.get_json()["error"]["fields"], body

    listing = client.get("/api/v1/associates").get_json()
    assert [a["name"] for a in listing["items"]] == ["Agnès Martin", "Alain Martin"]
    assert listing["meta"]["next_account_code"] == "4551003"
    assert all(e["label"] not in ("Agnès Martin", "Alain Martin") for e in listing["meta"]["entities"])

    associate = Associate.query.filter_by(entity_id=pascal.id).one()
    moved = client.patch(f"/api/v1/associates/{associate.id}", json={"account_code": "45510300", "notes": "Gérant"})
    assert moved.status_code == 200 and moved.get_json()["item"]["account_code"] == "45510300"
    assert moved.get_json()["item"]["notes"] == "Gérant"

    assert client.delete(f"/api/v1/associates/{associate.id}").status_code == 200
    assert Entity.query.get(pascal.id) is not None and Account.query.filter_by(code="45510300").one()


def test_holdings_and_delete_blocked_by_register(app, login_as):
    client = login_as(role="admin")
    _enable()
    _accounts()
    usufruct = associates.create({"new_name": "Parent"})
    bare = associates.create({"new_name": "Enfant"})
    movement = ShareMovement(movement_date=date(2026, 1, 10), kind="opening", nominal_cents=1000, lines=[
        ShareMovementLine(associate_id=usufruct.id, nature="usufruct", parts=300),
        ShareMovementLine(associate_id=bare.id, nature="bare", parts=300),
        ShareMovementLine(associate_id=bare.id, nature="full", parts=700),
    ])
    db.session.add(movement)
    db.session.commit()

    items = {a["name"]: a for a in client.get("/api/v1/associates").get_json()["items"]}
    assert items["Parent"]["parts"] == {"full": 0, "usufruct": 300, "bare": 0}
    assert items["Parent"]["percent"]["usufruct"] == 30.0
    assert items["Enfant"]["percent"] == {"full": 70.0, "usufruct": 0.0, "bare": 30.0}
    before = client.get("/api/v1/associates?at=2026-01-09").get_json()
    assert before["meta"]["total_parts"] == 0 and all(a["is_out"] for a in before["items"])

    blocked = client.delete(f"/api/v1/associates/{usufruct.id}")
    assert blocked.status_code == 409 and "registre" in blocked.get_json()["error"]["message"]


def test_roles(app, login_as):
    client = login_as(role="treasurer")
    _enable()
    _accounts()
    associate = associates.create({"new_name": "Lola"})
    assert client.get("/api/v1/associates").status_code == 200
    assert client.get(f"/api/v1/associates/{associate.id}").status_code == 200
    assert client.post("/api/v1/associates", json={"new_name": "X"}).status_code == 403
    assert client.patch(f"/api/v1/associates/{associate.id}", json={"notes": "x"}).status_code == 403
    assert client.delete(f"/api/v1/associates/{associate.id}").status_code == 403


def test_account_locked_once_it_has_entries(app, login_as):
    client = login_as(role="admin")
    _enable()
    _accounts()
    associate = associates.create({"new_name": "Lola"})
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    journal = Journal(code="OD", label="OD")
    db.session.add_all([fy, journal])
    db.session.commit()
    bank = Account.query.filter_by(code="512").one()
    post_entry(fy.id, journal.id, date(2026, 2, 1), "Remboursement", [
        {"account_id": associate.account_id, "debit_cents": 1000, "credit_cents": 0},
        {"account_id": bank.id, "debit_cents": 0, "credit_cents": 1000}])
    detail = client.get(f"/api/v1/associates/{associate.id}").get_json()
    assert detail["item"]["balance_cents"] == -1000  # débiteur : l'associé doit à la société
    assert detail["meta"] == {"can_delete": False, "account_locked": True}
    resp = client.patch(f"/api/v1/associates/{associate.id}", json={"account_code": "4551009"})
    assert resp.status_code == 422 and "écritures" in resp.get_json()["error"]["message"]
