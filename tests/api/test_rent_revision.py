"""Lot L5 : révision des loyers — indices (INSEE simulé, saisie, correction), révision appliquée à la
date prévue (prix des lignes, facture récurrente, dépôt), en attente sans indice, bail signé révisé,
courrier au preneur."""
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO

import pytest
from pypdf import PdfReader

from app.extensions import db
from app.models import Lease, LeaseRevision, LeaseSignature, RentIndex
from app.services import rent_revision
from test_lease_wizard import _tenant, admin  # noqa: F401  (fixture)

API = "/api/v1/leases"
TODAY = date.today()


@pytest.fixture()
def insee(monkeypatch):
    """INSEE simulé : séries par identifiant, appels comptés."""
    published = {"001532540": [("2025-Q2", Decimal("135.30"))], "001617112": [], "001515333": []}
    calls = []

    def fetch_series(series_id):
        calls.append(series_id)
        return list(published[series_id])

    monkeypatch.setattr(rent_revision, "fetch_series", fetch_series)
    return {"published": published, "calls": calls}


def _lease(admin, **terms):  # noqa: F811
    lease = admin.post(API, json={"draft": True, "entity_id": _tenant().id, "unit_label": "La Vauzelle",
                                  "kind": "derogatory", "start_date": date(TODAY.year - 3, 1, 1).isoformat(),
                                  "deposit": "200", "index_code": "ILC", "revision_months": "36",
                                  "index_reference_period": "2025-T2", "index_reference_value": "135.30",
                                  "revise_deposit": True, **terms}).get_json()["item"]
    admin.post(f"{API}/{lease['id']}/items", json={"label": "Bureau", "nature": "building", "area_m2": 40, "unit_price": "2"})
    admin.post(f"{API}/{lease['id']}/items", json={"label": "Terres", "nature": "land", "area_m2": 10323, "unit_price": "140"})
    assert admin.post(f"{API}/{lease['id']}/activate", json={"frequency": "yearly"}).status_code == 200
    row = db.session.get(Lease, lease["id"])
    row.next_revision_date = TODAY - timedelta(days=1)  # révision arrivée
    db.session.commit()
    return lease["id"]


def test_periods():
    assert rent_revision.normalize_period("ILC", "2025-T2") == "2025-Q2"
    assert rent_revision.normalize_period("IRL", "2025 q4") == "2025-Q4"
    assert rent_revision.normalize_period("FERMAGES", "2025") == "2025"
    with pytest.raises(rent_revision.RevisionError):
        rent_revision.normalize_period("ILC", "2025")
    assert rent_revision.shift_period("2025-Q2", 36) == "2028-Q2" and rent_revision.shift_period("2025", 12) == "2026"
    assert rent_revision.label_period("2025-Q1") == "1er trimestre 2025"


def test_revision_pending_then_applied(admin, insee):  # noqa: F811
    lease_id = _lease(admin)
    due = admin.get("/api/v1/sales/due").get_json()["meta"]["revisions"]
    assert due == {"applied": 0, "pending": 1} and len(insee["calls"]) == 3  # INSEE relu une fois
    rev = admin.get(f"{API}/{lease_id}").get_json()["item"]["revisions"][0]
    assert rev["status"] == "pending" and rev["note"] == "Indice ILC du 2e trimestre 2028 pas encore connu."
    admin.get("/api/v1/sales/due")
    assert len(insee["calls"]) == 3 and LeaseRevision.query.count() == 1  # pas deux fois le même jour

    resp = admin.post("/api/v1/rent-indices", json={"code": "ILC", "period": "2028-T2", "value": "140,00"})
    assert resp.status_code == 201 and "1 révision(s) de loyer appliquée(s)." in resp.get_json()["notices"][1]["message"]
    lease = admin.get(f"{API}/{lease_id}").get_json()["item"]
    rev = lease["revisions"][0]
    assert rev["status"] == "applied" and (rev["old_value"], rev["new_value"]) == ("135.30", "140.00")
    # 2,00 € × 140 / 135,30 = 2,07 € le m² ; 140 € × 1,0347 = 144,86 € l'hectare ; dépôt révisé.
    assert [(i["unit_price_cents"], i["annual_cents"]) for i in lease["items"]] == [(207, 8280), (14486, 14921)]
    assert (rev["old_annual_cents"], rev["new_annual_cents"]) == (22420, 23201)
    assert (rev["old_deposit_cents"], rev["new_deposit_cents"]) == (20000, 20695) and lease["deposit_cents"] == 20695
    assert sum(l.unit_price_cents for l in db.session.get(Lease, lease_id).recurrence.template.lines) == 23201
    assert (lease["index_reference_period"], lease["index_reference_value"]) == ("2028-Q2", "140.00")
    assert lease["next_revision_date"] == (TODAY - timedelta(days=1)).replace(year=TODAY.year + 3).isoformat()
    assert rent_revision.revise_due(fetch=False) == {"applied": 0, "pending": 0}  # rien de plus

    pdf = PdfReader(BytesIO(admin.get(rev["letter_url"]).data))
    text = "".join(p.extract_text() for p in pdf.pages)
    for expected in ("Révision du loyer — La Vauzelle", "224,20 €", "232,01 €", "2e trimestre 2028", "140,00"):
        assert expected in text, expected


