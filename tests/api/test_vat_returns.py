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

CODES = ("411", "401", "512", "706", "6061", "2183", "44562", "44566", "44571", "44574", "4452", "4453", "44551",
         "44567", "658", "758")


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


def test_reverse_charge_notes(books):
    """Autoliquidation (AL_S) : mention sous les lignes 08 et 20, la TVA due et déduite s'annulent."""
    _july(books)
    rows = {r["line"]: r for r in vat_return.preview(*vat_return.parse_period("2026-07"))["rows"] if r["kind"] != "section"}
    assert rows["08"]["note"] == "dont 60,00 € de TVA autoliquidée, déduite ligne 20"
    assert rows["20"]["note"].startswith("dont 60,00 € de TVA autoliquidée, due ligne 08")
    assert "note" not in rows["19"] and "note" not in rows["A1"]


def test_imports_and_article_283_1(books):
    """Importation 1 000 € à 20 % et 200 € à 5,5 % : A4 et I1 / I4, déduction en 20 dont 24 ; achat art. 283-1
    500 € : B4 et 08. Pas de ligne 17 (réservée aux acquisitions intracommunautaires)."""
    _entry(books, date(2026, 7, 4), ("6061", 100000, 0), ("44566", 20000, 0, "AL_I", 100000),
           ("4453", 0, 20000, "AL_I", 100000), ("401", 0, 100000))
    _entry(books, date(2026, 7, 5), ("6061", 20000, 0), ("44566", 1100, 0, "AL_I55", 20000),
           ("4453", 0, 1100, "AL_I55", 20000), ("401", 0, 20000))
    _entry(books, date(2026, 7, 6), ("6061", 50000, 0), ("44566", 10000, 0, "AL_FR", 50000),
           ("4452", 0, 10000, "AL_FR", 50000), ("401", 0, 50000))
    result = vat_return.preview(*vat_return.parse_period("2026-07"))
    boxes = _boxes(result["rows"])
    assert boxes["A4"][1] == 1200 and boxes["I1"] == (1000, 200) and boxes["I4"] == (200, 11)
    assert boxes["B4"][1] == 500 and boxes["08"] == (500, 100) and boxes["17"][1] == 0
    assert boxes["16"][1] == 311 and boxes["20"][1] == 311 and boxes["24"][1] == 211 and boxes["23"][1] == 311
    assert boxes["TD"][1] == 0 and boxes["25"][1] == 0
    assert any("douane" in c["message"] for c in result["checks"])
    assert {l.vat_code for l in vat_return.lines_for(date(2026, 7, 1), date(2026, 7, 31), "24")} == {"AL_I", "AL_I55"}
    ret = vat_return.validate(*vat_return.parse_period("2026-07"))
    entry = db.session.get(JournalEntry, ret.liquidation_entry_id)
    assert sum(l.debit_cents for l in entry.lines if l.account.code == "4453") == 21100


def test_supplier_credit_note_goes_to_line_15(books):
    """Avoir reçu d'un fournisseur : TVA déduite à reverser ligne 15 (incluse dans 16), la ligne 20 n'est pas réduite."""
    from app.models import Entity, Purchase
    _entry(books, date(2026, 7, 8), ("6061", 50000, 0), ("44566", 10000, 0, "D20", 50000), ("401", 0, 60000))
    note = _entry(books, date(2026, 7, 12), ("401", 12000, 0), ("6061", 0, 10000), ("44566", 0, 2000, "D20", 10000))
    supplier = Entity(name="Fournisseur", entity_type="FOURNISSEUR")
    db.session.add(supplier)
    db.session.flush()
    db.session.add(Purchase(entity_id=supplier.id, is_credit_note=True, journal_entry_id=note.id, invoice_number="AV1",
                            issue_date=date(2026, 7, 12), total_cents=12000, untaxed_cents=10000, tax_cents=2000))
    db.session.commit()
    boxes = _boxes(vat_return.preview(*vat_return.parse_period("2026-07"))["rows"])
    assert boxes["15"][1] == 20 and boxes["16"][1] == 20 and boxes["20"][1] == 100 and boxes["TD"][1] == 0
    assert boxes["25"][1] == 80
    assert [l.entry_id for l in vat_return.lines_for(date(2026, 7, 1), date(2026, 7, 31), "15")] == [note.id]


def test_uncoded_vat_lines_block_validation(books):
    """Essai de l'interface (09/11/2026) : taxe sans code bloquante (reprise FEC « néant ») ; crédit 44567 : avertissement."""
    _july(books)
    _entry(books, date(2026, 7, 21), ("6061", 10000, 0), ("44566", 2000, 0), ("401", 0, 12000))  # sans code
    client = books["client"]
    checks = client.get("/api/v1/vat-returns/preview?period=2026-07").get_json()["checks"]
    (uncoded,) = [c for c in checks if c["key"] == "uncoded"]
    assert uncoded["level"] == "error" and uncoded["count"] == 1
    response = client.post("/api/v1/vat-returns", json={"period": "2026-07"})
    assert response.status_code >= 400 and "sans code" in response.get_json()["error"]["message"]
