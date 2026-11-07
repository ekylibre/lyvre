"""Lot AG7.a : assiette sociale MSA des non-salariés agricoles (claudedocs/design_msa.md § 3, AGD24)."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, FiscalYear, Instance, Journal, ShareMovement, ShareMovementLine
from app.services import agri_profile, associates, msa
from app.services.ledger import post_entry
from test_agri_fixtures import _agri_instance


def _id(code):
    return Account.query.filter_by(code=code).one().id


def _entry(fy, od, debit, credit, cents):
    post_entry(fy.id, od.id, date(fy.end_date.year, 6, 30), "x", [
        {"account_id": _id(debit), "label": "x", "debit_cents": cents, "credit_cents": 0},
        {"account_id": _id(credit), "label": "x", "debit_cents": 0, "credit_cents": cents}])


@pytest.fixture()
def farm(app, login_as):
    client = login_as(role="admin")
    _agri_instance()
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    od = Journal(code="OD", label="OD")
    db.session.add_all([fy, od])
    db.session.commit()
    from app.services import organization
    organization.get().legal_form_code = "EI"
    db.session.commit()
    _entry(fy, od, "411", "7011", 4000000)
    return {"client": client, "fy": fy, "od": od, "url": f"/api/v1/fiscal-years/{fy.id}"}


def test_abatement_bounds(farm):
    assert msa.abatement(5000000, 2026)["amount_cents"] == 1300000                     # 26 %
    low = msa.abatement(-100000, 2026)                                                  # déficit : plancher (Q-M3)
    assert low["amount_cents"] == 84586 and low["bound"] == "plancher"
    high = msa.abatement(30000000, 2026)
    assert high["amount_cents"] == 6247800 and high["bound"] == "plafond"              # 130 % de 48 060 €
    assert "PASS 2027 non paramétré" in msa.abatement(5000000, 2026)["warning"]


def test_individual_farmer(farm):
    client, url, fy, od = farm["client"], farm["url"], farm["fy"], farm["od"]
    _entry(fy, od, "646", "4311", 800000)
    client.post(f"{url}/tax-result/lines", json={"kind": "csg", "label": "CSG non déductible", "amount_cents": 70000})
    body = client.get(f"{url}/msa").get_json()["item"]
    (person,) = body["people"]
    assert person["fiscal_result_cents"] == 3270000                                     # 40 000 − 8 000 + 700
    lines = {l["key"]: l["amount_cents"] for l in person["lines"]}
    assert lines == {"contributions": 730000}
    assert person["income_cents"] == 4000000 and person["abatement"]["amount_cents"] == 1040000
    assert person["base_cents"] == 2960000
    pid = person["person"]["id"]
    assert client.post(f"{url}/msa/adjustments", json={"person_id": pid, "kind": "add", "amount_cents": 100}).status_code == 422
    resp = client.post(f"{url}/msa/adjustments", json={"person_id": pid, "kind": "avaloir", "amount_cents": 100000})
    assert resp.status_code == 201
    person = resp.get_json()["item"]["people"][0]
    assert person["income_cents"] == 4100000
    assert client.patch(f"/api/v1/msa/people/{pid}", json={"base_option": "annual", "option_since": "2026-01-01"}).status_code == 200
    adj = [l for l in person["lines"] if l.get("id")][0]
    assert client.delete(f"{url}/msa/adjustments/{adj['id']}").status_code == 200


def test_ja_dja_and_blocked_stock(farm):
    client, url = farm["client"], farm["url"]
    agri_profile.save({"young_farmer_since": "2024-03-01"})
    db.session.commit()
    client.post("/api/v1/aids", json={"scheme": "dja", "campaign": 2026, "notified_cents": 3000000,
                                      "investment_share_cents": 2000000, "decision_on": "2025-03-01"})
    person = client.get(f"{url}/msa").get_json()["item"]["people"][0]
    lines = {l["key"]: l["amount_cents"] for l in person["lines"]}
    assert lines == {"ja": 3000000}                                                    # JA réintégré, DJA d'un autre exercice
    assert person["income_cents"] == 4000000
    client.post("/api/v1/aids", json={"scheme": "dja", "campaign": 2026, "notified_cents": 3000000,
                                      "investment_share_cents": 2000000, "decision_on": "2026-03-01"})
    assert msa._dja(farm["fy"])[0] == 1000000                                         # part d'exploitation (744)
    person = client.get(f"{url}/msa").get_json()["item"]["people"][0]
    assert {l["key"]: l["amount_cents"] for l in person["lines"]}["dja"] == -1000000


def test_company_operators(farm):
    client, url = farm["client"], farm["url"]
    Instance.query.one().has_associates = True
    db.session.commit()
    from app.services import organization
    organization.get().legal_form_code = "GAEC"
    paul, parent = (associates.create({"new_name": n}) for n in ("Paul", "Parent"))
    db.session.add(ShareMovement(movement_date=date(2026, 1, 1), kind="opening", nominal_cents=1000, lines=[
        ShareMovementLine(associate_id=paul.id, nature="full", parts=600),
        ShareMovementLine(associate_id=parent.id, nature="full", parts=400)]))
    db.session.commit()
    client.patch(f"/api/v1/associates/{paul.id}", json={"is_operator": True, "young_farmer_since": "2024-03-01"})
    _entry(farm["fy"], farm["od"], "646", "4311", 500000)                 # ignoré en société (cotisations en 455, Q-M2)
    body = client.get(f"{url}/msa").get_json()["item"]
    (person,) = body["people"]
    assert person["person"]["name"] == "Paul" and person["share_bp"] == 6000
    assert {l["key"]: l["amount_cents"] for l in person["lines"]} == {"ja": 1575000}
    assert person["income_cents"] == person["fiscal_result_cents"] + 1575000
    assert any("non exploitants" in w and "Parent" in w for w in body["warnings"])
    assert any("455" in w for w in body["warnings"])


def test_before_reform(farm):
    fy = FiscalYear(label="2024", start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
    db.session.add(fy)
    db.session.commit()
    body = farm["client"].get(f"/api/v1/fiscal-years/{fy.id}/msa").get_json()["item"]
    assert body["people"] == [] and "ancienne assiette" in body["reason"]
    assert farm["client"].get(f"/fiscal-years/{farm['fy'].id}/msa.xlsx").status_code == 200


def test_history_and_comparison(farm):
    client, url = farm["client"], farm["url"]
    person = client.get(f"{url}/msa").get_json()["item"]["people"][0]
    pid = person["person"]["id"]
    comp = person["comparison"]
    assert comp["contribution_year"] == 2027 and comp["missing"] == [2025, 2024] and comp["triennial_cents"] is None
    assert comp["annual_cents"] == person["base_cents"] == 2960000                    # 40 000 − 10 400
    assert any("Expérimentation" in n for n in comp["notes"]) and any("2024" in n and "reconstituée" in n for n in comp["notes"])
    assert client.put(f"/api/v1/msa/people/{pid}/bases/2025", json={"base_cents": 1500000, "note": "avis MSA"}).status_code == 200
    assert client.put(f"/api/v1/msa/people/{pid}/bases/2024", json={"base_cents": 1460000}).status_code == 200
    assert client.put(f"/api/v1/msa/people/{pid}/bases/2023", json={"base_cents": "x"}).status_code == 422
    comp = client.get(f"{url}/msa").get_json()["item"]["people"][0]["comparison"]
    assert comp["triennial_cents"] == 1973333 and comp["best"] == "triennial" and comp["retained_cents"] == 1973333
    assert comp["option"]["deadline"] == "2027-06-30"
    client.patch(f"/api/v1/msa/people/{pid}", json={"base_option": "annual", "option_since": "2024-01-01"})
    item = client.get(f"{url}/msa").get_json()["item"]["people"][0]
    assert item["comparison"]["retained_cents"] == 2960000 and item["comparison"]["option"]["commitment_end"] == "2028-12-31"
    assert [h["year"] for h in item["history"]] == [2025, 2024]
    assert client.delete(f"/api/v1/msa/people/{pid}/bases/2024").status_code == 200
    # assiette figée à la clôture : non modifiable
    from app.models import MsaBase
    db.session.add(MsaBase(person_id=pid, year=2022, source="lyvre", base_cents=1))
    db.session.commit()
    assert client.put(f"/api/v1/msa/people/{pid}/bases/2022", json={"base_cents": 5}).status_code == 409


def test_calls_register(farm):
    from app.models import BankAccount, BankTransaction, MsaBase
    client, url = farm["client"], farm["url"]
    pid = client.get(f"{url}/msa").get_json()["item"]["people"][0]["person"]["id"]
    for year, base in ((2023, 2000000), (2024, 2000000), (2025, 2000000)):
        db.session.add(MsaBase(person_id=pid, year=year, source="entered", base_cents=base))
    db.session.commit()
    resp = client.post("/api/v1/msa/calls", json={"person_id": pid, "kind": "first", "due_on": "2026-04-28",
                                                   "amount_cents": 300000, "base_cents": 3000000})
    assert resp.status_code == 201
    client.post("/api/v1/msa/calls", json={"person_id": pid, "kind": "balance", "due_on": "2026-12-08", "amount_cents": 500000,
                                           "contributions_cents": 400000, "csg_deductible_cents": 70000,
                                           "csg_crds_non_deductible_cents": 30000})
    bad = client.post("/api/v1/msa/calls", json={"person_id": pid, "kind": "second", "due_on": "2026-10-13", "amount_cents": 100,
                                                  "csg_deductible_cents": 200})
    assert bad.status_code == 422
    view = client.get("/api/v1/msa/calls?year=2026").get_json()["item"]
    (person,) = view["people"]
    assert person["retained_base_cents"] == 2000000 and person["totals"]["amount_cents"] == 800000
    first = person["calls"][0]
    prop = first["proposal"]                                   # 6,8 % et 2,9 % de 20 000 € × 3 000 / 8 000
    assert prop["available"] and prop["csg_deductible_cents"] == 51000 and prop["csg_crds_non_deductible_cents"] == 21750
    assert person["calls"][1]["proposal"] is None
    body = client.post(f"/api/v1/msa/calls/{first['id']}/estimate").get_json()["item"]
    first = body["people"][0]["calls"][0]
    assert first["estimated"] and first["contributions_cents"] == 300000 - 51000 - 21750
    # paiement
    bank = BankAccount(label="CIC", account_id=_id("512"))
    db.session.add(bank)
    db.session.commit()
    tx = BankTransaction(bank_account_id=bank.id, fitid="M1", transaction_date=date(2026, 4, 28), amount_cents=-300000,
                         label="PRLV MSA NORD")
    db.session.add(tx)
    db.session.commit()
    cands = client.get(f"/api/v1/msa/calls/{first['id']}/candidates").get_json()["items"]
    assert cands[0]["id"] == tx.id and cands[0]["amount_matches"]
    body = client.put(f"/api/v1/msa/calls/{first['id']}/payment", json={"bank_transaction_id": tx.id}).get_json()["item"]
    assert body["people"][0]["totals"]["paid_cents"] == 300000
    balance = body["people"][0]["calls"][1]
    assert client.put(f"/api/v1/msa/calls/{balance['id']}/payment", json={"bank_transaction_id": tx.id}).status_code == 409
    assert client.delete(f"/api/v1/msa/calls/{balance['id']}").status_code == 200


def test_monthly_and_modulation(farm):
    from app.models import MsaBase
    from app.services import msa_calls
    client, url = farm["client"], farm["url"]
    pid = client.get(f"{url}/msa").get_json()["item"]["people"][0]["person"]["id"]
    assert client.post("/api/v1/msa/calls/monthly", json={"person_id": pid, "year": 2026}).status_code == 422
    client.post("/api/v1/msa/calls", json={"person_id": pid, "kind": "single", "due_on": "2025-10-15", "amount_cents": 1100005})
    body = client.post("/api/v1/msa/calls/monthly", json={"person_id": pid, "year": 2026}).get_json()["item"]
    calls = body["people"][0]["calls"]
    assert len(calls) == 11 and calls[0]["amount_cents"] == 100000 and calls[-1]["amount_cents"] == 100005
    assert calls[0]["due_on"] == "2026-01-05" and all(c["estimated"] for c in calls)
    assert client.post("/api/v1/msa/calls/monthly", json={"person_id": pid, "year": 2026}).status_code == 409
    # modulation : assiette de l'avis 30 000 €, moyenne des revenus 15 000 €
    for year in (2023, 2024, 2025):
        db.session.add(MsaBase(person_id=pid, year=year, source="entered", base_cents=1500000))
    db.session.commit()
    client.patch(f"/api/v1/msa/calls/{calls[-1]['id']}", json={"base_cents": 3000000})
    view = msa_calls.listing(2026, today=date(2026, 9, 1))
    assert any("modulation possible" in w and "21/10/2026" in w for w in view["warnings"])


def test_ventilation_individual(farm):
    from app.models import BankAccount, BankTransaction
    from app.services import closing
    client, url, fy, od = farm["client"], farm["url"], farm["fy"], farm["od"]
    pid = client.get(f"{url}/msa").get_json()["item"]["people"][0]["person"]["id"]
    first = client.post("/api/v1/msa/calls", json={"person_id": pid, "kind": "first", "due_on": "2026-04-28", "amount_cents": 300000,
                                                    "csg_deductible_cents": 40000, "csg_crds_non_deductible_cents": 21750}).get_json()
    client.post("/api/v1/msa/calls", json={"person_id": pid, "kind": "balance", "due_on": "2026-12-08", "amount_cents": 500000,
                                           "csg_deductible_cents": 60000, "csg_crds_non_deductible_cents": 30000})
    bank = BankAccount(label="CIC", account_id=_id("512"))
    db.session.add(bank)
    db.session.commit()
    tx = BankTransaction(bank_account_id=bank.id, fitid="M1", transaction_date=date(2026, 4, 28), amount_cents=-300000, label="PRLV MSA")
    db.session.add(tx)
    db.session.commit()
    call_id = first["item"]["people"][0]["calls"][0]["id"]
    client.put(f"/api/v1/msa/calls/{call_id}/payment", json={"bank_transaction_id": tx.id})
    _entry(fy, od, "646", "512", 300000)
    tr = client.get(f"{url}/tax-result").get_json()["item"]
    (line,) = [l for l in tr["lines"] if l["source"] == "msa"]
    assert line["amount_cents"] == 51750
    vent = client.get(f"{url}/msa/ventilation").get_json()["item"]
    assert vent["mode"] == "ei" and vent["accrual"]["amount_cents"] == 500000
    assert {c["key"] for c in vent["checks"]} == {"msa_646", "msa_accrual"}
    assert client.post(f"{url}/msa/accrual").status_code == 201
    assert client.post(f"{url}/msa/accrual").status_code == 409
    vent = client.get(f"{url}/msa/ventilation").get_json()["item"]
    assert vent["checks"] == [] and vent["accrual"]["entry"]["amount_cents"] == 500000
    person = client.get(f"{url}/msa").get_json()["item"]["people"][0]
    assert {l["key"]: l["amount_cents"] for l in person["lines"]}["contributions"] == 800000 - 51750
    client.post(f"{url}/tax-result/lines", json={"kind": "csg", "label": "CSG", "amount_cents": 100})
    assert any("supprimez la ligne saisie" in w for w in client.get(f"{url}/tax-result").get_json()["item"]["warnings"])
    assert any(c.key == "msa_646" for c in closing.checks(fy)) is False
    assert client.delete(f"{url}/msa/accrual").status_code == 200


def test_ventilation_company(farm):
    client, url = farm["client"], farm["url"]
    Instance.query.one().has_associates = True
    db.session.commit()
    from app.services import organization
    organization.get().legal_form_code = "GAEC"
    paul = associates.create({"new_name": "Paul"})
    db.session.add(ShareMovement(movement_date=date(2026, 1, 1), kind="opening", nominal_cents=1000, lines=[
        ShareMovementLine(associate_id=paul.id, nature="full", parts=100)]))
    db.session.commit()
    client.patch(f"/api/v1/associates/{paul.id}", json={"is_operator": True})
    pid = client.get(f"{url}/msa").get_json()["item"]["people"][0]["person"]["id"]
    client.post("/api/v1/msa/calls", json={"person_id": pid, "kind": "single", "due_on": "2026-10-13", "amount_cents": 500000,
                                           "csg_deductible_cents": 60000, "csg_crds_non_deductible_cents": 30000})
    vent = client.get(f"{url}/msa/ventilation").get_json()["item"]
    assert vent["mode"] == "company" and vent["tax_lines"] == [] and vent["accrual"] is None
    (row,) = vent["associates"]
    assert row["deductible_cents"] == 470000 and row["non_deductible_cents"] == 30000
    assert client.post(f"{url}/msa/accrual").status_code == 422
    assert all(l["source"] != "msa" for l in client.get(f"{url}/tax-result").get_json()["item"]["lines"])


def test_estimate_lines(farm):
    from app.services import msa_estimate
    est = msa_estimate.estimate(3000000, 2026, "principal", "A")                       # 30 000 € d'assiette
    lines = {l["key"]: l["amount_cents"] for l in est["lines"]}
    # AMEXA : 30 000 € = 62,42 % du PASS → 4 % + 2,5 % × (30 000 − 28 836) / 24 030
    assert lines["amexa"] == round(3000000 * (400 + 250 * (3000000 - 2883600) / 2403000) / 10000)
    assert lines["invalidity"] == 33000 and lines["ij"] == 25000
    assert lines["pension_capped"] == 514500 and lines["pension_uncapped"] == 21600
    assert lines["rco"] == 120000                                                       # 4 % de 30 000 (≥ 1 820 SMIC)
    assert lines["pfa"] == 0 and lines["atexa"] == 52773
    assert lines["csg_deductible"] == 204000 and lines["csg_non_deductible"] == 72000 and lines["crds"] == 15000
    assert lines["vivea"] == 18300 and lines["fmse"] == 2000
    assert est["totals"]["non_deductible_cents"] == 87000 and est["warnings"] == []
    low = {l["key"]: l["amount_cents"] for l in msa_estimate.estimate(-100000, 2026, "principal")["lines"]}
    assert low["amexa"] == 0 and low["rco"] == round(1820 * 1202 * 4 / 100) and low["vivea"] == round(4806000 * 17 / 10000)
    assert "atexa" not in low
    high = {l["key"]: l["amount_cents"] for l in msa_estimate.estimate(20000000, 2026, "secondary", "C")["lines"]}
    assert high["pfa"] == round(20000000 * 310 / 10000) and high["pension_capped"] == round(4806000 * 1415 / 10000)
    assert "invalidity" not in high
    later = msa_estimate.estimate(3000000, 2027, "principal", "A")
    assert later["available"] and "barème 2026 appliqué" in later["warnings"][0]
    assert msa_estimate.estimate(3000000, 2026, "collaborator")["available"] is True        # lot CG5.f
    assert msa_estimate.estimate(3000000, 2026, "unknown")["available"] is False


def test_estimate_in_view(farm):
    from app.models import MsaBase
    client, url = farm["client"], farm["url"]
    pid = client.get(f"{url}/msa").get_json()["item"]["people"][0]["person"]["id"]
    for year in (2024, 2025):
        db.session.add(MsaBase(person_id=pid, year=year, source="entered", base_cents=2960000))
    db.session.commit()
    assert client.patch(f"/api/v1/msa/people/{pid}", json={"atexa_category": "Z"}).status_code == 422
    client.patch(f"/api/v1/msa/people/{pid}", json={"atexa_category": "B"})
    est = client.get(f"{url}/msa").get_json()["item"]["people"][0]["estimate"]
    assert est["available"] and est["year"] == 2027 and est["base_cents"] == 2960000
    assert any(l["key"] == "atexa" and l["amount_cents"] == 55095 for l in est["lines"])


def test_triennial_average_then_abatement_cg3c(farm):
    """Lot CG3.c (Q4, design_fiabilisation_cegara.md § 6.3) : moyenne des revenus, puis abattement de 26 % borné.
    Revenus 0, 0 et 90 000 € : moyenne 30 000 €, abattement 7 800 € → 22 200 € (21 636,09 € année par année)."""
    from app.models.msa import MsaBase, MsaPerson
    person = MsaPerson(status="principal")
    db.session.add(person)
    db.session.flush()
    for year in (2024, 2025):
        db.session.add(MsaBase(person_id=person.id, year=year, source="entered", income_cents=0, base_cents=-84586))
    db.session.commit()
    comp = msa.comparison(person, 2026, 6660000, current_income=9000000)
    assert comp["triennial_cents"] == 2220000 and comp["annual_cents"] == 6660000
    MsaBase.query.filter_by(person_id=person.id, year=2024).one().income_cents = None    # assiette de l'avis seule
    db.session.commit()
    comp = msa.comparison(person, 2026, 6660000, current_income=9000000)
    assert comp["triennial_cents"] == round((6660000 - 2 * 84586) / 3)                    # repli : moyenne des assiettes
    assert any("Revenu 2024 inconnu" in n for n in comp["notes"])


def test_micro_ba_has_no_computed_base_cg3c(farm):
    from app.models import TaxProfile
    db.session.add(TaxProfile(kind="ba_regime", value="micro", start_date=date(2025, 1, 1), origin="law"))
    db.session.commit()
    body = farm["client"].get(f"{farm['url']}/msa").get_json()["item"]
    assert body["people"] == [] and "Micro-BA" in body["reason"] and "87 %" in body["reason"]


def test_collaborator_estimate_cg5f(farm):
    """Lot CG5.f (barème NSA 2026) : collaborateur sur assiettes forfaitaires. SMIC 12,02 € : 600 SMIC = 7 212 €,
    1 200 SMIC = 14 424 € ; PASS 48 060 €."""
    from app.services import calculators, msa_estimate
    data = msa_estimate.estimate(None, 2026, "collaborator", "A")
    lines = {l["key"]: l["amount_cents"] for l in data["lines"]}
    assert lines == {"pension": 107242, "rco": 57696, "invalidity": 4100, "ij": 25000, "atexa": 20307, "vivea": 8170}
    assert data["totals"]["csg_crds_cents"] == 0 and any("SOC-06" in w for w in data["warnings"])
    second = msa_estimate.collaborator(2026, "A", secondary=True)
    assert {l["key"]: l["amount_cents"] for l in second["lines"]}["pension"] == 94117 and "ij" not in {
        l["key"] for l in second["lines"]}                                       # 13,05 % ; pas d'IJ
    module = calculators.get("msa")
    result = calculators.run(module, {"year": "2026", "status": "collaborator", "atexa": "A"})
    assert result["headline"][0]["value"].replace(" ", " ") == "2 225,15 €"
    with pytest.raises(calculators.CalculatorError):
        calculators.run(module, {"year": "2026", "status": "principal"})
