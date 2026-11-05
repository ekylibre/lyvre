"""Lot AG8.a : ateliers, activités, campagnes et mesures (claudedocs/design_analytique_agricole.md § 3, AGD25)."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Activity
from app.services import analytic
from test_agri_fixtures import _agri_instance


@pytest.fixture()
def farm(app, login_as):
    client = login_as(role="admin")
    _agri_instance()
    return client


def _workshop(client, name="Vaches laitières", family="animal_farming"):
    resp = client.post("/api/v1/workshops", json={"name": name, "family": family})
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["item"]


def test_lexicon_extract():
    wheat = analytic.lexicon_production("winter_common_wheat")
    assert wheat["start"] == "10-01" and wheat["stop"] == "08-31" and wheat["year_offset"] == 1 and wheat["unit"] == "hectare"
    assert analytic.lexicon_source()["licence"] == "CC-BY-SA 4.0"
    assert any(p["reference"] == "milk_cow" for p in analytic.lexicon_search("vaches lait"))


def test_campaign_of_a_date(farm):
    wheat = Activity(name="Blé", workshop_id=0, cycle_start="10-01", cycle_stop="08-31", year_offset=1)
    assert analytic.campaign_year(wheat, date(2025, 10, 15)) == 2026
    assert analytic.campaign_year(wheat, date(2026, 8, 31)) == 2026
    assert analytic.campaign_year(wheat, date(2026, 9, 10)) == 2027              # entre deux cycles : campagne suivante
    civil = Activity(name="Maraîchage", workshop_id=0, cycle_start="01-01", cycle_stop="12-31", year_offset=0)
    assert analytic.campaign_year(civil, date(2026, 12, 31)) == 2026
    apple = Activity(name="Pommes", workshop_id=0, cycle_start="03-01", cycle_stop="06-30", year_offset=0)
    assert analytic.campaign_year(apple, date(2026, 7, 1)) == 2027
    leap = Activity(name="X", workshop_id=0, cycle_start="03-01", cycle_stop="02-29", year_offset=1)
    assert analytic.cycle_bounds(leap, 2027)[1] == date(2027, 2, 28)


def test_workshops_activities_measures(farm):
    client = farm
    workshop = _workshop(client)
    assert client.post("/api/v1/workshops", json={"name": "Vaches laitières", "family": "animal_farming"}).status_code == 409
    assert client.post("/api/v1/workshops", json={"name": "X", "family": "nope"}).status_code == 422
    resp = client.post("/api/v1/activities", json={"workshop_id": workshop["id"], "lexicon_reference": "milk_cow", "name": "Lait"})
    milk = resp.get_json()["item"]
    assert resp.status_code == 201 and milk["unit"] == "head" and milk["cycle_start"] == "09-01" and milk["year_offset"] == 1
    assert milk["cycle"] == "perennial" and milk["lexicon_name"] == "Vaches laitières"
    heifers = client.post("/api/v1/activities", json={"workshop_id": workshop["id"], "lexicon_reference": "dairy_heifer",
                                                      "name": "Génisses 1 an"}).get_json()["item"]
    assert client.post("/api/v1/activities", json={"workshop_id": workshop["id"], "name": "Lait"}).status_code == 409
    assert client.patch(f"/api/v1/activities/{milk['id']}", json={"cycle_start": "13-01"}).status_code == 422
    assert client.patch(f"/api/v1/activities/{milk['id']}", json={"year_offset": 0}).status_code == 422   # 09-01 > 08-31
    assert client.post("/api/v1/activities", json={"workshop_id": workshop["id"], "lexicon_reference": "zzz"}).status_code == 422
    body = client.put(f"/api/v1/activities/{milk['id']}/campaigns/2026", json={"measure": "62"}).get_json()["item"]
    client.put(f"/api/v1/activities/{heifers['id']}/campaigns/2026", json={"measure": "18,5"})
    assert client.put(f"/api/v1/activities/{milk['id']}/campaigns/2026", json={"measure": "-1"}).status_code == 422
    listing = client.get("/api/v1/workshops?campaign=2026").get_json()["item"]
    acts = {a["name"]: a for a in listing["workshops"][0]["activities"]}
    assert acts["Lait"]["campaign"]["measure"] == "62" and acts["Lait"]["campaign"]["start"] == "2025-09-01"
    assert listing["totals"] == [{"unit": "head", "unit_label": "têtes", "measure": "80.5"}]
    assert body["campaigns"] == [2026]
    copied = client.post("/api/v1/campaigns/2027/copy-measures").get_json()
    assert "2 mesure(s)" in copied["notices"][0]["message"]
    assert client.delete(f"/api/v1/workshops/{workshop['id']}").status_code == 409
    assert client.delete(f"/api/v1/activities/{heifers['id']}").status_code == 200
    client.patch(f"/api/v1/activities/{milk['id']}", json={"archived": True})
    assert client.get("/api/v1/workshops").get_json()["item"]["workshops"][0]["activities"] == []
    assert client.get("/api/v1/lexicon/productions?q=blé&family=plant_farming").get_json()["items"]


def test_not_agri(app, login_as):
    client = login_as(role="admin")
    assert client.get("/api/v1/workshops").status_code == 404


def _id(code):
    from app.models import Account
    return Account.query.filter_by(code=code).one().id


def test_keys_rules_allocations(farm):
    from decimal import Decimal

    from app.models import Account, FiscalYear, Journal
    from app.services import analytic_allocation as alloc
    from app.services.ledger import post_entry
    client = farm
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    od = Journal(code="OD", label="OD")
    parent = Account.query.filter_by(code="7011").one()
    db.session.add_all([fy, od, Account(code="70111", label="Ventes de blé", account_type=parent.account_type)])
    db.session.commit()

    def entry(debit, credit, cents, day=date(2026, 6, 30)):
        post_entry(fy.id, od.id, day, "x", [
            {"account_id": _id(debit), "label": "x", "debit_cents": cents, "credit_cents": 0},
            {"account_id": _id(credit), "label": "x", "debit_cents": 0, "credit_cents": cents}])
    entry("411", "70111", 5000000)
    entry("60111", "401", 1000000)
    entry("60614", "401", 200000)
    entry("6711", "401", 5000) if Account.query.filter_by(code="6711").first() else None
    crops = _workshop(client, "Grandes cultures", "plant_farming")
    dairy = _workshop(client)
    wheat = client.post("/api/v1/activities", json={"workshop_id": crops["id"], "lexicon_reference": "winter_common_wheat", "name": "Blé"}).get_json()["item"]
    corn = client.post("/api/v1/activities", json={"workshop_id": crops["id"], "name": "Maïs"}).get_json()["item"]
    milk = client.post("/api/v1/activities", json={"workshop_id": dairy["id"], "lexicon_reference": "milk_cow", "name": "Lait"}).get_json()["item"]
    client.put(f"/api/v1/activities/{wheat['id']}/campaigns/2026", json={"measure": "40"})
    client.put(f"/api/v1/activities/{corn['id']}/campaigns/2026", json={"measure": "60"})
    url = f"/api/v1/fiscal-years/{fy.id}/analytic"
    view = client.get(f"{url}/unallocated").get_json()["item"]
    assert view["suggestions"] == [{"account_prefix": "70111", "account_label": "Ventes de blé",
                                    "target": {"kind": "activity", "id": wheat["id"], "label": "Grandes cultures › Blé"}}]
    assert view["coverage"]["charges"]["ratio_bp"] == 0
    assert client.post("/api/v1/analytic-rules", json={"account_prefix": "70111", "activity_id": wheat["id"]}).status_code == 201
    assert client.post("/api/v1/analytic-rules", json={"account_prefix": "713", "activity_id": wheat["id"]}).status_code == 422
    key = client.post("/api/v1/analytic-keys", json={"name": "Surface cultures", "basis": "surface",
                                                     "members": [{"activity_id": wheat["id"]}, {"activity_id": corn["id"]}]}).get_json()["item"]
    assert key["warnings"] == []
    bad = client.post("/api/v1/analytic-keys", json={"name": "Mixte", "basis": "surface", "members": [{"activity_id": milk["id"]}]}).get_json()["item"]
    assert any("unité" in w for w in bad["warnings"])
    assert client.post("/api/v1/analytic-keys", json={"name": "P", "basis": "percentage", "members": [{"activity_id": milk["id"]}]}).status_code == 422
    view = client.get(f"{url}/unallocated?account=60111").get_json()["item"]
    (line,) = view["lines"]
    assert {g["account"] for g in view["groups"]} == {"60111", "60614"} and view["coverage"]["products"]["ratio_bp"] == 10000
    assert client.post(f"{url}/allocations", json={"line_ids": [line["id"]], "targets": [{"key_id": key["id"], "share_bp": 6000},
                                                                                        {"activity_id": milk["id"], "share_bp": 5000}]}).status_code == 422
    assert client.post(f"{url}/allocations", json={"line_ids": [line["id"]], "targets": [{"key_id": key["id"]}]}).status_code == 200
    view = client.get(f"{url}/unallocated").get_json()["item"]
    assert [g["account"] for g in view["groups"]] == ["60614"]
    assert view["coverage"]["charges"]["allocated_cents"] == 1000000
    from app.models import AnalyticKey
    parts = alloc.expand(None, db.session.get(AnalyticKey, key["id"]), date(2026, 6, 30))["parts"]
    assert {p["activity"]: p["share"] for p in parts} == {"Blé": Decimal("0.4"), "Maïs": Decimal("0.6")}
    late = alloc.expand(None, db.session.get(AnalyticKey, key["id"]), date(2026, 10, 15))   # blé : campagne 2027 sans mesure
    assert any("Blé" in w and "2027" in w for w in late["warnings"])
    gas = client.get(f"{url}/unallocated?account=60614").get_json()["item"]["lines"][0]
    client.post(f"{url}/allocations", json={"line_ids": [gas["id"]], "targets": [{"activity_id": corn["id"], "share_bp": 5000}]})
    group = client.get(f"{url}/unallocated").get_json()["item"]["groups"][0]
    assert group["partial"] == 1 and group["amount_cents"] == 100000
    assert client.post(f"{url}/allocations/clear", json={"line_ids": [gas["id"], line["id"]]}).status_code == 200
    assert len(client.get(f"{url}/unallocated").get_json()["item"]["groups"]) == 2
    other = client.post(f"{url}/allocations", json={"line_ids": [999999], "targets": [{"activity_id": corn["id"]}]})
    assert other.status_code == 422


def test_targets_on_sources(farm):
    """Lot AG8.c : affectation analytique saisie sur l'écriture, l'opération, la règle, l'aide et les fiches."""
    from app.models import (Account, AnalyticAllocation, BankAccount, BankTransaction, FiscalYear, Journal, JournalEntry)
    from app.services import rule_entries
    client = farm
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    db.session.add_all([fy, Journal(code="OD", label="OD"), Journal(code="BQ", label="Banque")])
    db.session.commit()
    crops = _workshop(client, "Grandes cultures", "plant_farming")
    corn = client.post("/api/v1/activities", json={"workshop_id": crops["id"], "name": "Maïs"}).get_json()["item"]
    target = f"activity:{corn['id']}"
    od = Journal.query.filter_by(code="OD").one()
    payload = {"fiscal_year_id": fy.id, "journal_id": od.id, "entry_date": "2026-03-01", "description": "Engrais",
               "lines": [{"account_id": _id("60111"), "debit_cents": 1000, "analytic": target},
                         {"account_id": _id("401"), "credit_cents": 1000, "analytic": target}]}
    assert client.post("/api/v1/entries", json={**payload, "lines": [{**payload["lines"][0], "analytic": "activity:999"},
                                                                     payload["lines"][1]]}).status_code == 422
    entry_id = client.post("/api/v1/entries", json=payload).get_json()["id"]
    rows = AnalyticAllocation.query.all()
    assert len(rows) == 1 and rows[0].activity_id == corn["id"] and rows[0].origin == "manual"     # 401 ignoré
    lines = client.get(f"/api/v1/entries/{entry_id}").get_json()
    lines = lines.get("lines") or lines.get("item", {}).get("lines")
    assert [l["analytic"] for l in lines] == [target, None]
    payload["lines"][0].pop("analytic")
    assert client.put(f"/api/v1/entries/{entry_id}", json=payload).status_code == 200
    assert AnalyticAllocation.query.count() == 0
    # règle bancaire
    bank = BankAccount(label="CIC", account_id=_id("512"))
    db.session.add(bank)
    db.session.commit()
    tx = BankTransaction(bank_account_id=bank.id, fitid="R1", transaction_date=date(2026, 4, 2), amount_cents=-5000, label="GAZOLE")
    db.session.add(tx)
    db.session.commit()
    document, _settlement = rule_entries.post(tx, Account.query.filter_by(code="60614").one(), "Gazole", analytic=target)
    db.session.commit()
    (row,) = AnalyticAllocation.query.all()
    assert row.origin == "rule" and row.journal_line.entry_id == document.id
    resp = client.post("/api/v1/rules", json={"name": "Gazole", "label_contains": "GAZOLE", "account_code": "60614", "analytic": target})
    assert resp.status_code in (200, 201) and resp.get_json()["item"]["analytic"] == target
    # aide et fiches
    aid = client.post("/api/v1/aids", json={"scheme": "dja", "campaign": 2026, "notified_cents": 100, "analytic": target}).get_json()["item"]
    assert aid["analytic"] == target and aid["analytic_label"] == "Grandes cultures › Maïs"
    assert client.post("/api/v1/aids", json={"scheme": "dja", "campaign": 2026, "analytic": "x:1"}).status_code == 422
    asset = client.post("/api/v1/assets", json={"label": "Semoir", "account_id": _id("2154"), "acquired_on": "2026-01-01",
                                                "in_service_date": "2026-01-01", "acquisition_cents": 100000, "method": "linear",
                                                "duration_months": 60, "activity_id": corn["id"]}).get_json()["item"]
    assert asset["activity"] == "Grandes cultures › Maïs"
    assert JournalEntry.query.count() >= 2


