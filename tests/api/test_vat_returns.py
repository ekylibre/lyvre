"""Lot T3 : déclaration de TVA mensuelle (CA3) — cases calculées depuis les lignes codées, report du crédit,
liquidation, contrôles, annulation, dépôt et verrouillage, exports (claudedocs/design_societe_tva.md § 3.4-3.5).

Jeu d'essai calculé à la main :
- juillet : vente 1 000 € + 200 € (V20) ; achat 500 € + 100 € (D20) ; ordinateur 1 000 € + 200 € (D20 sur
  44562) ; hébergement étranger 300 € autoliquidé (AL_S, 60 €) ; export 400 € (V_EXP) ; TVA en attente
  sur 44574 (non déclarée). → A1 1 000, A3 300, E1 400, 08 base 1 300 / taxe 260, 19 = 200, 20 = 160,
  23 = 360, crédit 100.
- août : vente 2 001,99 € + 400,40 € ; avoir 100 € + 20 € → 08 base 1 902 / taxe 380, 22 = 100, TD = 280.
"""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, FiscalYear, Journal, JournalEntry, JournalLine, VatReturn
from app.services import vat_return
from app.services.ledger import post_entry
from app.services.ledger_errors import LedgerGuardError

CODES = ("411", "401", "512", "706", "6061", "2183", "44562", "44566", "44571", "44574", "4452", "44551", "44567",
         "658", "758")


def _setup():
    accounts = {code: Account(code=code, label=code, account_type="TIERS") for code in CODES}
    fy = FiscalYear(label="2026-2027", start_date=date(2026, 7, 1), end_date=date(2027, 6, 30), vat_liable=True,
                    vat_period="monthly")
    db.session.add_all([*accounts.values(), fy, Journal(code="OD", label="OD")])
    db.session.commit()
    return {"fy": fy, **accounts}


@pytest.fixture()
def books(app, login_as):
    client = login_as()  # un seul client par test (contexte d'application partagé)
    return {"client": client, **_setup()}


def _entry(books, day, *lines):
    """lines : (compte, débit, crédit[, code, base])."""
    payload = [{"account_id": books[code].id, "label": code, "debit_cents": debit, "credit_cents": credit,
                "vat_code": rest[0] if rest else None, "vat_base_cents": rest[1] if len(rest) > 1 else None}
               for code, debit, credit, *rest in lines]
    entry = post_entry(books["fy"].id, Journal.query.filter_by(code="OD").one().id, day, "essai", payload)
    return entry


def _july(books):
    _entry(books, date(2026, 7, 3), ("411", 120000, 0), ("706", 0, 100000), ("44571", 0, 20000, "V20", 100000))
    _entry(books, date(2026, 7, 8), ("6061", 50000, 0), ("44566", 10000, 0, "D20", 50000), ("401", 0, 60000))
    _entry(books, date(2026, 7, 9), ("2183", 100000, 0), ("44562", 20000, 0, "D20", 100000), ("401", 0, 120000))
    _entry(books, date(2026, 7, 10), ("6061", 30000, 0), ("44566", 6000, 0, "AL_S", 30000),
           ("4452", 0, 6000, "AL_S", 30000), ("401", 0, 30000))
    _entry(books, date(2026, 7, 15), ("411", 40000, 0), ("706", 0, 40000, "V_EXP"))
    _entry(books, date(2026, 7, 20), ("411", 6000, 0), ("706", 0, 5000), ("44574", 0, 1000, "V20", 5000))


def _august(books):
    _entry(books, date(2026, 8, 5), ("411", 240239, 0), ("706", 0, 200199), ("44571", 0, 40040, "V20", 200199))
    _entry(books, date(2026, 8, 12), ("706", 10000, 0), ("44571", 2000, 0, "V20", 10000), ("411", 0, 12000))


def _boxes(rows):
    return {row["line"]: (row["base"], row["amount"]) for row in rows if row["kind"] != "section"}


