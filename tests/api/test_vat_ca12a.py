"""Lot AG2.b : déclaration annuelle CA12A / CA12AE du régime simplifié agricole (3517-AGR-SD 2026).

Jeu calculé à la main (année civile 2026) :
- ventes : 1 000 € à 20 % (200), 5 000 € à 10 % (500), 10 000 € à 5,5 % (550) ; export 2 000 € ;
- achats : engrais 3 000 € + 600 (44566), tracteur 20 000 € + 4 000 (44562), service étranger 300 € autoliquidé (60) ;
- crédit d'ouverture 44567 : 100 €.
→ 15 = 1 310 ; 17 = 4 000 ; 18 = 660 ; 19 = 100 ; 21 = 4 760 ; 24 = 3 450 ; 30 = 36 = 3 450 ; 42 = 44 = 3 450.
"""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, FiscalYear, Instance, Journal, JournalEntry, TaxOption, VatReturn
from app.models.journal_entry import SOURCE_OPENING
from app.services import vat_return
from app.services.ledger import post_entry

CODES = ("411", "401", "512", "7011", "7012", "7013", "60111", "6226", "2154", "44562", "44566", "44571", "44551",
         "44567", "44581", "44583", "4452", "658", "758", "110")


def _setup(start=date(2026, 1, 1), end=date(2026, 12, 31)):
    Instance.query.filter_by(slug="test").one().chart = "agri"
    accounts = {code: Account(code=code, label=code, account_type="TIERS") for code in CODES}
    fy = FiscalYear(label="2026", start_date=start, end_date=end, vat_liable=True, vat_period="annual")
    db.session.add_all([*accounts.values(), fy, Journal(code="OD", label="OD"), Journal(code="AN", label="AN")])
    db.session.commit()
    return {"fy": fy, **accounts}


@pytest.fixture()
def books(app, login_as):
    client = login_as()
    return {"client": client, **_setup()}


def _entry(books, day, *lines, journal="OD", source=None):
    payload = [{"account_id": books[code].id, "label": code, "debit_cents": debit, "credit_cents": credit,
                "vat_code": rest[0] if rest else None, "vat_base_cents": rest[1] if len(rest) > 1 else None}
               for code, debit, credit, *rest in lines]
    kwargs = {"source": source} if source else {}
    return post_entry(books["fy"].id, Journal.query.filter_by(code=journal).one().id, day, "essai", payload, **kwargs)


def _year(books):
    _entry(books, date(2026, 1, 1), ("44567", 10000, 0), ("110", 0, 10000), journal="AN", source=SOURCE_OPENING)
    _entry(books, date(2026, 3, 2), ("411", 120000, 0), ("7013", 0, 100000), ("44571", 0, 20000, "V20", 100000))
    _entry(books, date(2026, 4, 2), ("411", 550000, 0), ("7012", 0, 500000), ("44571", 0, 50000, "V10", 500000))
    _entry(books, date(2026, 5, 2), ("411", 1055000, 0), ("7011", 0, 1000000), ("44571", 0, 55000, "V55", 1000000))
    _entry(books, date(2026, 6, 2), ("411", 200000, 0), ("7011", 0, 200000, "V_EXP"))
    _entry(books, date(2026, 2, 10), ("60111", 300000, 0), ("44566", 60000, 0, "D20", 300000), ("401", 0, 360000))
    _entry(books, date(2026, 2, 20), ("2154", 2000000, 0), ("44562", 400000, 0, "D20", 2000000), ("401", 0, 2400000))
    _entry(books, date(2026, 7, 1), ("6226", 30000, 0), ("44566", 6000, 0, "AL_S", 30000),
           ("4452", 0, 6000, "AL_S", 30000), ("401", 0, 30000))


def _boxes(rows):
    return {r["line"]: (r.get("base"), r["amount"]) for r in rows if r["kind"] != "section"}


def test_annual_period_key_label_and_deadline(books):
    body = books["client"].get("/api/v1/vat-returns").get_json()
    assert [(r["period"], r["label"], r["deadline"]) for r in body["items"]] == [("2026-A", "2026", "2027-05-04")]
    assert vat_return.parse_period("2026-A") == (date(2026, 1, 1), date(2026, 12, 31))


