"""Essai de l'interface (10/11/2026), analytique : couverture nette, dotations reprises remplacées par les fiches,
lignes d'inventaire à quantité nulle, alertes d'inventaire regroupées."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, Asset, FiscalYear, Journal
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

    def entry(debit, credit, cents, source="MANUAL"):
        post_entry(fy.id, od.id, date(2026, 6, 30), "x", [
            {"account_id": _id(debit), "label": "x", "debit_cents": cents, "credit_cents": 0},
            {"account_id": _id(credit), "label": "x", "debit_cents": 0, "credit_cents": cents}], source=source)
    entry("60111", "401", 100000)
    entry("401", "60111", 20000)                                    # avoir
    entry("411", "7011", 500000)
    entry("7011", "411", 50000)                                     # avoir client
    entry("68112", "2815", 120000, source="FEC_IMPORT")             # dotation reprise d'un FEC
    return {"client": client, "fy": fy, "url": f"/api/v1/fiscal-years/{fy.id}/analytic/unallocated"}


def test_coverage_on_net_amounts(farm):
    view = farm["client"].get(farm["url"]).get_json()["item"]
    assert view["coverage"]["products"]["total_cents"] == 450000
    assert view["coverage"]["charges"]["total_cents"] == 80000 + 120000
    assert {g["account"]: g["amount_cents"] for g in view["groups"]}["60111"] == 80000
    assert view["replaced"] == []


def test_imported_depreciation_replaced_by_asset_records(farm):
    client, fy = farm["client"], farm["fy"]
    db.session.add(Asset(label="Tracteur", account_id=_id("2154"), acquired_on=date(2026, 1, 1),
                         in_service_date=date(2026, 1, 1), acquisition_cents=840000, method="linear",
                         duration_months=84, status="in_use"))
    db.session.commit()
    view = client.get(farm["url"]).get_json()["item"]
    assert "68112" not in {g["account"] for g in view["groups"]}
    assert [(r["account"], r["amount_cents"]) for r in view["replaced"]] == [("68112", 120000)]
    assert view["coverage"]["charges"]["total_cents"] == 80000
    data = client.get(f"/api/v1/fiscal-years/{fy.id}/activity-margins").get_json()["item"]
    assert data["unallocated"]["classes"].get("depreciation") == 120000          # fiche : 8 400 € / 7 ans
    classes = data["unallocated"]["classes"]
    assert classes["plant_specific"] == 80000 and classes["structure"] == 0          # dotation reprise non comptée


def test_inventory_zero_quantity_and_grouped_warning(farm):
    client, fy = farm["client"], farm["fy"]
    url = f"/api/v1/fiscal-years/{fy.id}/stock/lines"
    for label, quantity in (("Aliments", "0"), ("Engrais", "0"), ("Blé", "2")):
        resp = client.post(url, json={"account_code": "35511" if label == "Blé" else "31", "label": label,
                                      "quantity": quantity, "unit": "t", "method": "actual"})
        assert resp.status_code == 201, resp.get_json()
    warnings = client.get(f"/api/v1/fiscal-years/{fy.id}/activity-margins").get_json()["item"]["warnings"]
    stock = [w for w in warnings if w.startswith("Inventaire 2026")]
    assert stock == ["Inventaire 2026 : 1 ligne(s) sans valeur, écartée(s) des marges (« Blé ») — valorisez-les "
                     "(Compta › Immobilisations et stocks › Inventaire de clôture)."]