def test_gross_margins(farm):
    """Lot AG8.d : marge par activité (RICA), clé à la surface, 6051 selon la famille, stocks, amortissements."""
    from app.models import Account, AnalyticAllocation, FiscalYear, Journal, JournalLine
    from app.services import analytic_margins
    from app.services.ledger import post_entry
    client = farm
    prev = FiscalYear(label="2025", start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    od = Journal(code="OD", label="OD")
    parent = Account.query.filter_by(code="7011").one()
    db.session.add_all([prev, fy, od, Account(code="70111", label="Ventes de blé", account_type=parent.account_type)])
    db.session.commit()
    crops = _workshop(client, "Grandes cultures", "plant_farming")
    dairy = _workshop(client)
    wheat = client.post("/api/v1/activities", json={"workshop_id": crops["id"], "name": "Blé"}).get_json()["item"]
    corn = client.post("/api/v1/activities", json={"workshop_id": crops["id"], "name": "Maïs"}).get_json()["item"]
    milk = client.post("/api/v1/activities", json={"workshop_id": dairy["id"], "name": "Lait", "unit": "head"}).get_json()["item"]
    for act, m in ((wheat, "40"), (corn, "60"), (milk, "50")):
        client.put(f"/api/v1/activities/{act['id']}/campaigns/2026", json={"measure": m})
    key = client.post("/api/v1/analytic-keys", json={"name": "Cultures", "basis": "surface",
                                                     "members": [{"activity_id": wheat["id"]}, {"activity_id": corn["id"]}]}).get_json()["item"]
    client.post("/api/v1/analytic-rules", json={"account_prefix": "70111", "activity_id": wheat["id"]})

    def entry(debit, credit, cents, target=None):
        e = post_entry(fy.id, od.id, date(2026, 6, 30), "x", [
            {"account_id": _id(debit), "label": "x", "debit_cents": cents, "credit_cents": 0, "analytic": target},
            {"account_id": _id(credit), "label": "x", "debit_cents": 0, "credit_cents": cents, "analytic": target}])
        return e
    entry("411", "70111", 5000000)                                           # règle → Blé
    entry("60111", "401", 1000000, f"key:{key['id']}")                       # clé surface 40 / 60
    entry("60114", "401", 300000, f"activity:{milk['id']}")
    entry("60117", "401", 200000, f"activity:{milk['id']}")                  # achats d'animaux
    entry("6051", "401", 100000, f"activity:{milk['id']}")                   # → spécifiques animaux
    entry("6051", "401", 50000, f"activity:{wheat['id']}")                   # → spécifiques végétaux
    entry("60614", "401", 200000)                                            # non affecté
    entry("512", "745", 500000, f"activity:{corn['id']}")                    # aide
    url_prev, url = f"/api/v1/fiscal-years/{prev.id}/stock/lines", f"/api/v1/fiscal-years/{fy.id}/stock/lines"
    for u, value in ((url_prev, 1000000), (url, 1500000)):
        resp = client.post(u, json={"account_code": "35511", "label": "Blé", "quantity": "1", "unit": "t", "method": "actual",
                                    "unit_value_cents": value, "activity_id": wheat["id"]})
        assert resp.status_code == 201, resp.get_json()
    data = client.get(f"/api/v1/fiscal-years/{fy.id}/activity-margins").get_json()["item"]
    rows = {r["activity"]: r for r in data["productions"]}
    blé, maïs, lait = rows["Blé"], rows["Maïs"], rows["Lait"]
    assert blé["classes"]["sales"] == 5000000 and blé["classes"]["stock_production"] == 500000
    assert blé["classes"]["plant_specific"] == 400000 + 50000 and blé["gross_margin_cents"] == 5500000 - 450000
    assert blé["gross_margin_per_unit_cents"] == round((5500000 - 450000) / 40)
    assert maïs["classes"]["plant_specific"] == 600000 and maïs["classes"]["aids"] == 500000 and maïs["gross_margin_cents"] == -100000
    assert lait["production_cents"] == -200000 and lait["classes"]["animal_specific"] == 400000
    assert data["unallocated"]["classes"]["structure"] == 200000
    ws = {w["workshop"]: w for w in data["workshops"]}
    assert ws["Grandes cultures"]["gross_margin_cents"] == blé["gross_margin_cents"] + maïs["gross_margin_cents"]
    assert ws["Grandes cultures"]["measure"] == "100"
    assert analytic_margins.account_class("6051", "animal_farming") == "animal_specific"
    assert analytic_margins.account_class("6711") is None
    assert client.get(f"/fiscal-years/{fy.id}/activity-margins.xlsx").status_code == 200
    assert client.get(f"/fiscal-years/{fy.id}/activity-margins.pdf").status_code == 200
    assert JournalLine.query.count() and AnalyticAllocation.query.count() == 6


def test_auxiliaries_reconciliation_freeze(farm):
    """Lot AG8.e : auxiliaire répartie, clé à la marge brute, rapprochement, contrôles, figement à la clôture."""
    from app.models import Account, FiscalYear, Journal
    from app.services import analytic_margins
    from app.services.ledger import post_entry
    client = farm
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    od = Journal(code="OD", label="OD")
    db.session.add_all([fy, od])
    db.session.commit()
    crops = _workshop(client, "Grandes cultures", "plant_farming")
    common = _workshop(client, "Commun", "tool_maintaining")
    wheat = client.post("/api/v1/activities", json={"workshop_id": crops["id"], "name": "Blé"}).get_json()["item"]
    corn = client.post("/api/v1/activities", json={"workshop_id": crops["id"], "name": "Maïs"}).get_json()["item"]
    for act, m in ((wheat, "40"), (corn, "60")):
        client.put(f"/api/v1/activities/{act['id']}/campaigns/2026", json={"measure": m})
    surface = client.post("/api/v1/analytic-keys", json={"name": "Surface", "basis": "surface",
                                                         "members": [{"activity_id": wheat["id"]}, {"activity_id": corn["id"]}]}).get_json()["item"]
    margin = client.post("/api/v1/analytic-keys", json={"name": "Marge", "basis": "gross_margin",
                                                        "members": [{"activity_id": wheat["id"]}, {"activity_id": corn["id"]}]}).get_json()["item"]
    tools = client.post("/api/v1/activities", json={"workshop_id": common["id"], "name": "Matériel", "nature": "auxiliary",
                                                    "distribution_key_id": surface["id"]}).get_json()["item"]
    assert tools["distribution_key"] == "Surface"
    assert client.post("/api/v1/activities", json={"workshop_id": common["id"], "name": "X", "distribution_key_id": 999}).status_code == 422

    def entry(debit, credit, cents, target=None):
        post_entry(fy.id, od.id, date(2026, 6, 30), "x", [
            {"account_id": _id(debit), "label": "x", "debit_cents": cents, "credit_cents": 0, "analytic": target},
            {"account_id": _id(credit), "label": "x", "debit_cents": 0, "credit_cents": cents, "analytic": target}])
    entry("411", "7011", 3000000, f"activity:{wheat['id']}")
    entry("411", "7011", 1000000, f"activity:{corn['id']}")
    entry("60614", "401", 500000, f"activity:{tools['id']}")              # gazole : auxiliaire
    entry("6226", "401", 200000, f"key:{margin['id']}")                    # honoraires à la marge brute (3/4, 1/4)
    entry("6131", "401", 100000)                                           # fermage non affecté
    data = client.get(f"/api/v1/fiscal-years/{fy.id}/activity-margins").get_json()["item"]
    rows = {r["activity"]: r for r in data["productions"]}
    assert rows["Matériel"]["auxiliary_cents"] == 500000 and rows["Matériel"]["result_after_cents"] == 0
    assert rows["Blé"]["auxiliary_cents"] == -200000 and rows["Maïs"]["auxiliary_cents"] == -300000
    assert rows["Blé"]["classes"]["structure"] == 150000 and rows["Maïs"]["classes"]["structure"] == 50000
    assert rows["Blé"]["result_after_cents"] == 3000000 - 150000 - 200000
    rec = data["reconciliation"]
    assert rec["accounting_result_cents"] == 4000000 - 800000
    assert rec["activities_cents"] + rec["unallocated_cents"] + rec["excluded_cents"] + rec["method_gap_cents"] == rec["accounting_result_cents"]
    assert rec["method_gap_cents"] == 0 and rec["unallocated_cents"] == -100000
    keys = {k for k, *_ in analytic_margins.checks(fy)}
    assert "analytic_coverage_charges" not in keys and "analytic_measures" not in keys
    fy.status = "closed"
    db.session.commit()
    frozen = client.get(f"/api/v1/fiscal-years/{fy.id}/activity-margins").get_json()["item"]
    assert frozen["frozen"] is True
    fy.status = "open"
    db.session.commit()
    assert client.get(f"/api/v1/fiscal-years/{fy.id}/activity-margins").get_json()["item"]["frozen"] is False
