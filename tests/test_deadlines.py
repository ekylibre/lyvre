"""Lot AG9a.a : base d'échéances (data/deadlines), règles de date, applicabilité, profil des démarches."""
from datetime import date, timedelta

import pytest

from app.extensions import db
from app.models import Instance
from app.services import agri_profile, deadlines
from app.services.deadlines import Context


def _event(fiche_id, label_start):
    return next(e for e in deadlines.fiche(fiche_id)["events"] if e["label"].startswith(label_start))


def _ctx(close: date, **kw) -> Context:
    start = (close + timedelta(days=1)).replace(year=close.year - 1)
    return Context(fiscal_years=[(start, close)], **kw)


def _first(rule, ctx, after):
    return deadlines.dates(rule, after, after + timedelta(days=400), ctx)[0]


def test_base_is_valid_and_complete():
    fiches = deadlines.fiches()
    assert len(fiches) == 39 and len({f["id"] for f in fiches}) == 39       # 38 de l'audit + DIV-06 (AG5.c)
    assert {f["domain"] for f in fiches} == set(deadlines.DOMAINS)
    bad = [{"id": "X-1", "title": "x", "domain": "tva", "organism": "x", "summary": "x", "reliability": "Z",
            "applies": {"weather": [1]}, "events": [{"label": "x", "rule": {"type": "eval", "expr": "1"}}]}]
    problems = deadlines.validate(bad)
    assert any("fiabilité" in p for p in problems) and any("condition inconnue" in p for p in problems)
    assert any("règle de date inconnue" in p for p in problems)


@pytest.mark.parametrize("close, liasse, solde_is, ag", [
    (date(2026, 3, 31), date(2026, 6, 30), date(2026, 7, 15), date(2026, 9, 30)),
    (date(2026, 4, 30), date(2026, 7, 31), date(2026, 8, 17), date(2026, 10, 31)),   # 15/8 : samedi férié
    (date(2026, 6, 30), date(2026, 9, 30), date(2026, 10, 15), date(2026, 12, 31)),
    (date(2026, 8, 31), date(2026, 11, 30), date(2026, 12, 15), date(2027, 2, 28)),
    (date(2026, 9, 30), date(2026, 12, 31), date(2027, 1, 15), date(2027, 3, 31)),
    # 31/12 : 2e jour ouvré après le 1er mai ; solde d'IS le 15/5 (samedi), reporté après le lundi de Pentecôte.
    (date(2026, 12, 31), date(2027, 5, 4), date(2027, 5, 18), date(2027, 6, 30)),
])
def test_dates_by_closing_date(app, close, liasse, solde_is, ag):
    """Table § 3.4 de audit_calendrier.md (liasse, solde d'IS, AG) pour six dates de clôture."""
    with app.app_context():
        ctx = _ctx(close)
        assert _first(_event("FIS-01", "Liasse")["rule"], ctx, close).date == liasse
        assert _first(_event("FIS-03", "Solde")["rule"], ctx, close).date == solde_is
        assert _first(_event("DIV-02", "Assemblée")["rule"], ctx, close).date == ag


def test_edi_delay_and_is_installments(app):
    with app.app_context():
        ctx = _ctx(date(2026, 12, 31))
        liasse = _first(_event("FIS-01", "Liasse")["rule"], ctx, date(2026, 12, 31))
        assert liasse.edi_date == date(2027, 5, 19)
        installments = deadlines.dates(_event("FIS-03", "Acompte")["rule"], date(2026, 1, 1), date(2026, 12, 31),
                                       Context(fiscal_years=[(date(2026, 1, 1), date(2026, 12, 31))]))
        assert [o.date for o in installments] == [date(2026, 3, 16), date(2026, 6, 15), date(2026, 9, 15),
                                                  date(2026, 12, 15)]   # 15/3/2026 : dimanche


def test_annual_parameter_and_fallback_to_confirm(app):
    with app.app_context():
        rule = _event("PAC-01", "Date limite")["rule"]
        ctx = Context()
        y2026 = deadlines.dates(rule, date(2026, 1, 1), date(2026, 12, 31), ctx)
        assert [(o.date, o.to_confirm) for o in y2026] == [(date(2026, 5, 18), False)]
        y2027 = deadlines.dates(rule, date(2027, 1, 1), date(2027, 12, 31), ctx)
        # Repli : 15/5/2027 (samedi), lundi 17/5 de Pentecôte férié → 18/5, « date à confirmer ».
        assert [(o.date, o.to_confirm, o.note) for o in y2027] == [(date(2027, 5, 18), True, "Date à confirmer")]
        msa = _event("SOC-02", "Appel")["rule"]
        known = deadlines.dates(msa, date(2026, 1, 1), date(2026, 12, 31), Context(profile={"msa_fund": "nord_pas_de_calais"}))
        assert [o.date for o in known] == [date(2026, 4, 28), date(2026, 10, 13), date(2026, 12, 8)]
        assert not any(o.to_confirm for o in known)
        unknown = deadlines.dates(msa, date(2026, 1, 1), date(2026, 12, 31), Context())
        assert len(unknown) == 3 and all(o.to_confirm for o in unknown)


