"""Lot AG9a.b : échéancier de l'exploitation (US-A2).

EARL au réel simplifié et au RSA (acomptes et CA12A), exercice civil 2026 au rythme annuel, CA12A 2025 dans Lyvre
(TVA due 5 003 €) : le lundi 2 novembre 2026, l'acompte du 5/11 est « cette semaine » avec 1 001 € proposés.
"""
from datetime import date

import pytest

from app.extensions import db
from app.models import DeadlineState, TaxProfile
from app.services import agenda, organization, vat_installments
from test_vat_ca12a import _setup
from test_vat_installments import _previous

MONDAY = date(2026, 11, 2)


@pytest.fixture()
def farm(app, login_as):
    client = login_as(role="admin")
    data = {"client": client, **_setup()}
    org = organization.get()
    org.legal_form_code = "EARL"
    for kind, value in (("income_tax", "IR"), ("ba_regime", "simplified"), ("vat_regime", "rsa_installments")):
        db.session.add(TaxProfile(kind=kind, value=value, start_date=date(2025, 1, 1), origin="law"))
    db.session.commit()
    _previous(data, 6003, 500, 1000, 5003)
    return data


def _find(items, fiche_id, day=None):
    return [i for i in items if i["fiche_id"] == fiche_id and (day is None or i["date"] == day)]


def test_installment_of_the_week_with_its_amount(farm):
    data = agenda.occurrences(date(2026, 10, 1), date(2027, 6, 30), MONDAY)
    (installment,) = _find(data["items"], "TVA-02", date(2026, 11, 5))
    assert installment["status"] == "this_week" and installment["amount_cents"] == 100100
    assert installment["amount_proposed"] is True and installment["managed"] is True
    assert installment["period"] == "acompte n° 3 2026"
    (ca12a,) = _find(data["items"], "TVA-01")
    assert ca12a["date"] == date(2027, 5, 4) and ca12a["status"] == "upcoming"
    (liasse,) = _find(data["items"], "FIS-01")
    assert liasse["date"] == date(2027, 5, 4) and liasse["edi_date"] == date(2027, 5, 19)
    assert _find(data["items"], "DIV-02") and not _find(data["items"], "TVA-05")      # société ; pas au RFA
    assert "PAC-01" in data["questions"] and "SOC-05" in data["questions"]           # profil non renseigné


def test_profile_answers_remove_questions(farm):
    from app.services import agri_profile
    agri_profile.save({"pac": False, "employer": True, "leases": [{"label": "Bail", "due": "11-11"}]})
    data = agenda.occurrences(date(2026, 10, 1), date(2027, 3, 31), MONDAY)
    assert "PAC-01" not in data["questions"] and not _find(data["items"], "PAC-01")
    assert [i["date"] for i in _find(data["items"], "SOC-05")][:2] == [date(2026, 10, 15), date(2026, 11, 16)]
    (lease,) = _find(data["items"], "DIV-01", date(2026, 11, 11))
    assert lease["period"] == "2026 · Bail" and lease["status"] == "to_prepare"   # J+9


def test_installment_follows_its_declaration(farm):
    period = (date(2026, 1, 1), date(2026, 12, 31))
    for number in (1, 2, 3):
        vat_installments.validate(period, number, 100100)
    db.session.commit()
    items = agenda.occurrences(date(2026, 4, 1), date(2026, 12, 31), MONDAY)["items"]
    assert [i["status"] for i in _find(items, "TVA-02")] == ["ready", "ready", "ready"]


def test_manual_states(farm):
    client = farm["client"]
    body = client.get("/api/v1/agenda?from=2026-10-01&to=2026-10-31").get_json()
    (tfnb,) = [i for i in body["items"] if i["fiche_id"] == "FIS-06"]
    assert tfnb["date"] == "2026-10-15" and body["fiches"]["FIS-06"]["organism"] == "SIP"
    payload = {"deadline_id": tfnb["deadline_id"], "occurs_on": tfnb["date"], "period": tfnb["period"]}
    assert client.post("/api/v1/agenda/states", json={**payload, "status": "skipped"}).status_code == 422  # motif
    resp = client.post("/api/v1/agenda/states", json={**payload, "status": "done", "done_on": "2026-10-14"})
    assert resp.status_code == 201, resp.get_json()
    assert client.post("/api/v1/agenda/states", json={**payload, "status": "done"}).status_code == 409
    body = client.get("/api/v1/agenda?from=2026-10-01&to=2026-10-31").get_json()
    (tfnb,) = [i for i in body["items"] if i["fiche_id"] == "FIS-06"]
    assert tfnb["status"] == "done" and tfnb["state"]["done_on"] == "2026-10-14"
    assert client.delete(f"/api/v1/agenda/states/{tfnb['state']['id']}").status_code == 200
    assert DeadlineState.query.count() == 0
    installment = client.get("/api/v1/agenda?from=2026-11-01&to=2026-11-30").get_json()
    (tva,) = [i for i in installment["items"] if i["fiche_id"] == "TVA-02"]
    managed = client.post("/api/v1/agenda/states", json={"deadline_id": tva["deadline_id"], "occurs_on": tva["date"],
                                                         "period": tva["period"], "status": "done"})
    assert managed.status_code == 409
    assert client.get("/api/v1/agenda?from=2026-12-01&to=2026-11-01").status_code == 422
