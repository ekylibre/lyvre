"""Lot AG2.d : livres de TVA du régime simplifié agricole et contrôle croisé avec la CA12A.

Jeu de tests/api/test_vat_ca12a.py (année civile 2026), plus un achat sans TVA déductible (assurance 500 €) :
ventes 01 = 2 000 ; 04 = 1 000 / 200 ; 5A = 5 000 / 500 ; 5C = 10 000 / 550 ;
achats : immobilisations 20 000 HT / 4 000 (ligne 17) ; autres 3 000 + 300 + 500 HT / 600 + 60 (ligne 18).
"""
from datetime import date

import pytest

from app.models import VatReturn
from test_vat_ca12a import _entry, _setup, _year


@pytest.fixture()
def books(app, login_as):
    client = login_as()
    data = {"client": client, **_setup()}
    _year(data)
    _entry(data, date(2026, 8, 3), ("6226", 50000, 0), ("401", 0, 50000))  # assurance : pas de TVA déductible
    return data


def test_sales_book_totals_equal_ca12a_lines(books):
    body = books["client"].get("/api/v1/vat-books/sales?period=2026-A").get_json()
    totals = {t["line"]: (t["base_cents"], t["tax_cents"]) for t in body["totals"]}
    assert totals["01"] == (200000, 0) and totals["04"] == (100000, 20000)
    assert totals["5A"] == (500000, 50000) and totals["5C"] == (1000000, 55000)
    assert len(body["items"]) == 4 and {i["category"] for i in body["items"]} >= {"Exportations hors UE", "Taxables à 20 %"}
    assert body["control"]["ok"] is True and body["control"]["validated"] is False


def test_purchases_book_lists_non_deductible_purchases(books):
    body = books["client"].get("/api/v1/vat-books/purchases?period=2026-A").get_json()
    insurance = [i for i in body["items"] if i["ht_cents"] == 50000]
    assert len(insurance) == 1 and insurance[0]["non_deductible"] is True and insurance[0]["group"] == "other"
    totals = {t["group"]: t for t in body["totals"]}
    assert (totals["assets"]["ht_cents"], totals["assets"]["deductible_cents"]) == (2000000, 400000)
    assert (totals["other"]["ht_cents"], totals["other"]["deductible_cents"]) == (380000, 66000)
    assert totals["other"]["reverse_charge_cents"] == 6000 and totals["other"]["non_deductible_ht_cents"] == 50000
    control = body["control"]
    assert (control["book_total"], control["return_total"], control["ok"]) == (4660, 4660, True)


def test_control_after_validation_and_gap_on_uncoded_vat(books):
    client = books["client"]
    assert client.post("/api/v1/vat-returns", json={"period": "2026-A"}).status_code == 201
    assert VatReturn.query.filter_by(form="CA12A").count() == 1
    _entry(books, date(2026, 9, 1), ("60111", 10000, 0), ("44566", 2000, 0), ("401", 0, 12000))  # TVA sans code
    body = client.get("/api/v1/vat-books/purchases?period=2026-A").get_json()
    assert body["control"]["validated"] is True and body["control"]["ok"] is False
    assert body["control"]["book_total"] - body["control"]["return_total"] == 20
    assert client.get("/api/v1/vat-books/sales?period=2026-A").get_json()["control"]["ok"] is True


def test_free_period_has_no_control_and_bad_dates(books):
    client = books["client"]
    body = client.get("/api/v1/vat-books/sales?start=2026-04-01&end=2026-06-30").get_json()
    assert body["control"] is None and {i["code"] for i in body["items"]} == {"V10", "V55", "V_EXP"}
    assert client.get("/api/v1/vat-books/sales?start=2026-06-30&end=2026-04-01").status_code == 422
    assert client.get("/api/v1/vat-books/purchases").status_code == 200   # période par défaut


def test_exports(books):
    client = books["client"]
    for kind in ("sales", "purchases"):
        xlsx = client.get(f"/vat-books/{kind}.xlsx?period=2026-A")
        assert xlsx.status_code == 200 and xlsx.data[:2] == b"PK"
        pdf = client.get(f"/vat-books/{kind}.pdf?period=2026-A")
        assert pdf.status_code == 200 and pdf.data[:4] == b"%PDF"
    assert client.get("/vat-books/other.xlsx").status_code == 404
