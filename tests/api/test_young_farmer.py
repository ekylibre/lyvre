"""Lot AG6.b : abattement jeune agriculteur (art. 73 B, barème daté ba.ja.*, AGD23)."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, FiscalYear, Instance, Journal, ShareMovement, ShareMovementLine
from app.services import agri_profile, associates, young_farmer
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
    post_entry(fy.id, od.id, date(2026, 6, 30), "Ventes", [
        {"account_id": _id("411"), "label": "x", "debit_cents": 4000000, "credit_cents": 0},
        {"account_id": _id("7011"), "label": "x", "debit_cents": 0, "credit_cents": 4000000}])
    return {"client": client, "fy": fy, "url": f"/api/v1/fiscal-years/{fy.id}/tax-result"}


def test_scale(farm):
    fy = farm["fy"]
    assert young_farmer.compute(4000000, fy)["amount_cents"] == 3000000                    # 75 %
    assert young_farmer.compute(6000000, fy)["amount_cents"] == 2814000                    # 50 % × 50 700 + 30 % × 9 300
    assert young_farmer.compute(8000000, fy)["amount_cents"] == 3042000                    # plafonné à 67 600
    assert young_farmer.compute(6000000, fy, dja_cents=1)["amount_cents"] == 5628000       # 100 % + 60 %
    assert young_farmer.compute(1000000, fy, dja_cents=3000000)["amount_cents"] == 1000000 # au moins la DJA, ≤ base
    assert young_farmer.compute(-5000, fy)["amount_cents"] == 0
    assert young_farmer.eligible(date(2022, 1, 1), fy) is True and young_farmer.eligible(date(2021, 12, 30), fy) is False


def test_individual_farmer(farm):
    client = farm["client"]
    assert all(l["source"] != "young_farmer" for l in client.get(farm["url"]).get_json()["item"]["lines"])
    agri_profile.save({"young_farmer_since": "2024-03-01"})
    db.session.commit()
    body = client.get(farm["url"]).get_json()["item"]
    (line,) = [l for l in body["lines"] if l["source"] == "young_farmer"]
    assert line["amount_cents"] == -3000000 and body["fiscal_result_cents"] == 1000000
    assert body["fiscal_result_before_ja_cents"] == 4000000


def test_dja_year_individual(farm):
    client = farm["client"]
    agri_profile.save({"young_farmer_since": "2026-02-01"})
    db.session.commit()
    client.post("/api/v1/aids", json={"scheme": "dja", "campaign": 2026, "notified_cents": 3000000, "decision_on": "2026-03-01"})
    body = client.get(farm["url"]).get_json()["item"]
    (line,) = [l for l in body["lines"] if l["source"] == "young_farmer"]
    assert line["amount_cents"] == -4000000 and "DJA" in line["label"] and body["fiscal_result_cents"] == 0


def test_associate_ja_in_company(farm):
    client = farm["client"]
    Instance.query.one().has_associates = True
    db.session.commit()
    paul, parent, other = (associates.create({"new_name": n}) for n in ("Paul", "Parent", "Autre"))
    db.session.add(ShareMovement(movement_date=date(2026, 1, 1), kind="opening", nominal_cents=1000, lines=[
        ShareMovementLine(associate_id=paul.id, nature="full", parts=600),
        ShareMovementLine(associate_id=parent.id, nature="full", parts=400)]))
    db.session.commit()
    client.patch(f"/api/v1/associates/{paul.id}", json={"is_operator": True, "young_farmer_since": "2024-03-01"})
    client.patch(f"/api/v1/associates/{parent.id}", json={"young_farmer_since": "2025-01-01"})            # non exploitant
    body = client.get(farm["url"]).get_json()["item"]
    (line,) = [l for l in body["lines"] if l["source"] == "young_farmer"]
    assert line["amount_cents"] == -1800000 and line["associate_id"] == paul.id               # 75 % de 24 000
    split = {a["name"]: (a["fiscal_result_cents"], a["ja_cents"]) for a in body["associates"]}
    assert split == {"Paul": (600000, 1800000), "Parent": (1600000, 0)}
    assert body["fiscal_result_cents"] == 2200000
    assert any("non exploitant" in w for w in body["warnings"])
