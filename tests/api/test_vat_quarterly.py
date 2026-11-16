"""Lot AG2.a : calendrier des jours ouvrés, CA3 trimestrielle (RSA sur option), remboursement de crédit (3519)."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, FiscalYear, Journal, VatReturn
from app.services import fr_calendar, vat_return
from app.services.ledger import post_entry

CODES = ("411", "401", "512", "706", "6061", "2154", "44562", "44566", "44571", "44551", "44567", "44583", "658", "758")


@pytest.mark.parametrize("year,expected", [(2026, date(2026, 5, 5)), (2027, date(2027, 5, 4)), (2025, date(2025, 5, 5))])
def test_second_working_day_after_may_first(year, expected):
    assert fr_calendar.nth_working_day_after(date(year, 5, 1), 2) == expected


def test_holidays_and_postponement():
    assert fr_calendar.easter(2027) == date(2027, 3, 28)
    assert date(2027, 5, 17) in fr_calendar.holidays(2027)  # lundi de Pentecôte
    assert fr_calendar.next_working_day(date(2027, 5, 15)) == date(2027, 5, 18)  # samedi → mardi
    assert fr_calendar.next_working_day(date(2026, 11, 5)) == date(2026, 11, 5)
    assert fr_calendar.next_working_day(date(2027, 2, 6)) == date(2027, 2, 8)


@pytest.mark.parametrize("text,start,end", [("2026-T3", date(2026, 7, 1), date(2026, 9, 30)),
                                            ("2026-t4", date(2026, 10, 1), date(2026, 12, 31)),
                                            ("2026-07", date(2026, 7, 1), date(2026, 7, 31))])
def test_parse_period(text, start, end):
    assert vat_return.parse_period(text) == (start, end)


def test_parse_period_invalid():
    with pytest.raises(vat_return.VatReturnError):
        vat_return.parse_period("2026-T5")


def _setup(period="quarterly"):
    accounts = {code: Account(code=code, label=code, account_type="TIERS") for code in CODES}
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), vat_liable=True,
                    vat_period=period)
    db.session.add_all([*accounts.values(), fy, Journal(code="OD", label="OD")])
    db.session.commit()
    return {"fy": fy, **accounts}


@pytest.fixture()
def books(app, login_as):
    client = login_as()
    return {"client": client, **_setup()}


def _entry(books, day, *lines):
    payload = [{"account_id": books[code].id, "label": code, "debit_cents": debit, "credit_cents": credit,
                "vat_code": rest[0] if rest else None, "vat_base_cents": rest[1] if len(rest) > 1 else None}
               for code, debit, credit, *rest in lines]
    return post_entry(books["fy"].id, Journal.query.filter_by(code="OD").one().id, day, "essai", payload)


def test_quarters_and_deadlines(books):
    body = books["client"].get("/api/v1/vat-returns").get_json()
    assert [r["period"] for r in body["items"]] == ["2026-T1", "2026-T2", "2026-T3", "2026-T4"]
    assert [r["label"] for r in body["items"]][2] == "T3 2026"
    deadlines = [r["deadline"] for r in body["items"]]
    assert deadlines == ["2026-05-05", "2026-08-05", "2026-11-05", "2027-02-05"]
    assert body["fiscal_year"]["vat_period"] == "quarterly"


def test_quarter_return_and_credit_carried(books):
    # T1 : investissement 10 000 € + 2 000 € de TVA, vente 1 000 € + 200 € : crédit 1 800 €.
    _entry(books, date(2026, 2, 10), ("2154", 1000000, 0), ("44562", 200000, 0, "D20", 1000000), ("401", 0, 1200000))
    _entry(books, date(2026, 3, 5), ("411", 120000, 0), ("706", 0, 100000), ("44571", 0, 20000, "V20", 100000))
    client = books["client"]
    preview = client.get("/api/v1/vat-returns/preview?period=2026-T1").get_json()
    assert preview["label"] == "T1 2026" and preview["credit_cents"] == 180000
    assert preview["refund"] == {"minimum_cents": 76000, "maximum_cents": 180000, "possible": True}
    created = client.post("/api/v1/vat-returns", json={"period": "2026-T1"})
    assert created.status_code == 201, created.get_json()
    # T2 : rien ; crédit reporté depuis T1 (case 22).
    t2 = client.get("/api/v1/vat-returns/preview?period=2026-T2").get_json()
    assert t2["credit_carried_cents"] == 180000
    # T3 validé avant T2 : refusé.
    bad = client.post("/api/v1/vat-returns", json={"period": "2026-T3"})
    assert bad.status_code == 409 and "T2 2026" in bad.get_json()["error"]["message"]


def test_refund_request(books):
    _entry(books, date(2026, 2, 10), ("2154", 1000000, 0), ("44562", 200000, 0, "D20", 1000000), ("401", 0, 1200000))
    client = books["client"]
    too_small = client.post("/api/v1/vat-returns", json={"period": "2026-T1", "refund_cents": 50000})
    assert too_small.status_code == 422 and "760" in too_small.get_json()["error"]["message"]
    too_big = client.post("/api/v1/vat-returns", json={"period": "2026-T1", "refund_cents": 300000})
    assert too_big.status_code == 422
    ok = client.post("/api/v1/vat-returns", json={"period": "2026-T1", "refund_cents": 150000})
    assert ok.status_code == 201, ok.get_json()
    assert "3519" in ok.get_json()["notices"][0]["message"]
    ret = VatReturn.query.one()
    assert (ret.refund_cents, ret.credit_cents) == (150000, 50000)
    assert ret.detail["boxes"]["26"] == {"amount": 1500} and ret.detail["boxes"]["27"] == {"amount": 500}
    lines = {l.account.code: (l.debit_cents, l.credit_cents) for l in ret.liquidation_entry.lines}
    assert lines["44583"] == (150000, 0) and lines["44567"] == (50000, 0) and lines["44562"] == (0, 200000)
    assert client.get("/api/v1/vat-returns/preview?period=2026-T2").get_json()["credit_carried_cents"] == 50000


def test_annual_refund_threshold_on_last_quarter(app, instance):
    assert vat_return.refund_problem(date(2026, 10, 1), date(2026, 12, 31), 20000, 50000) is None  # 150 € suffisent
    assert "760" in vat_return.refund_problem(date(2026, 7, 1), date(2026, 9, 30), 20000, 50000)
    assert vat_return.refund_problem(date(2026, 10, 1), date(2026, 12, 31), 10000, 50000) is not None


def test_period_change_refused_once_returns_exist(books):
    client = books["client"]
    assert client.post("/api/v1/vat-returns", json={"period": "2026-T1"}).status_code == 201
    fy = books["fy"]
    resp = client.patch(f"/api/v1/fiscal-years/{fy.id}/vat", json={"vat_period": "monthly"})
    if resp.status_code == 404:  # route de réglage de l'exercice
        resp = client.patch(f"/api/v1/fiscal-years/{fy.id}", json={"vat_period": "monthly"})
    assert resp.status_code == 422 and "rythme" in resp.get_json()["error"]["message"]