def test_ca12a_lines(books):
    _year(books)
    preview = books["client"].get("/api/v1/vat-returns/preview?period=2026-A").get_json()
    assert preview["form"] == "3517-AGR-SD" and preview["form_code"] == "CA12A"
    b = _boxes(preview["rows"])
    assert b["04"] == (1000, 200) and b["5A"] == (5000, 500) and b["5C"] == (10000, 550)
    assert b["9C"] == (300, 60) and b["01"] == (None, 2000)
    assert b["15"][1] == 1310 and b["17"][1] == 4000 and b["18"][1] == 660 and b["19"][1] == 100
    assert b["21"][1] == 4760 and b["23"][1] == 0 and b["24"][1] == 3450
    assert b["30"][1] == 3450 and b["36"][1] == 3450 and b["42"][1] == 3450 and b["44"][1] == 3450
    assert preview["refund"] == {"minimum_cents": 100, "maximum_cents": 345000, "possible": True}


def test_ca12a_validation_with_refund_and_liquidation(books):
    _year(books)
    client = books["client"]
    too_big = client.post("/api/v1/vat-returns", json={"period": "2026-A", "refund_cents": 400000})
    assert too_big.status_code == 422
    resp = client.post("/api/v1/vat-returns", json={"period": "2026-A", "refund_cents": 300000, "tca_euros": 42})
    assert resp.status_code == 201, resp.get_json()
    ret = VatReturn.query.one()
    assert ret.form == "CA12A" and (ret.refund_cents, ret.credit_cents, ret.due_cents) == (300000, 45000, 0)
    boxes = ret.detail["boxes"]
    assert boxes["37"] == {"amount": 3000} and boxes["38"] == {"amount": 450} and boxes["46"] == {"amount": 450}
    assert boxes["31"] == {"amount": 42} and boxes["41"] == {"amount": 42}
    entry = ret.liquidation_entry
    assert sum(l.debit_cents for l in entry.lines) == sum(l.credit_cents for l in entry.lines)
    by_code = {}
    for line in entry.lines:
        d, c = by_code.get(line.account.code, (0, 0))
        by_code[line.account.code] = (d + line.debit_cents, c + line.credit_cents)
    assert by_code["44583"] == (300000, 0) and by_code["44567"][0] - by_code["44567"][1] == 45000 - 10000
    assert not any(code in by_code for code in ("658", "758"))  # pas d'écart d'arrondi


def test_ca12a_due_with_installments(books):
    _entry(books, date(2026, 3, 2), ("411", 1200000, 0), ("7013", 0, 1000000), ("44571", 0, 200000, "V20", 1000000))
    fy = books["fy"]
    for start, end, cents in ((date(2026, 4, 1), date(2026, 6, 30), 40000), (date(2026, 7, 1), date(2026, 9, 30), 40000)):
        db.session.add(VatReturn(fiscal_year_id=fy.id, period_start=start, period_end=end, form="ACOMPTE",
                                 boxes_json="{}", due_cents=cents))
    db.session.commit()
    preview = books["client"].get("/api/v1/vat-returns/preview?period=2026-A").get_json()
    b = _boxes(preview["rows"])
    assert b["23"][1] == 2000 and b["25"][1] == 800 and b["28"][1] == 1200 and b["29"][1] == 0 and b["39"][1] == 1200
    assert preview["installments_cents"] == 80000
    assert books["client"].post("/api/v1/vat-returns", json={"period": "2026-A"}).status_code == 201
    entry = VatReturn.query.filter_by(form="CA12A").one().liquidation_entry
    lines = {l.account.code: (l.debit_cents, l.credit_cents) for l in entry.lines}
    assert lines["44581"] == (0, 80000) and lines["44551"] == (0, 120000) and lines["44571"] == (200000, 0)


