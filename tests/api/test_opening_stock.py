"""Lot CG5.c (BOI-BA-REG-40-10-10 § 190 à 200, § 470) : stock d'entrée au passage du micro-BA au réel."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, Associate, Entity, FiscalYear, JournalEntry, ShareMovement, ShareMovementLine, TaxProfile
from app.models.journal_entry import SOURCE_STOCK_OPENING
from test_agri_fixtures import _agri_instance


@pytest.fixture()
def farm(app, login_as):
    client = login_as(role="admin")
    _agri_instance()
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    db.session.add(fy)
    db.session.add_all([TaxProfile(kind="ba_regime", value="micro", start_date=date(2023, 1, 1), end_date=date(2025, 12, 31)),
                        TaxProfile(kind="ba_regime", value="simplified", start_date=date(2026, 1, 1))])
    from app.services import organization
    organization.get().legal_form_code = "EI"
    db.session.commit()
    return {"client": client, "fy": fy, "url": f"/api/v1/fiscal-years/{fy.id}/opening-stock"}


def _entry(fy):
    entry = JournalEntry.query.filter_by(fiscal_year_id=fy.id, source=SOURCE_STOCK_OPENING).one()
    return {(l.account.code, l.debit_cents, l.credit_cents) for l in entry.lines}


def test_individual_farmer(farm):
    client, url, fy = farm["client"], farm["url"], farm["fy"]
    body = client.get(url).get_json()["item"]
    assert body["applies"] is True and body["lines"] == []
    stock = client.get(f"/api/v1/fiscal-years/{fy.id}/stock").get_json()["item"]
    assert stock["opening_stock"] is True
    r = client.post(f"{url}/lines", json={"account_code": "35511", "label": "Blé", "quantity": "10", "unit": "t",
                                          "cost_unit_cents": 18000, "market_unit_cents": 16000})
    assert r.status_code == 201, r.get_json()
    (line,) = r.get_json()["item"]["lines"]
    assert line["value_cents"] == 160000                                       # cours du jour inférieur (§ 195)
    client.post(f"{url}/lines", json={"account_code": "31151", "label": "Colza en terre", "method": "crop_advance",
                                      "amount_cents": 50000})
    assert client.post(f"{url}/lines", json={"account_code": "6011", "label": "x"}).status_code == 422
    resp = client.post(f"{url}/entry")
    assert resp.status_code == 200, resp.get_json()
    assert _entry(fy) == {("35511", 160000, 0), ("31151", 50000, 0), ("108", 0, 210000)}
    item = resp.get_json()["item"]
    assert item["total_cents"] == 210000 and "valeur la plus faible" in item["note"] and "38 sexdecies" in item["note"]
    client.put(f"{url}/lines/{line['id']}", json={"quantity": "12"})
    client.post(f"{url}/entry")                                                # repassée : une seule écriture
    assert _entry(fy) == {("35511", 192000, 0), ("31151", 50000, 0), ("108", 0, 242000)}
    from app.services import fec
    fec.validate(fy)                                                           # validée : stock figé (§ 197)
    db.session.commit()
    assert client.put(f"{url}/lines/{line['id']}", json={"quantity": "1"}).status_code == 409
    assert client.get(url).get_json()["item"]["frozen"] is True


def test_company_partner_accounts(farm):
    from app.services import organization
    client, url, fy = farm["client"], farm["url"], farm["fy"]
    organization.get().legal_form_code = "EARL"
    accounts = {c: Account(code=c, label=f"Associé {c}") for c in ("455901", "455902")}
    db.session.add_all(accounts.values())
    db.session.flush()
    people = []
    for i, code in enumerate(("455901", "455902")):
        entity = Entity(name=f"Associé {i}")
        db.session.add(entity)
        db.session.flush()
        people.append(Associate(entity_id=entity.id, account_id=accounts[code].id, is_operator=True))
    db.session.add_all(people)
    db.session.flush()
    move = ShareMovement(movement_date=date(2020, 1, 1), kind="subscription", description="Constitution")
    db.session.add(move)
    db.session.flush()
    db.session.add_all([ShareMovementLine(movement_id=move.id, associate_id=people[0].id, nature="full", parts=75),
                        ShareMovementLine(movement_id=move.id, associate_id=people[1].id, nature="full", parts=25)])
    db.session.commit()
    client.post(f"{url}/lines", json={"account_code": "35511", "label": "Blé", "quantity": "10", "unit": "t",
                                      "cost_unit_cents": 10000})
    assert client.post(f"{url}/entry").status_code == 200
    assert _entry(fy) == {("35511", 100000, 0), ("455901", 0, 75000), ("455902", 0, 25000)}   # D-CG5.1 : 455 au prorata
