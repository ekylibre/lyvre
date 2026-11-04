"""Lot AG2.c : acomptes de TVA du régime simplifié agricole (3525 bis).

CA12A 2025 de référence (saisie directe de la déclaration) : ligne 15 = 6 003, ligne 21 = 1 000 dont ligne 17
(immobilisations) = 500, ligne 23 = 5 003 → acompte proposé ⌈ 5 003 × 20 % ⌉ = 1 001 € ; avant immobilisations
5 503 € ≥ 1 000 € : pas de dispense.
"""
import json
from datetime import date

import pytest

from app.extensions import db
from app.models import JournalEntry, VatReturn
from app.services import vat_installments
from test_vat_ca12a import _entry, _setup


@pytest.fixture()
def books(app, login_as):
    client = login_as()
    return {"client": client, **_setup()}


def _previous(books, line15, line17, line21, line23):
    boxes = {"15": {"amount": line15}, "17": {"amount": line17}, "21": {"amount": line21}, "23": {"amount": line23}}
    db.session.add(VatReturn(fiscal_year_id=books["fy"].id, period_start=date(2025, 1, 1), period_end=date(2025, 12, 31),
                             form="CA12A", status="declared", boxes_json=json.dumps({"boxes": boxes}),
                             due_cents=line23 * 100))
    db.session.commit()


def _schedule(books):
    return books["client"].get("/api/v1/vat-returns/installments?period=2026-A").get_json()


def test_schedule_and_amount_rounded_up_to_the_euro(books):
    _previous(books, 6003, 500, 1000, 5003)
    body = _schedule(books)
    assert body["reference"]["source"] == "ca12a" and body["reference"]["due_cents"] == 500300
    assert body["reference"]["before_assets_cents"] == 550300 and body["dispensed"] is False
    assert body["proposed_cents"] == 100100
    assert [(i["number"], i["start"], i["end"], i["deadline"]) for i in body["items"]] == [
        (1, "2026-01-01", "2026-03-31", "2026-05-05"), (2, "2026-04-01", "2026-06-30", "2026-08-05"),
        (3, "2026-07-01", "2026-09-30", "2026-11-05"), (4, "2026-10-01", "2026-12-31", "2027-02-05")]
    assert [i["can_validate"] for i in body["items"]] == [True, False, False, False]


def test_exemption_read_before_fixed_asset_vat(books):
    # Ligne 23 = 600 € seule dispenserait ; avant immobilisations : 1 600 − 1 000 + 500 = 1 100 € → acomptes dus.
    _previous(books, 1600, 500, 1000, 600)
    body = _schedule(books)
    assert body["dispensed"] is False and body["proposed_cents"] == 12000


def test_exemption_below_1000_euros(books):
    _previous(books, 1600, 300, 1000, 600)  # avant immobilisations : 900 €
    body = _schedule(books)
    assert body["dispensed"] is True and body["proposed_cents"] is None
    assert {i["status"] for i in body["items"]} == {"dispensed"}
    resp = books["client"].post("/api/v1/vat-returns/installments",
                                json={"period": "2026-A", "number": 1, "amount_cents": 10000})
    assert resp.status_code == 409 and "Dispensé" in resp.get_json()["error"]["message"]


def test_validate_declare_and_ca12a_line_25(books):
    _previous(books, 6003, 500, 1000, 5003)
    client = books["client"]
    post = lambda **kw: client.post("/api/v1/vat-returns/installments", json={"period": "2026-A", **kw})  # noqa: E731
    assert post(number=2, amount_cents=100100).status_code == 409          # dans l'ordre
    modulated = post(number=1, amount_cents=50000)
    assert modulated.status_code == 422 and "motive" in modulated.get_json()["error"]["fields"]
    assert post(number=1, amount_cents=100050).status_code == 422          # euros entiers
    resp = post(number=1, amount_cents=100100)
    assert resp.status_code == 201, resp.get_json()
    ret = VatReturn.query.filter_by(form="ACOMPTE").one()
    assert (ret.period_start, ret.period_end, ret.deadline, ret.due_cents) == (
        date(2026, 1, 1), date(2026, 3, 31), date(2026, 5, 5), 100100)
    lines = {l.account.code: (l.debit_cents, l.credit_cents) for l in ret.liquidation_entry.lines}
    assert lines == {"44581": (100100, 0), "44551": (0, 100100)}
    assert ret.liquidation_entry.validation_number is None
    assert post(number=2, amount_cents=0, motive="Suspension : acomptes suffisants").status_code == 201

    paid = client.post(f"/api/v1/vat-returns/{ret.id}/declare", json={"declared_on": "2026-05-04"})
    assert paid.status_code == 200, paid.get_json()
    db.session.refresh(ret)
    assert ret.status == "declared" and ret.liquidation_entry.validation_number is not None
    db.session.refresh(books["fy"])
    assert books["fy"].locked_until is None                                # un acompte ne verrouille pas

    _entry(books, date(2026, 3, 2), ("411", 1200000, 0), ("7013", 0, 1000000), ("44571", 0, 200000, "V20", 1000000))
    preview = client.get("/api/v1/vat-returns/preview?period=2026-A").get_json()
    assert preview["installments_cents"] == 100100
    late = vat_installments.missing(date(2026, 1, 1), date(2026, 12, 31), today=date(2026, 11, 6))
    assert [i["number"] for i in late] == [3]
    assert client.post("/api/v1/vat-returns", json={"period": "2026-A"}).status_code == 201
    second = VatReturn.query.filter_by(form="ACOMPTE", period_start=date(2026, 4, 1)).one()
    refused = client.post(f"/api/v1/vat-returns/{second.id}/unvalidate")
    assert refused.status_code == 409 and "CA12A" in refused.get_json()["error"]["message"]
    assert post(number=3, amount_cents=100100).status_code == 409          # figés par la CA12A