def test_signed_lease_is_still_revised(admin, insee):  # noqa: F811
    lease_id = _lease(admin, revise_deposit=False)
    db.session.add(LeaseSignature(lease_id=lease_id, submission_id="e1", status="completed", sent_at=datetime.utcnow()))
    db.session.add(RentIndex(code="ILC", period="2028-Q2", value=Decimal("140.00"), source="insee"))
    db.session.commit()
    result = admin.post("/api/v1/lease-revisions/run").get_json()["result"]
    assert result == {"applied": 1, "pending": 0}
    lease = db.session.get(Lease, lease_id)
    assert lease.deposit_cents == 20000 and lease.items[0].unit_price_cents == 207  # dépôt non révisé (clause)


def test_missing_reference_period(admin, insee):  # noqa: F811
    lease_id = _lease(admin, index_reference_period="", index_reference_value="")
    admin.post("/api/v1/lease-revisions/run")
    rev = LeaseRevision.query.filter_by(lease_id=lease_id).one()
    assert rev.status == "pending" and "Période de l'indice de référence manquante" in rev.note


def test_indices_fetch_save_and_delete(admin, insee):  # noqa: F811
    insee["published"]["001532540"] = [("2026-Q1", Decimal("135.26")), ("2026-Q2", Decimal("137.16"))]
    resp = admin.post("/api/v1/rent-indices/fetch")
    assert resp.status_code == 200 and "2 valeur(s) nouvelle(s)" in resp.get_json()["notices"][0]["message"]
    admin.post("/api/v1/rent-indices", json={"code": "ILC", "period": "2026-Q2", "value": "137.20"})  # correction
    insee["published"]["001532540"] = [("2026-Q2", Decimal("137.16"))]
    admin.post("/api/v1/rent-indices/fetch")
    assert rent_revision.value_of("ILC", "2026-Q2") == Decimal("137.20")  # la saisie l'emporte
    admin.post("/api/v1/rent-indices", json={"code": "FERMAGES", "period": "2025", "value": "123.06"})
    body = admin.get("/api/v1/rent-indices").get_json()
    assert {(i["code"], i["period"], i["source"]) for i in body["items"]} == {
        ("ILC", "2026-Q1", "insee"), ("ILC", "2026-Q2", "manual"), ("FERMAGES", "2025", "manual")}
    insee_row = next(i for i in body["items"] if i["source"] == "insee")
    manual_row = next(i for i in body["items"] if i["code"] == "FERMAGES")
    assert admin.delete(f"/api/v1/rent-indices/{insee_row['id']}").status_code == 409
    assert admin.delete(f"/api/v1/rent-indices/{manual_row['id']}").status_code == 200
    for bad in ({"code": "ILC", "period": "2025", "value": "1"}, {"code": "X", "period": "2025-T1", "value": "1"},
                {"code": "IRL", "period": "2025-T1", "value": "abc"}):
        assert admin.post("/api/v1/rent-indices", json=bad).status_code == 422
