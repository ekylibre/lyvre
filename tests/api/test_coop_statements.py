"""Lot AG10.d : décomptes de coopérative (lignes typées, écriture unique, activités). Données fictives."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, AnalyticAllocation, AnalyticRule, CoopStatement, Entity, FiscalYear, JournalEntry
from app.services import analytic, import_activities

from test_agri_fixtures import _agri_instance

API = "/api/v1/coop-statements"


@pytest.fixture()
def farm(app, login_as):
    client = login_as(role="admin")
    _agri_instance()
    db.session.add_all([
        FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), vat_liable=True,
                   vat_on_receipts=False),
        Entity(name="Coopérative Fictive", entity_type="CLIENT", siren="775665912"),
        Account(code="7011001", label="Blé tendre", account_type="PRODUIT",
                parent_id=Account.query.filter_by(code="7011").one().id),
    ])
    db.session.commit()
    workshop = import_activities._workshop("plant_farming")
    activity = analytic.save_activity(None, {"workshop_id": workshop.id, "name": "Blé tendre"})
    db.session.add(AnalyticRule(account_prefix="7011001", activity_id=activity.id))
    db.session.commit()
    return client


def _coop():
    return Entity.query.filter_by(name="Coopérative Fictive").one()


def _activity():
    from app.models import Activity
    return Activity.query.filter_by(name="Blé tendre").one()


def _body(**extra):
    return {"entity_id": _coop().id, "number": "DEC-2026-07", "statement_date": "2026-09-30", "label": "Moisson 2026",
            "lines": [
                {"kind": "delivery", "label": "Blé tendre", "quantity": "30", "unit": "t", "amount": "6000",
                 "vat_rate": "5,5", "activity_id": str(_activity().id)},
                {"kind": "complement", "label": "Complément blé 2025", "amount": "400", "vat_rate": "5,5",
                 "account_code": "7011001", "campaign_year": "2025"},
                {"kind": "rebate", "label": "Ristourne", "amount": "100", "vat_rate": "5,5", "account_code": "7011"},
                {"kind": "advance", "label": "Acompte de juillet", "amount": "2000"},
                {"kind": "shares", "label": "Parts sociales", "amount": "150"},
                {"kind": "fee", "label": "Frais de collecte", "amount": "200", "vat_rate": "20", "account_code": "6226"},
            ], **extra}


def test_save_propose_post_and_unpost(farm):
    if Account.query.filter_by(code="6226").first() is None:
        db.session.add(Account(code="6226", label="Honoraires", account_type="CHARGE"))
        db.session.commit()
    resp = farm.post(API, json=_body())
    assert resp.status_code == 201, resp.get_json()
    item = resp.get_json()["item"]
    accounts = [l["account_code"] for l in item["lines"]]
    assert accounts == ["7011001", "7011001", "7011", "", "2621", "6226"]   # activité → règle ; parts → 2621
    assert item["lines"][0]["campaign_year"] == "2026"                      # campagne déduite de la date
    # Ventes 6 500 HT + TVA 357,50 ; parts 150 ; frais 200 + 40 ; acompte 2 000.
    assert (item["sales_cents"], item["sales_vat_cents"], item["fees_vat_cents"]) == (650000, 35750, 4000)
    assert item["customer_cents"] == 650000 + 35750 - 15000 - 20000 - 4000
    assert item["net_cents"] == item["customer_cents"] - 200000
    assert item["problems"] == []
    # Doublon : même coopérative, même numéro.
    assert farm.post(API, json=_body()).status_code == 409
    resp = farm.post(f"{API}/{item['id']}/post")
    assert resp.status_code == 200, resp.get_json()
    entry = db.session.get(JournalEntry, resp.get_json()["item"]["journal_entry"]["id"])
    assert entry.journal.code == "VE" and entry.entry_date == date(2026, 9, 30)
    assert sum(l.debit_cents for l in entry.lines) == sum(l.credit_cents for l in entry.lines)
    by_code = {}
    for l in entry.lines:
        by_code.setdefault(l.account.code, [0, 0])
        by_code[l.account.code][0] += l.debit_cents
        by_code[l.account.code][1] += l.credit_cents
    assert by_code["7011001"] == [0, 640000] and by_code["7011"] == [0, 10000]
    assert by_code["2621"] == [15000, 0] and by_code["6226"] == [20000, 0]
    assert by_code["44571"] == [0, 35750] and by_code["44566"] == [4000, 0]
    assert by_code[_coop().customer_account_code] == [item["customer_cents"], 0]
    assert {l.vat_code for l in entry.lines if l.account.code == "44571"} == {"V55"}
    assert {l.vat_code for l in entry.lines if l.account.code == "44566"} == {"D20"}
    allocations = AnalyticAllocation.query.all()
    assert [(a.activity_id, a.campaign_year, a.origin) for a in allocations] == [(_activity().id, 2026, "coop")]
    # Comptabilisé : ni modifié ni supprimé ; retour en brouillon possible (écriture non validée).
    assert farm.put(f"{API}/{item['id']}", json=_body()).status_code == 409
    assert farm.delete(f"{API}/{item['id']}").status_code == 409
    resp = farm.post(f"{API}/{item['id']}/unpost")
    assert resp.status_code == 200 and resp.get_json()["item"]["status"] == "draft"
    assert db.session.get(JournalEntry, entry.id) is None
    assert farm.delete(f"{API}/{item['id']}").status_code == 200
    assert CoopStatement.query.count() == 0


def test_refusals(farm):
    body = _body()
    body["lines"] = [{"kind": "shares", "label": "Parts", "amount": "100"}]
    assert farm.post(API, json=body).status_code == 422                     # pas de vente
    body["lines"] = [{"kind": "delivery", "label": "Blé", "amount": "-5"}]
    assert farm.post(API, json=body).status_code == 422                     # montant positif
    body["lines"] = [{"kind": "delivery", "label": "Blé", "amount": "5", "account_code": "2621"}]
    assert farm.post(API, json=body).status_code == 422                     # compte inadapté
    body["lines"] = [{"kind": "advance", "label": "Acompte", "amount": "5", "vat_rate": "20"},
                     {"kind": "delivery", "label": "Blé", "amount": "5"}]
    assert farm.post(API, json=body).status_code == 422                     # TVA sur un acompte
    body["lines"] = [{"kind": "delivery", "label": "Produit inconnu", "amount": "5"}]
    item = farm.post(API, json=body).get_json()["item"]
    assert item["problems"] == ["Compte manquant (ligne 1)."]
    assert farm.post(f"{API}/{item['id']}/post").status_code == 409


def test_not_agri(app, login_as):
    client = login_as(role="admin")
    assert client.get(API).status_code == 404


def test_coop_journal_and_entity_groups(farm):
    """Essai de l'interface (10/11/2026) : un journal par coopérative (reprise d'un FEC), associés écartés de la liste."""
    from app.models import Associate, Journal
    from app.services.ledger import post_entry
    coop = _coop()
    coop.customer_account_code = "411900"
    kb = Journal(code="KB", label="Coopérative B")
    partner = Entity(name="Associée Fictive")
    db.session.add_all([kb, partner, Account(code="411900", label="Coop", account_type="TIERS"),
                        Account(code="455100", label="Associée", account_type="TIERS")])
    db.session.flush()
    db.session.add(Associate(entity_id=partner.id, account_id=Account.query.filter_by(code="455100").one().id))
    db.session.commit()
    fy = FiscalYear.query.one()
    ids = {c: Account.query.filter_by(code=c).one().id for c in ("411900", "7011")}
    post_entry(fy.id, kb.id, date(2026, 3, 1), "apport", [
        {"account_id": ids["411900"], "label": "x", "debit_cents": 1000, "credit_cents": 0},
        {"account_id": ids["7011"], "label": "x", "debit_cents": 0, "credit_cents": 1000}])
    options = farm.get(f"{API}/form-options").get_json()
    entities = {e["label"]: e for e in options["entities"]}
    assert "Associée Fictive" not in entities
    assert entities["Coopérative Fictive"]["journal"] == "KB" and options["entities"][0]["label"] == "Coopérative Fictive"
    assert entities["Coopérative Fictive"]["group"] == "Coopératives et négoces"
    assert "OD" not in {j["value"] for j in options["journals"]}
    assert farm.post(API, json=_body(journal_code="OD")).status_code == 422
    item = farm.post(API, json=_body(journal_code="KB")).get_json()["item"]
    assert item["journal_code"] == "KB"
    if Account.query.filter_by(code="6226").first() is None:
        db.session.add(Account(code="6226", label="Honoraires", account_type="CHARGE"))
        db.session.commit()
    resp = farm.post(f"{API}/{item['id']}/post")
    assert resp.status_code == 200, resp.get_json()
    assert db.session.get(JournalEntry, resp.get_json()["item"]["journal_entry"]["id"]).journal.code == "KB"
