"""Essai de l'interface (09/11/2026) : indices de la comptabilité et usages des réponses (Structure › Activités et démarches)."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, FiscalYear, Journal
from app.services import agri_profile
from app.services.ledger import post_entry
from test_agri_fixtures import _agri_instance


def _id(code):
    return Account.query.filter_by(code=code).one().id


@pytest.fixture()
def farm(app, login_as):
    client = login_as(role="admin")
    _agri_instance()
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    od = Journal(code="OD", label="OD")
    db.session.add_all([fy, od])
    db.session.commit()

    def post(account, cents, side):
        other = "411" if side == "credit" else "401"
        lines = [{"account_id": _id(account), "label": "x", "debit_cents": cents if side == "debit" else 0,
                  "credit_cents": cents if side == "credit" else 0},
                 {"account_id": _id(other), "label": "x", "debit_cents": cents if side == "credit" else 0,
                  "credit_cents": cents if side == "debit" else 0}]
        post_entry(fy.id, od.id, date(2026, 6, 30), "x", lines)

    return {"client": client, "post": post}


def test_hints_from_the_ledger(farm):
    farm["post"]("742", 1_000_000, "credit")
    farm["post"]("641", 50_000, "debit")
    farm["post"]("6131", 200_000, "debit")
    farm["post"]("7014", 5_000_000, "credit")
    body = farm["client"].get("/api/v1/agri-profile").get_json()
    hints = body["hints"]
    assert hints["pac"]["suggested"] and "Compte 742 mouvementé" in hints["pac"]["text"] and not hints["pac"]["conflict"]
    assert "641" in hints["employer"]["text"]
    assert "Fermages payés (6131)" in hints["leases"]["text"]
    assert "sans production animale" in hints["productions"]["text"] and not hints["productions"]["conflict"]
    assert "plant_protection" not in hints and "irrigation" not in hints
    assert body["item"] == {}                                        # un indice ne répond jamais à la place


def test_conflicts_after_answers(farm):
    farm["post"]("742", 1_000_000, "credit")
    farm["post"]("6131", 200_000, "debit")
    farm["post"]("7014", 5_000_000, "credit")
    body = farm["client"].put("/api/v1/agri-profile", json={"pac": False, "leases": [], "productions": ["field_crops"]}).get_json()
    assert body["hints"]["pac"]["conflict"] and body["hints"]["leases"]["conflict"] and body["hints"]["productions"]["conflict"]
    agri_profile.save({"pac": True, "productions": ["pigs"], "leases": [{"label": "Bail", "due": "11-11"}]})
    hints = agri_profile.hints()
    assert not hints["pac"]["conflict"] and not hints["leases"]["conflict"] and "productions" not in hints


def test_uses_list_the_deadlines(farm):
    uses = farm["client"].get("/api/v1/agri-profile").get_json()["uses"]
    assert any(t.startswith("PAC-01 ") for t in uses["pac"])
    assert uses["leases"] and uses["productions"]
