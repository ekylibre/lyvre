"""Lot AG1.d : micro-BA (livre des recettes, récapitulatif N / N-1 / N-2, recettes antérieures), exercice civil,
régularisations de clôture agricoles (conventions 472, MSA à payer) et contrôles de clôture d'une exploitation."""
import json
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, BankAccount, FiscalYear, Instance, SimpleCategory
from app.services import closing, micro_ba, simple_categories, simple_operations
from scripts.agri_fixtures.load import FIXTURES, load
from seed_accounts import load_chart
from test_reports_charts import _post


def _agri(bookkeeping="simple"):
    inst = Instance.query.filter_by(slug="test").one()
    inst.chart, inst.bookkeeping = "agri", bookkeeping
    db.session.add_all([Account(code=a["code"], label=a["label"], account_type=a["account_type"],
                                is_header=a["is_header"]) for a in load_chart("agri")])
    db.session.commit()


def _micro_books(year=2026):
    db.session.add(FiscalYear(label=str(year), start_date=date(year, 1, 1), end_date=date(year, 12, 31)))
    bank = BankAccount(label="Compte", account_id=Account.query.filter_by(code="512").one().id)
    db.session.add(bank)
    db.session.commit()
    simple_categories.ensure_defaults()
    cats = {c.code: c.id for c in SimpleCategory.query}

    def op(day, category, cents, label="Vente"):
        simple_operations.create({"date": day, "label": label, "amount_cents": cents, "category_id": cats[category],
                                  "bank_account_id": bank.id})
    op(f"{year}-03-01", "ventes_vegetaux", 4000, "Marché")
    op(f"{year}-03-01", "ventes_vegetaux", 6000, "Marché")
    op(f"{year}-03-01", "ventes_vegetaux", 50000, "Restaurant")
    op(f"{year}-05-02", "cessions", 120000, "Vente du broyeur")
    op(f"{year}-10-20", "aides_pac", 80000, "Avance PAC")
    op(f"{year}-04-10", "semences", 30000, "Semences")
    return cats


def test_receipts_book_groups_small_sales_and_flags_excluded(app, instance):
    _agri()
    _micro_books()
    book = micro_ba.receipts_book(2026)
    labels = [i["label"] for i in book["items"]]
    assert "Ventes au détail du jour (2)" in labels and "Restaurant" in labels
    grouped = next(i for i in book["items"] if i.get("grouped"))
    assert grouped["amount_cents"] == 10000
    assert book["total"] == {"retained_cents": 140000, "excluded_cents": 120000, "receipts_cents": 260000}
    assert [q["retained_cents"] for q in book["quarters"]] == [60000, 0, 0, 80000]
    ungrouped = micro_ba.receipts_book(2026, group_small=False)
    assert len(ungrouped["items"]) == 5 and ungrouped["grouping_cents"] is None


def test_summary_average_profit_and_carryover(app, instance):
    _agri()
    _micro_books()
    summary = micro_ba.summary(2026)
    assert [y["source"] for y in summary["years"]] == ["lyvre", "missing", "missing"]
    assert summary["average_cents"] == 140000 and summary["profit_cents"] == 30500  # minimum de 305 €
    assert any("inconnues" in w for w in summary["warnings"])
    micro_ba.save_carryover(2025, 2000000)
    micro_ba.save_carryover(2024, 1000000)
    summary = micro_ba.summary(2026)
    assert summary["average_cents"] == round((140000 + 2000000 + 1000000) / 3)
    assert summary["profit_cents"] == round(summary["average_cents"] * 1300 / 10000)
    micro_ba.save_carryover(2025, None)  # retrait de la saisie
    assert micro_ba.retained_receipts(2025)["source"] == "missing"
    with pytest.raises(micro_ba.MicroError):
        micro_ba.save_carryover(2025, -5)


def test_threshold_warning(app, instance):
    _agri()
    _micro_books()
    for year in (2025, 2024):
        micro_ba.save_carryover(year, 30000000)
    assert any("seuil du micro-BA" in w for w in micro_ba.summary(2026)["warnings"])