def test_july_boxes(books):
    _july(books)
    result = vat_return.preview(*vat_return.parse_period("2026-07"))
    boxes = _boxes(result["rows"])
    assert boxes["A1"][1] == 1000 and boxes["A3"][1] == 300 and boxes["E1"][1] == 400
    assert boxes["08"] == (1300, 260) and boxes["16"][1] == 260
    assert boxes["19"][1] == 200 and boxes["20"][1] == 160 and boxes["23"][1] == 360
    assert boxes["25"][1] == 100 and boxes["27"][1] == 100 and boxes["TD"][1] == 0 and boxes["32"][1] == 0
    assert result["credit_cents"] == 10000 and result["due_cents"] == 0


def test_validate_then_carry_the_credit(books):
    _july(books)
    client = books["client"]
    resp = client.post("/api/v1/vat-returns", json={"period": "2026-07"})
    assert resp.status_code == 201, resp.get_json()
    july = VatReturn.query.one()
    assert july.credit_cents == 10000 and july.status == "validated"
    liquidation = sorted((l.account.code, l.debit_cents, l.credit_cents) for l in july.liquidation_entry.lines)
    assert liquidation == sorted([("44562", 0, 20000), ("44566", 0, 16000), ("44567", 10000, 0), ("44571", 20000, 0),
                                  ("4452", 6000, 0)])
    assert july.liquidation_entry.source == "VAT_RETURN"
    # Les écritures du mois sont validées, les lignes rattachées ; la TVA en attente (44574) non.
    # (la liquidation reste en brouillard jusqu'au dépôt : elle s'annule sans contrepassation).
    assert all(e.validation_number for e in JournalEntry.query.filter(JournalEntry.entry_date <= date(2026, 7, 31),
                                                                     JournalEntry.source != "VAT_RETURN"))
    assert july.liquidation_entry.validation_number is None
    assert JournalLine.query.filter(JournalLine.vat_return_id == july.id).count() == 6
    assert JournalLine.query.join(Account).filter(Account.code == "44574").one().vat_return_id is None

    _august(books)
    august = client.get("/api/v1/vat-returns/preview?period=2026-08").get_json()
    boxes = _boxes(august["rows"])
    assert boxes["08"] == (1902, 380) and boxes["22"][1] == 100 and boxes["TD"][1] == 280 and boxes["28"][1] == 280
    assert client.post("/api/v1/vat-returns", json={"period": "2026-08"}).status_code == 201
    aug = VatReturn.query.filter_by(period_start=date(2026, 8, 1)).one()
    lines = sorted((l.account.code, l.debit_cents, l.credit_cents) for l in aug.liquidation_entry.lines)
    # 44571 soldé (40 040 − 2 000), crédit de juillet repris, 280 € dus, 0,40 € d'arrondi en produit.
    assert lines == [("44551", 0, 28000), ("44567", 0, 10000), ("44571", 38040, 0), ("758", 0, 40)]


def test_order_and_cancellation(books):
    _july(books)
    _august(books)
    client = books["client"]
    resp = client.post("/api/v1/vat-returns", json={"period": "2026-08"})
    assert resp.status_code == 409 and "07/2026" in resp.get_json()["error"]["message"]
    assert client.post("/api/v1/vat-returns", json={"period": "2026-07"}).status_code == 201
    assert client.post("/api/v1/vat-returns", json={"period": "2026-07"}).status_code == 409  # déjà validée
    assert client.post("/api/v1/vat-returns", json={"period": "2026-08"}).status_code == 201
    july, august = VatReturn.query.order_by(VatReturn.period_start).all()
    assert client.post(f"/api/v1/vat-returns/{july.id}/unvalidate").status_code == 409  # pas la dernière
    resp = client.post(f"/api/v1/vat-returns/{august.id}/unvalidate")
    assert resp.status_code == 200, resp.get_json()
    assert VatReturn.query.count() == 1
    assert JournalLine.query.filter(JournalLine.vat_return_id.isnot(None)).count() == 6  # juillet seulement


