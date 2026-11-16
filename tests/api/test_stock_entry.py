"""Lot AG4.d : écriture de stock à la clôture (design_inventaire_agricole.md § 8, AGD21 Q-S1).

Recettes du design (§ 13) :
- engrais : stock initial 6 692,66 €, stock final 4 000 € → D 6031 / C 31111 6 692,66 puis D 31111 / C 6031 4 000 ;
- dossier fictif A : sans son journal KF, la saisie des stocks finaux redonne les soldes des comptes de stock.
"""
from datetime import date

import pytest
from sqlalchemy import func

from app.extensions import db
from app.models import Account, FiscalYear, Journal, JournalEntry, JournalLine, StockLine
from app.models.journal_entry import SOURCE_OPENING, SOURCE_STOCK
from app.services import closing, stock_entry
from app.services.ledger import post_entry
from test_agri_fixtures import _agri_instance


def _id(code):
    return Account.query.filter_by(code=code).one().id


@pytest.fixture()
def farm(app, login_as):
    client = login_as(role="admin")
    _agri_instance()
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    an = Journal(code="AN", label="À-nouveaux")
    db.session.add_all([fy, an])
    db.session.commit()
    post_entry(fy.id, an.id, date(2026, 1, 1), "À-nouveaux", [
        {"account_id": _id("31111"), "label": "Engrais", "debit_cents": 669266, "credit_cents": 0},
        {"account_id": _id("3113"), "label": "Porcelets", "debit_cents": 150000, "credit_cents": 0},
        {"account_id": _id("391"), "label": "Dépréciation", "debit_cents": 0, "credit_cents": 50000},
        {"account_id": _id("110"), "label": "Report", "debit_cents": 0, "credit_cents": 769266}], source=SOURCE_OPENING)
    return {"client": client, "fy": fy, "url": f"/api/v1/fiscal-years/{fy.id}/stock"}


def _line(farm, **data):
    resp = farm["client"].post(f"{farm['url']}/lines", json=data)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


def _balance(fy, code):
    return int(db.session.query(func.coalesce(func.sum(JournalLine.debit_cents - JournalLine.credit_cents), 0))
               .join(JournalEntry).filter(JournalEntry.fiscal_year_id == fy.id, JournalLine.account_id == _id(code)).scalar())


def _keys(fy):
    return {c.key: c for c in closing._agri_checks(fy)}


def test_cancel_opening_and_record_final(farm):
    client, fy = farm["client"], farm["fy"]
    assert _keys(fy)["stock_forgotten"].severity == "anomaly"
    _line(farm, account_code="31111", label="Engrais", quantity="1", method="actual", unit_value_cents=400000,
          depreciation_cents=30000, depreciation_reason="produit périmé")
    checks = _keys(fy)
    assert checks["stock_entry"].severity == "anomaly" and "3113" in checks["stock_uncounted"].label
    resp = client.post(f"{farm['url']}/entry")
    assert resp.status_code == 200, resp.get_json()
    entry = stock_entry.entry(fy)
    lines = {(l.account.code, l.debit_cents, l.credit_cents) for l in entry.lines}
    assert {("6031", 669266, 0), ("31111", 0, 669266), ("31111", 400000, 0), ("6031", 0, 400000)} <= lines
    assert {("713552", 150000, 0), ("3113", 0, 150000)} <= lines                       # stock non compté : ramené à 0
    assert {("391", 50000, 0), ("78173", 0, 50000), ("68173", 30000, 0), ("391", 0, 30000)} <= lines
    assert entry.entry_date == date(2026, 12, 31) and entry.source == SOURCE_STOCK
    assert _balance(fy, "31111") == 400000 and _balance(fy, "3113") == 0 and _balance(fy, "391") == -30000
    status = resp.get_json()["entry"]
    assert status["stale"] is False and status["final_cents"] == 400000 and status["variation_cents"] == -419266
    assert not {"stock_entry", "stock_forgotten", "stock_stale"} & set(_keys(fy))
    line = StockLine.query.one()
    client.put(f"{farm['url']}/lines/{line.id}", json={"unit_value_cents": 410000})
    assert _keys(fy)["stock_stale"].severity == "anomaly"
    client.post(f"{farm['url']}/entry")                                                  # repassée
    assert JournalEntry.query.filter_by(source=SOURCE_STOCK).count() == 1 and _balance(fy, "31111") == 410000
    assert "stock_stale" not in _keys(fy)
    assert client.delete(f"{farm['url']}/entry").status_code == 200 and stock_entry.entry(fy) is None
    assert _balance(fy, "31111") == 669266


def test_incomplete_inventory_blocks(farm):
    _line(farm, account_code="35511", label="Blé", quantity="10", unit="t", method="retail", market_price_cents=20000)
    resp = farm["client"].post(f"{farm['url']}/entry")
    assert resp.status_code == 422 and "Décote" not in resp.get_json()["error"]["message"]
    assert "valeur à compléter" in resp.get_json()["error"]["message"]
    assert _keys(farm["fy"])["stock_warnings"].count == 1


def test_frozen_and_export(farm):
    client, fy = farm["client"], farm["fy"]
    _line(farm, account_code="31111", label="Engrais", quantity="2", method="actual", unit_value_cents=100000)
    client.post(f"{farm['url']}/entry")
    xlsx = client.get(f"/fiscal-years/{fy.id}/stock.xlsx")
    assert xlsx.status_code == 200 and xlsx.data[:2] == b"PK"
    fy.status = "closed"
    db.session.commit()
    assert client.post(f"{farm['url']}/entry").status_code == 409
    assert client.delete(f"{farm['url']}/entry").status_code == 409


def test_fixture_farm_a_recette(app, login_as):
    """Dossier fictif A (clôture au 31/01/2025) : stocks finaux saisis → mêmes soldes que le journal KF."""
    from scripts.agri_fixtures.load import FIXTURES, load

    client = login_as(role="admin")
    _agri_instance()
    load(FIXTURES / "A_earl_porcs_rs")
    fy = FiscalYear.query.filter(FiscalYear.end_date == date(2025, 1, 31)).one()
    codes = ("31111", "31114", "31115", "3113", "31", "35511", "35513")
    expected = {code: _balance(fy, code) for code in codes}
    kf = JournalEntry.query.filter(JournalEntry.fiscal_year_id == fy.id, JournalEntry.source_ref.like("KF%")).all()
    assert kf, "journal KF du jeu d'essai"
    ids = [e.id for e in kf]                     # écritures validées du jeu d'essai : retirées en SQL pour la recette
    db.session.execute(db.delete(JournalLine).where(JournalLine.entry_id.in_(ids)))
    db.session.execute(db.delete(JournalEntry).where(JournalEntry.id.in_(ids)))
    fy.status = "open"                           # exercice du jeu d'essai clôturé : rouvert pour la recette
    db.session.commit()
    db.session.expire_all()
    for code, cents in expected.items():
        if cents:
            resp = client.post(f"/api/v1/fiscal-years/{fy.id}/stock/lines",
                               json={"account_code": code, "label": f"Stock {code}", "quantity": "1", "method": "actual",
                                     "unit_value_cents": cents})
            assert resp.status_code == 201, resp.get_json()
    resp = client.post(f"/api/v1/fiscal-years/{fy.id}/stock/entry")
    assert resp.status_code == 200, resp.get_json()
    assert {code: _balance(fy, code) for code in codes} == expected
