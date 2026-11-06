"""Lot AG10.a : import FEC d'un dossier de cabinet en ancien plan agricole (PCGA 1986) et activités proposées.

FEC fictif en numérotation Isacompta (comptes généraux sur 8 chiffres) ; aucune donnée réelle."""
import io

import pytest

from app.extensions import db
from app.models import Account, AccountMapping, Activity, AnalyticRule, FiscalYear, Workshop
from app.services import agri_chart, fec, fec_import, import_activities

from test_agri_fixtures import _agri_instance


def _fec(rows):
    lines = ["\t".join(fec.FIELDS)] + ["\t".join(r) for r in rows]
    return ("\r\n".join(lines) + "\r\n").encode("iso-8859-15")


def _row(journal, num, day, account, label, debit, credit):
    return [journal, journal, num, day, account, label, "", "", f"P{num}", day, label, debit, credit, "", "", day, "", ""]


ROWS = [
    _row("VT", "1", "20250310", "41100000", "Clients", "3000,00", "0,00"),
    _row("VT", "1", "20250310", "70117111", "MAIS GRAINS", "0,00", "1800,00"),
    _row("VT", "1", "20250310", "70142000", "ASPERGES", "0,00", "700,00"),
    _row("VT", "1", "20250310", "70120700", "TOURNESOL", "0,00", "500,00"),
    _row("AC", "2", "20250315", "60110000", "ENGRAIS & AMENDEMENT", "400,00", "0,00"),
    _row("AC", "2", "20250315", "40100000", "Fournisseurs", "0,00", "400,00"),
    _row("BQ", "3", "20250320", "51200100", "BANQUE CREDIT AGRICOLE", "3000,00", "0,00"),
    _row("BQ", "3", "20250320", "41100000", "Clients", "0,00", "3000,00"),
]


def _post(client, url, content, **form):
    return client.post(url, data={"file": (io.BytesIO(content), "FEC20251231.txt"), **form},
                       content_type="multipart/form-data")


@pytest.fixture()
def farm(app, login_as):
    client = login_as(role="admin")
    _agri_instance()
    return client


def test_resolve_and_detection():
    assert agri_chart.resolve_pcga1986("60110000") == ("60111", False)        # renuméroté
    assert agri_chart.resolve_pcga1986("70117111") == ("7011", True)          # sous-compte de culture replié
    assert agri_chart.resolve_pcga1986("70600000") == ("706", False)          # numéro inchangé
    assert agri_chart.map_pcga1986("74300000") is None                        # sans correspondance
    assert agri_chart.old_numbering({"60110000", "70117111", "4010023", "41100000"})
    assert not agri_chart.old_numbering({"60111", "7011", "512100", "60110000"})


def test_match_production():
    assert import_activities.match_production("MAIS GRAINS")["reference"]
    assert import_activities.match_production("MAIS GRAINS")["name"] == "Maïs grain"
    assert import_activities.match_production("ASPERGES")["name"] == "Asperge"
    assert import_activities.match_production("HARICOTS VERTS")["name"] == "Haricot vert"
    assert import_activities.match_production("MAIS") is None                 # ambigu : grain, doux, ensilage…
    assert import_activities.match_production("PRODUITS DIVERS") is None


def test_analysis_maps_old_plan(farm):
    analysis = _post(farm, "/api/v1/imports/fec/analyze", _fec(ROWS)).get_json()
    assert analysis["pcga1986"] is True and analysis["problems"] == []
    plan = {r["key"]: r for r in analysis["accounts"]}
    assert plan["60110000"]["action"] == "mapped" and plan["60110000"]["target_code"] == "60111"
    assert plan["60110000"]["origin"] == "pcga1986"
    assert plan["70117111"]["action"] == "create" and plan["70117111"]["target_code"] == "70117111"
    # 701 → 7011 : les numéros qui ne commencent pas par 7011 prennent le premier numéro libre.
    assert plan["70120700"]["action"] == "create" and plan["70120700"]["target_code"] == "7011001"
    assert plan["70142000"]["target_code"] == "7011002"
    assert plan["51200100"]["target_code"] == "512001"


def test_import_then_activities(farm):
    resp = _post(farm, "/api/v1/imports/fec", _fec(ROWS), mode="history", start_date="2025-01-01", end_date="2025-12-31")
    assert resp.status_code == 200, resp.get_json()
    maize = Account.query.filter_by(code="70117111").one()
    assert maize.parent.code == "7011" and maize.account_type == maize.parent.account_type
    assert AccountMapping.query.filter_by(source_code="70120700").one()       # mémorisé pour l'exercice suivant
    # Exercice suivant : mêmes comptes retrouvés, rien à créer.
    again = _post(farm, "/api/v1/imports/fec/analyze", _fec([[c.replace("2025", "2026", 1) if i in (3, 9, 15) else c
                                                                for i, c in enumerate(r)] for r in ROWS])).get_json()
    assert again["to_create"] == 0

    items = farm.get("/api/v1/imports/activities").get_json()["items"]
    by_code = {p["code"]: p for p in items}
    assert by_code["70117111"]["name"] == "Maïs grain" and by_code["70117111"]["family"] == "plant_farming"
    assert by_code["70117111"]["lexicon_reference"]
    resp = farm.post("/api/v1/imports/activities", json={"items": [{"account_id": by_code["70117111"]["account_id"]},
                                                                    {"account_id": by_code["7011002"]["account_id"]}]})
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["activities"] == 2 and body["rules"] == 2
    assert {p["code"] for p in body["items"]} == set(by_code) - {"70117111", "7011002"}
    (workshop,) = Workshop.query.all()
    assert workshop.family == "plant_farming"
    rule = AnalyticRule.query.filter_by(account_prefix="70117111").one()
    assert rule.activity.name == "Maïs grain" and rule.activity.lexicon_reference == by_code["70117111"]["lexicon_reference"]
    assert Activity.query.filter_by(name="Asperge").one().workshop_id == workshop.id
    # Déjà ventilé : refus.
    assert farm.post("/api/v1/imports/activities", json={"items": [{"account_id": maize.id}]}).status_code == 409


def test_existing_activity_reused(farm):
    _post(farm, "/api/v1/imports/fec", _fec(ROWS), mode="history", start_date="2025-01-01", end_date="2025-12-31")
    workshop = Workshop(name="Cultures", family="plant_farming")
    db.session.add(workshop)
    db.session.flush()
    db.session.add(Activity(name="Tournesol", workshop_id=workshop.id))
    db.session.commit()
    items = {p["label"]: p for p in farm.get("/api/v1/imports/activities").get_json()["items"]}
    assert items["TOURNESOL"]["activity_id"] is not None
    farm.post("/api/v1/imports/activities", json={"items": [{"account_id": items["TOURNESOL"]["account_id"]}]})
    assert Activity.query.filter_by(name="Tournesol").count() == 1 and Workshop.query.count() == 1


def test_not_agri(app, login_as):
    client = login_as(role="admin")
    assert client.get("/api/v1/imports/activities").status_code == 404
    analysis = _post(client, "/api/v1/imports/fec/analyze", _fec(ROWS)).get_json()
    assert analysis["pcga1986"] is False
    assert {r["key"]: r for r in analysis["accounts"]}["60110000"]["target_code"] == "60110000"