def test_declare_locks_the_month(books):
    _july(books)
    client = books["client"]
    client.post("/api/v1/vat-returns", json={"period": "2026-07"})
    july = VatReturn.query.one()
    assert client.post(f"/api/v1/vat-returns/{july.id}/declare", json={"declared_on": "2026-07-15"}).status_code == 422
    resp = client.post(f"/api/v1/vat-returns/{july.id}/declare", json={"declared_on": "2026-10-28", "reference": "TD-1"})
    assert resp.status_code == 200, resp.get_json()
    assert july.status == "declared" and books["fy"].locked_until == date(2026, 7, 31)
    assert july.liquidation_entry.validation_number is not None
    with pytest.raises(LedgerGuardError):
        _entry(books, date(2026, 7, 20), ("6061", 100, 0), ("401", 0, 100))
    db.session.rollback()
    assert client.post(f"/api/v1/vat-returns/{july.id}/unvalidate").status_code == 409  # déposée


def test_late_piece_goes_to_the_next_month(books):
    _july(books)
    client = books["client"]
    client.post("/api/v1/vat-returns", json={"period": "2026-07"})
    _entry(books, date(2026, 7, 28), ("6061", 10000, 0), ("44566", 2000, 0, "D20", 10000), ("401", 0, 12000))
    august = client.get("/api/v1/vat-returns/preview?period=2026-08").get_json()
    assert _boxes(august["rows"])["20"][1] == 20
    assert any("mois précédents" in c["message"] for c in august["checks"])


def test_checks_and_lines_of_a_box(books):
    _july(books)
    _entry(books, date(2026, 7, 21), ("6061", 10000, 0), ("44566", 2000, 0), ("401", 0, 12000))  # sans code
    _entry(books, date(2026, 7, 22), ("6061", 10000, 0), ("44566", 5000, 0, "D20", 10000), ("401", 0, 15000))
    client = books["client"]
    messages = " ".join(c["message"] for c in client.get("/api/v1/vat-returns/preview?period=2026-07").get_json()["checks"])
    assert "sans code" in messages and "base × taux" in messages and "brouillard" in messages
    lines = client.get("/api/v1/vat-returns/lines?period=2026-07&box=20").get_json()["items"]
    assert sorted(l["debit_cents"] for l in lines) == [5000, 6000, 10000]


def test_months_list_exports_and_fiscal_year_setting(books):
    _july(books)
    client = books["client"]
    body = client.get("/api/v1/vat-returns").get_json()
    assert body["fiscal_year"]["label"] == "2026-2027" and len(body["items"]) == 12
    assert body["items"][0]["period"] == "2026-07" and body["items"][0]["deadline"] == "2026-08-24"
    assert client.get("/vat-returns/2026-07.xlsx").status_code == 200
    pdf = client.get("/vat-returns/2026-07.pdf")
    assert pdf.status_code == 200 and pdf.mimetype == "application/pdf"
    other = FiscalYear(label="2027-2028", start_date=date(2027, 7, 1), end_date=date(2028, 6, 30))
    db.session.add(other)
    db.session.commit()
    assert client.patch(f"/api/v1/fiscal-years/{other.id}", json={"vat_period": "monthly"}).status_code == 422
    assert client.patch(f"/api/v1/fiscal-years/{other.id}", json={"vat_liable": True}).status_code == 200
    assert client.patch(f"/api/v1/fiscal-years/{other.id}", json={"vat_period": "monthly"}).get_json()["item"]["vat_period"] \
        == "monthly"


def test_accountant_reads_but_does_not_validate(app, login_as):
    expert = login_as(role="accountant")
    _july(_setup())
    assert expert.get("/api/v1/vat-returns/preview?period=2026-07").status_code == 200
    assert expert.post("/api/v1/vat-returns", json={"period": "2026-07"}).status_code == 403
