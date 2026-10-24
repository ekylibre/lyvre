"""Lot F5 : immobilisations (méthodes d'Ekylibre, base 360), dotations, mise en service, sortie, états."""
from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import Account, Asset, AssetDepreciation, FiscalYear, Journal, JournalEntry, Organization
from app.services import assets, organization


def _error(resp, status):
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()["error"]


@pytest.fixture()
def books(app):
    years = [FiscalYear(label=str(y), start_date=date(y, 1, 1), end_date=date(y, 12, 31)) for y in (2026, 2027)]
    accounts = [Account(code=c, label=f"Compte {c}", account_type="OTHER") for c in
                ("2154", "2183", "2313", "28", "6811", "6752", "7752", "462", "512100", "211")]
    db.session.add_all([*years, Journal(code="OD", label="Opérations diverses"), *accounts])
    db.session.commit()
    Account.query.filter_by(code="28").one().is_header = True
    db.session.commit()
    return years[0]


def _acc(code):
    return Account.query.filter_by(code=code).one()


def _asset(**kw):
    data = {"label": "Perceuse", "account_id": _acc("2154").id, "acquired_on": "2026-03-15", "in_service_date": "2026-03-15",
            "acquisition_cents": 180000, "method": "linear", "duration_months": 60}
    data.update(kw)
    asset = assets.save(None, data)
    db.session.commit()
    return asset


def test_days360_like_ekylibre():
    assert assets.days360(date(2026, 3, 15), date(2026, 12, 31)) == 286
    assert assets.days360(date(2026, 3, 15), date(2031, 3, 14)) == 1800
    assert assets.days360(date(2026, 1, 1), date(2026, 12, 31)) == 360
    assert assets.days360(date(2026, 2, 1), date(2026, 2, 28)) == 30


def test_linear_prorata_and_total(books):
    asset = _asset()
    rows = assets.schedule(asset)
    assert rows[0].days == 286 and rows[0].amount_cents == round(180000 * 286 / 1800) == 28600
    assert sum(r.amount_cents for r in rows) == 180000 and rows[-1].stop == date(2031, 3, 14)
    assert [r.label for r in rows][:3] == ["2026", "2027", "2028"]
    assert rows[1].amount_cents == 36000  # année pleine : 1/5
    assert asset.depreciation_account.code == "28154"  # créé sous 28


def test_regressive_switches_to_linear(books):
    asset = _asset(method="regressive", acquired_on="2026-01-10", in_service_date="2026-01-10", acquisition_cents=100000)
    assert asset.fiscal_coefficient == Decimal("1.75")
    rows = assets.schedule(asset)
    assert [r.amount_cents for r in rows] == [35000, 22750, 14788, 13731, 13731]
    assert sum(r.amount_cents for r in rows) == 100000


def test_components_and_land(books):
    building = _asset(label="Immeuble", acquisition_cents=0, method="none")
    _asset(label="Terrain", account_id=_acc("211").id, acquisition_cents=50000, method="none", parent_id=building.id)
    _asset(label="Gros œuvre", acquisition_cents=300000, duration_months=480, parent_id=building.id, acquired_on="2026-01-01",
           in_service_date="2026-01-01")
    data = assets.payload(db.session.get(Asset, building.id))
    assert data["acquisition_cents"] == 350000 and len(data["components"]) == 2
    assert [r["amount_cents"] for r in assets.depreciation_rows(books)] == [7500]


def test_post_depreciation_and_revision(books, login_as):
    asset = _asset()
    client = login_as()
    base = f"/api/v1/fiscal-years/{books.id}/closing/depreciation"
    assert client.get(base).get_json()["items"][0]["amount_cents"] == 28600
    resp = client.post(base)
    assert resp.status_code == 200, resp.get_json()
    entry = JournalEntry.query.filter_by(source="DEPRECIATION").one()
    assert sorted((l.account.code, l.debit_cents, l.credit_cents) for l in entry.lines) == [("28154", 0, 28600), ("6811", 28600, 0)]
    assert client.post(base).status_code == 200  # repassée : une seule écriture
    assert JournalEntry.query.filter_by(source="DEPRECIATION").count() == 1 and AssetDepreciation.query.count() == 1
    # Révision : la durée passe à 3 ans ; la dotation 2026 passée reste, la suite se recalcule.
    assets.save(asset, {**assets.payload(asset), "account_id": asset.account_id, "duration_months": 36})
    db.session.commit()
    rows = assets.schedule(asset)
    assert rows[0].amount_cents == 28600 and rows[0].posted
    assert sum(r.amount_cents for r in rows) == 180000


def test_disposal_sold(books, login_as):
    asset = _asset(in_service_date="2026-01-01", acquired_on="2026-01-01")
    client = login_as()
    resp = client.post(f"/api/v1/assets/{asset.id}/dispose", json={"date": "2026-06-30", "kind": "sold", "price_cents": 150000})
    assert resp.status_code == 200, resp.get_json()
    entry = JournalEntry.query.filter_by(source="ASSET").one()
    # Dotation complémentaire 180 j : 18 000 ; sortie : 28 (18 000) + 675 (162 000) / 2154 (180 000) ; cession 462 / 775.
    assert sorted((l.account.code, l.debit_cents, l.credit_cents) for l in entry.lines) == [
        ("2154", 0, 180000), ("28154", 0, 18000), ("28154", 18000, 0), ("462", 150000, 0), ("6752", 162000, 0),
        ("6811", 18000, 0), ("7752", 0, 150000)]
    assert db.session.get(Asset, asset.id).status == "sold"
    assert assets.depreciation_rows(books) == []


def test_waiting_then_in_service(books, login_as):
    asset = _asset(label="Travaux", account_id=_acc("2313").id, in_service_date=None)
    assert asset.status == "waiting" and assets.schedule(asset) == []
    client = login_as()
    resp = client.post(f"/api/v1/assets/{asset.id}/in-service", json={"date": "2026-07-01", "account_id": _acc("2183").id})
    assert resp.status_code == 200, resp.get_json()
    entry = JournalEntry.query.filter_by(source="ASSET").one()
    assert sorted((l.account.code, l.debit_cents, l.credit_cents) for l in entry.lines) == [("2183", 180000, 0), ("2313", 0, 180000)]
    asset = db.session.get(Asset, asset.id)
    assert asset.status == "in_use" and asset.account.code == "2183" and assets.schedule(asset)[0].days == 180


def test_register_annex_and_api(books, login_as):
    _asset()
    client = login_as()
    listing = client.get("/api/v1/assets").get_json()
    assert listing["items"][0]["net_cents"] == 180000
    (row,) = client.get(f"/api/v1/fiscal-years/{books.id}/assets/annex").get_json()["items"]
    assert row["increases"] == 180000 and row["gross_end"] == 180000
    resp = client.post("/api/v1/assets", json={"label": "", "account_id": _acc("2154").id})
    assert _error(resp, 422)["fields"]["label"]


def test_sci_registry_only(books, login_as):
    org = organization.get()
    org.depreciation_enabled = False
    db.session.commit()
    _asset()
    assert "registre" in _error(login_as().post(f"/api/v1/fiscal-years/{books.id}/closing/depreciation"), 409)["message"]