def test_profile_leases_and_monthly_rules(app):
    with app.app_context():
        ctx = Context(profile={"leases": [{"label": "Bail des Grands Champs", "due": "11-11", "role": "tenant"}],
                               "young_farmer_since": "2024-03-15"})
        leases = deadlines.dates(_event("DIV-01", "Échéance")["rule"], date(2026, 11, 1), date(2027, 11, 30), ctx)
        assert [(o.date, o.note) for o in leases] == [(date(2026, 11, 11), "Bail des Grands Champs"),
                                                       (date(2027, 11, 11), "Bail des Grands Champs")]
        ja = deadlines.dates(_event("PAC-06", "Fin")["rule"], date(2026, 1, 1), date(2030, 1, 1), ctx)
        assert [o.date for o in ja] == [date(2028, 3, 15)]
        dsn = deadlines.dates(_event("SOC-05", "DSN")["rule"], date(2026, 11, 1), date(2027, 1, 31), Context())
        assert [o.date for o in dsn] == [date(2026, 11, 16), date(2026, 12, 15), date(2027, 1, 15)]


def test_every_event_computes_over_two_years(app):
    profile = {"pac": True, "employer": True, "irrigation": True, "plant_protection": True, "bonded_warehouse": True,
               "young_farmer": True, "young_farmer_since": "2025-02-01", "certiphyto_expires_on": "2027-06-30",
               "non_agricultural": True, "msa_fund": "cotes_normandes", "productions": list(agri_profile.PRODUCTIONS),
               "leases": [{"label": "Bail", "due": "09-29", "role": "tenant"}]}
    with app.app_context():
        ctx = Context(legal_form="SAS", profile=profile, fiscal_years=[(date(2025, 7, 1), date(2026, 6, 30))])
        dated = 0
        for fiche in deadlines.fiches():
            for event in fiche["events"]:
                if event["rule"]["type"] == "lyvre":
                    continue
                found = deadlines.dates(event["rule"], date(2026, 1, 1), date(2027, 12, 31), ctx)
                assert all(date(2026, 1, 1) <= o.date <= date(2027, 12, 31) for o in found), fiche["id"]
                dated += bool(found)
        assert dated >= 30


def test_applicability():
    on = date(2026, 11, 2)
    rsa = Context(legal_form="EARL", tax={"vat_regime": "rsa_installments", "income_tax": "IR", "ba_regime": "simplified"})
    assert deadlines.applies(deadlines.fiche("TVA-02")["applies"], rsa, on) is True
    assert deadlines.applies(deadlines.fiche("TVA-05")["applies"], rsa, on) is False
    assert deadlines.applies(deadlines.fiche("FIS-01")["applies"], rsa, on) is True
    assert deadlines.applies(deadlines.fiche("DIV-02")["applies"], rsa, on) is True        # société
    assert deadlines.applies({"commercial": True}, rsa, on) is False                         # EARL : civile
    assert deadlines.applies(deadlines.fiche("PAC-01")["applies"], rsa, on) is None          # non renseigné
    assert deadlines.applies(deadlines.fiche("PAC-01")["applies"], Context(profile={"pac": False}), on) is False
    assert deadlines.applies(deadlines.fiche("ELE-01")["applies"], Context(profile={"productions": ["cattle"]}), on) is True
    assert deadlines.applies(deadlines.fiche("DIV-01")["applies"], Context(profile={"leases": []}), on) is False
    assert deadlines.applies(deadlines.fiche("TVA-02")["applies"], Context(), on) is None     # régime inconnu


def test_profile_validation():
    assert agri_profile.clean({"pac": True, "productions": ["cattle", "cattle"], "msa_fund": "cotes_normandes"}) == {
        "pac": True, "productions": ["cattle"], "msa_fund": "cotes_normandes"}
    for data, field in (({"pac": "oui"}, "pac"), ({"productions": ["vaches"]}, "productions"),
                        ({"pacage": "12"}, "pacage"), ({"leases": [{"label": "x", "due": "13-01"}]}, "leases"),
                        ({"meteo": 1}, "meteo"), ({"certiphyto_expires_on": "demain"}, "certiphyto_expires_on")):
        with pytest.raises(agri_profile.ProfileError) as exc:
            agri_profile.clean(data)
        assert exc.value.field == field


def test_api_profile_and_deadlines(app, login_as):
    client = login_as(role="admin")
    Instance.query.filter_by(slug="test").one().chart = "agri"
    db.session.commit()
    resp = client.put("/api/v1/agri-profile", json={"pac": True, "msa_fund": "nord_pas_de_calais",
                                                    "leases": [{"label": "Bail", "due": "09-29"}]})
    assert resp.status_code == 200, resp.get_json()
    assert client.get("/api/v1/agri-profile").get_json()["item"]["leases"][0]["role"] == "tenant"
    assert client.put("/api/v1/agri-profile", json={"msa_fund": "x"}).status_code == 422
    items = {f["id"]: f for f in client.get("/api/v1/deadlines").get_json()["items"]}
    assert items["PAC-01"]["applicable"] == "yes" and items["DIV-01"]["applicable"] == "yes"
    assert items["SOC-05"]["applicable"] == "unknown"
    Instance.query.filter_by(slug="test").one().chart = "societe"
    db.session.commit()
    assert client.get("/api/v1/deadlines").status_code == 404