def test_unvalidate_deletes_draft_entry(books):
    _previous(books, 6003, 500, 1000, 5003)
    client = books["client"]
    client.post("/api/v1/vat-returns/installments", json={"period": "2026-A", "number": 1, "amount_cents": 100100})
    ret = VatReturn.query.filter_by(form="ACOMPTE").one()
    entry_id = ret.liquidation_entry_id
    assert client.post(f"/api/v1/vat-returns/{ret.id}/unvalidate").status_code == 200
    assert VatReturn.query.filter_by(form="ACOMPTE").count() == 0 and db.session.get(JournalEntry, entry_id) is None


def test_entered_reference_and_new_taxpayer(books):
    client = books["client"]
    body = _schedule(books)
    assert body["reference"]["source"] == "missing" and body["proposed_cents"] is None
    assert any("70 %" in w for w in body["warnings"])
    resp = client.put("/api/v1/vat-returns/installments/reference",
                      json={"period": "2026-A", "reference_cents": 400000, "assets_cents": 0})
    assert resp.status_code == 200
    body = resp.get_json()["item"]
    assert body["reference"]["source"] == "entered" and body["proposed_cents"] == 80000
    client.put("/api/v1/vat-returns/installments/reference", json={"period": "2026-A", "reference_cents": None})
    # Nouvel assujetti : montant libre, sans motif.
    resp = client.post("/api/v1/vat-returns/installments", json={"period": "2026-A", "number": 1, "amount_cents": 30000})
    assert resp.status_code == 201
    refused = client.put("/api/v1/vat-returns/installments/reference", json={"period": "2026-A", "reference_cents": 1})
    assert refused.status_code == 409


def test_alert_when_estimated_vat_exceeds_reduced_installments_by_30_percent(books):
    _previous(books, 6003, 500, 1000, 5003)
    client = books["client"]
    client.post("/api/v1/vat-returns/installments",
                json={"period": "2026-A", "number": 1, "amount_cents": 0, "motive": "Baisse d'activité"})
    # 2 000 € de TVA nette au 1er semestre → 4 000 € estimés sur l'année ; acomptes : 0 + 3 × 1 001 = 3 003 €.
    _entry(books, date(2026, 3, 2), ("411", 1200000, 0), ("7013", 0, 1000000), ("44571", 0, 200000, "V20", 1000000))
    period = (date(2026, 1, 1), date(2026, 12, 31))
    data = vat_installments.schedule(period, today=date(2026, 7, 2))
    assert data["planned_cents"] == 300300 and data["estimate"]["year_cents"] == pytest.approx(400000, rel=0.01)
    assert any(w.startswith("TVA estimée") for w in data["warnings"])
    calm = vat_installments.schedule(period, today=date(2026, 12, 31))   # 2 000 € sur l'année : sous 3 003 €
    assert not any(w.startswith("TVA estimée") for w in calm["warnings"])


def test_fiscal_year_calendar_blocks(app):
    with app.app_context():
        due = [vat_installments.due_date(end) for _, end in vat_installments.blocks(date(2025, 7, 1), date(2026, 6, 30))]
    assert due == [date(2025, 11, 5), date(2026, 2, 5), date(2026, 5, 5), date(2026, 8, 5)]