def test_excess_of_installments_is_refundable_without_minimum(books):
    _entry(books, date(2026, 3, 2), ("411", 12000, 0), ("7013", 0, 10000), ("44571", 0, 2000, "V20", 10000))
    db.session.add(VatReturn(fiscal_year_id=books["fy"].id, period_start=date(2026, 4, 1), period_end=date(2026, 6, 30),
                             form="ACOMPTE", boxes_json="{}", due_cents=10000))
    db.session.commit()
    preview = books["client"].get("/api/v1/vat-returns/preview?period=2026-A").get_json()
    b = _boxes(preview["rows"])
    assert b["23"][1] == 20 and b["29"][1] == 80 and b["30"][1] == 80 and b["43"][1] == 80 and b["44"][1] == 80
    assert any("4/5" in c["message"] for c in preview["checks"])


def test_ca12ae_on_fiscal_year(app, login_as):
    client = login_as()
    books = {"client": client, **_setup(date(2025, 7, 1), date(2026, 6, 30))}
    db.session.add(TaxOption(code="rsa_fiscal_year", start_date=date(2025, 7, 1)))
    db.session.commit()
    items = client.get("/api/v1/vat-returns").get_json()["items"]
    assert [(r["period"], r["label"], r["deadline"]) for r in items] == [
        ("2025-07-A", "exercice 2025-2026", "2026-11-05")]
    assert vat_return.parse_period("2025-07-A") == (date(2025, 7, 1), date(2026, 6, 30))


def test_annual_only_for_farms(app, login_as):
    client = login_as(role="admin")
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), vat_liable=True)
    db.session.add(fy)
    db.session.commit()
    resp = client.patch(f"/api/v1/fiscal-years/{fy.id}", json={"vat_period": "annual"})
    assert resp.status_code == 422 and "agricole" in resp.get_json()["error"]["message"]
    Instance.query.filter_by(slug="test").one().chart = "agri"
    db.session.commit()
    assert client.patch(f"/api/v1/fiscal-years/{fy.id}", json={"vat_period": "annual"}).status_code == 200


def test_setup_hint_without_declaring_year(app, login_as):
    """Essai de l'interface (09/11/2026) : sans exercice déclarant, la page TVA d'une exploitation part du profil fiscal."""
    from app.models import Instance, TaxProfile
    client = login_as(role="admin")
    Instance.query.filter_by(slug="test").one().chart = "agri"
    db.session.commit()
    body = client.get("/api/v1/vat-returns").get_json()
    assert body["fiscal_year"] is None and "Régime de TVA non renseigné" in body["setup"]["message"]
    assert body["setup"]["link"] == "/configuration/organization?tab=tax"
    import json
    assert '"vat_returns"' in json.dumps(client.get("/api/v1/session").get_json()["nav"])   # menu visible
    db.session.add(TaxProfile(kind="vat_regime", value="rsa_installments", start_date=date(2020, 1, 1)))
    db.session.commit()
    setup = client.get("/api/v1/vat-returns").get_json()["setup"]
    assert "période annuelle (CA12A et acomptes)" in setup["message"] and setup["link"] == "/fiscal-years/"


def test_offset_year_annual_deadlines(app):
    """Essai de l'interface (09/11/2026) : exercice 01/02/2024–31/01/2025 au rythme annuel ; l'année civile 2025 finit
    hors de tout exercice et gardait l'échéance mensuelle (24/01/2026) au lieu du 2e jour ouvré après le 1er mai."""
    from app.services import fr_calendar
    fy = FiscalYear(label="2024-2025", start_date=date(2024, 2, 1), end_date=date(2025, 1, 31), vat_liable=True,
                    vat_period="annual")
    db.session.add(fy)
    db.session.commit()
    rows = vat_return.periods(fy, today=date(2026, 11, 9))
    assert [r["period"] for r in rows] == ["2024-A", "2025-A"]
    assert [r["deadline"] for r in rows] == [fr_calendar.nth_working_day_after(date(2025, 5, 1), 2),
                                             fr_calendar.nth_working_day_after(date(2026, 5, 1), 2)]
    assert vat_return.period_kind(date(2024, 1, 1), date(2024, 12, 31)) == "annual"
    # L'année civile 2024 commence avant l'exercice : CA12A et acomptes tout de même.
    assert vat_return.form_for(date(2024, 1, 1)) == vat_return.CA12A
    from app.services import vat_installments
    assert vat_installments.schedule((date(2024, 1, 1), date(2024, 12, 31)))
    assert vat_return.period_fiscal_year(date(2024, 1, 1)).id == fy.id