def test_micro_fixture_totals(app, instance):
    _agri()
    load(FIXTURES / "D_micro_rfa")
    expected = json.loads((FIXTURES / "D_micro_rfa" / "expected.json").read_text("utf-8"))
    book = micro_ba.receipts_book(2025, group_small=False)
    assert book["total"]["retained_cents"] == expected["micro_receipts_cents"]
    assert book["total"]["excluded_cents"] == expected["excluded_cents"]


def test_api_micro(app, login_as):
    client = login_as()
    assert client.get("/api/v1/simple/reports/micro-ba").status_code == 404  # association
    _agri()
    _micro_books()
    body = client.get("/api/v1/simple/reports/receipts-book?year=2026").get_json()
    assert body["total"]["retained_cents"] == 140000 and "year=2026" in body["export_url"]
    xlsx = client.get(body["export_url"])
    assert xlsx.status_code == 200 and xlsx.data[:2] == b"PK"
    saved = client.put("/api/v1/simple/reports/micro-ba/carryover?year=2026", json={"year": 2025, "receipts_cents": 100})
    assert saved.status_code == 200 and saved.get_json()["item"]["years"][1]["source"] == "entered"
    bad = client.put("/api/v1/simple/reports/micro-ba/carryover?year=2026", json={"year": 2025, "receipts_cents": "x"})
    assert bad.status_code == 422


def test_micro_fiscal_year_is_civil(app, login_as):
    client = login_as()
    _agri()
    bad = client.post("/api/v1/fiscal-years", json={"label": "2026-2027", "start_date": "2026-05-01", "end_date": "2027-04-30"})
    assert bad.status_code == 422 and "end_date" in bad.get_json()["error"]["fields"]
    assert client.post("/api/v1/fiscal-years", json={"label": "2027", "start_date": "2027-01-01",
                                                      "end_date": "2027-12-31"}).status_code == 201


# ------------------------------------------------------------------ clôture d'une exploitation au réel

def _fy():
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    db.session.add(fy)
    db.session.commit()
    return fy


def test_compensation_kinds_only_for_farms(app, instance):
    assert "compensation_debit" not in closing.inventory_options()
    _agri("double")
    options = closing.inventory_options()
    assert {"compensation_debit", "compensation_credit"} <= options.keys()
    assert any(c["value"] == "4311" for c in options["accrued_expense"]["counterparts"])


def test_472_check_and_compensation_entry(app, instance):
    _agri("double")
    fy = _fy()
    db.session.add(Account(code="4721", label="Convention CUMA"))
    db.session.commit()
    _post(db.session, fy, [("4721", 50000, 0), ("7041", 0, 50000)])
    db.session.commit()
    keys = {c.key for c in closing.checks(fy)}
    assert "compensation_4721" in keys and "suspense_4721" not in keys
    entry = closing.add_inventory(fy, "compensation_debit", "4721", 50000, "Solde convention")
    lines = {l.account.code: (l.debit_cents, l.credit_cents) for l in entry.lines}
    assert lines == {"412": (50000, 0), "4721": (0, 50000)}
    assert "compensation_4721" not in {c.key for c in closing.checks(fy)}


def test_living_asset_disposal_check(app, instance):
    _agri("double")
    fy = _fy()
    _post(db.session, fy, [("241", 0, 100000), ("675", 100000, 0)])  # sortie hors 6571 / 7571
    db.session.commit()
    checks = {c.key: c for c in closing.checks(fy)}
    assert "living_disposal" in checks
    _post(db.session, fy, [("6571", 100000, 0), ("675", 0, 100000)])
    db.session.commit()
    assert "living_disposal" not in {c.key for c in closing.checks(fy)}


def test_living_assets_without_register(app, instance):
    _agri("double")
    fy = _fy()
    _post(db.session, fy, [("241", 300000, 0), ("512", 0, 300000)])
    db.session.commit()
    assert "living_register" in {c.key for c in closing.checks(fy)}


def test_exit_from_micro_warns(app, login_as):
    admin = login_as(is_admin=True)
    _agri("simple")
    inst = Instance.query.filter_by(slug="test").one()
    body = admin.patch(f"/api/v1/instances/{inst.id}", json={"label": inst.label, "bookkeeping": "double"}).get_json()
    assert any("72 E bis" in n["message"] for n in body["notices"])
