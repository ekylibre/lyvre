"""Lot AG1.b : référentiel « Exploitation agricole » (plan PCG 2026 + titre 5 du Recueil 2026), correspondance
PCGA 1986, énumérations des plans, comptes par défaut, comptabilité simplifiée ouverte aux exploitations, création
d'une instance agri (claudedocs/design_compta_agricole.md § 2, § 3.5, § 8, § 9)."""
import json
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from app.extensions import db
from app.menu_config import ALL_CHARTS, build_nav
from app.models import FiscalYear, Instance, Organization, SimpleCategory, TaxProfile
from app.services import account_roles, agri_chart, external_config, instance_provisioning, simple_categories
from seed_accounts import CHARTS as SEED_CHARTS, detect_chart, load_chart

ROOT = Path(__file__).resolve().parents[1]
AGRI = {a["code"]: a for a in load_chart("agri")}

# Comptes de l'art. 131-1 du titre 5 (relevés à la main dans le Recueil 2026, pages 630 à 634).
TITLE5 = ["1641", "1642", "1643", "172", "2071", "2121", "2125", "217", "2341", "2343", "2346", "2347", "241", "243",
          "246", "247", "2621", "2622", "2624", "2628", "2672", "26721", "26728", "2715", "2723", "284", "294",
          "2962", "31111", "31116", "3112", "3113", "31141", "31142", "31148", "31151", "31158", "33111", "33126",
          "35113", "35513", "402", "412", "4311", "4552", "45582", "461", "472", "4952", "4954", "497", "60111",
          "60117", "6051", "60615", "6131", "6134", "6144", "6348", "64116", "64117", "6451", "68114", "68164",
          "7011", "7012", "7013", "7014", "7041", "7042", "713311", "713312", "713551", "713554", "7221", "7222",
          "724", "73", "741", "742", "743", "744", "745", "748"]


def test_chart_contains_title5_and_pcg():
    for code in TITLE5 + ["101", "120", "129", "401", "411", "44566", "44571", "512", "6811"]:
        assert code in AGRI, code
    assert [a["code"] for a in AGRI.values() if a["is_header"]] == list("1234567")
    assert all(a["label"] and len(a["label"]) <= 255 for a in AGRI.values())
    assert len(AGRI) == len(load_chart("agri"))  # pas de doublon
    types = {"1": "EQUITY", "2": "ASSET", "3": "ASSET", "4": "TIERS", "5": "ASSET", "6": "EXPENSE", "7": "REVENUE"}
    assert all(a["account_type"] == types[a["code"][0]] for a in AGRI.values())


def test_title5_labels_win_and_decisions_applied():
    assert AGRI["741"]["label"] == "Remboursement forfaitaire de TVA"
    assert AGRI["742"]["label"] == "Indemnités liées à la production agricole"
    assert AGRI["7014"]["label"] == "Ventes d'animaux" and AGRI["7012"]["label"] == "Ventes de produits animaux"
    assert AGRI["6451"]["label"] == "Cotisations à la Mutualité Sociale Agricole"
    assert AGRI["7571"]["label"] == "Produits de cessions des biens vivants immobilisés"
    assert {"7578", "6571", "6578"} <= AGRI.keys()
    assert AGRI["757"]["label"].startswith("Produits des cessions d'immobilisations")  # parent : PCG 2026
    assert AGRI["234"]["label"] == "Immobilisations corporelles en cours - biens vivants"
    assert AGRI["296"]["label"] == "Dépréciations des participations et créances rattachées à des participations"


def test_detect_agri_chart():
    assert detect_chart(list(AGRI)) == "agri"
    societe = [a["code"] for a in load_chart("societe")]
    assert detect_chart(societe) == "societe"  # le plan agri contient le plan société : pas de confusion


def test_chart_enumerations_agree():
    assert set(instance_provisioning.CHARTS) == set(SEED_CHARTS) == set(ALL_CHARTS)
    roles = json.loads((ROOT / "data" / "account_roles.json").read_text())["roles"]
    for role, spec in roles.items():
        assert set(ALL_CHARTS) <= spec.keys(), role
        assert all(code in AGRI for code in spec["agri"]), role


@pytest.mark.parametrize("old,new", [
    ("70117111", "7011"), ("70120700", "7011"), ("70411000", "7014"), ("60110000", "60111"), ("60311000", "6031"),
    ("24200000", "241"), ("24100000", "241"), ("64600000", "646"), ("74500000", "745"), ("61310000", "6131"),
    ("71371110", "7135"), ("41100000", "411"), ("74300000", None), ("99999", None),
])
def test_map_pcga1986(old, new):
    assert agri_chart.map_pcga1986(old) == new


def test_map_file_targets_exist():
    data = json.loads((ROOT / "data" / "agri_pcga1986_map.json").read_text())
    assert data["_attribution"] and "CC-BY-SA" in data["_attribution"]
    assert all(target in AGRI for target in data["map"].values())


def test_menus_and_integrations_of_a_farm():
    nav = {m["key"]: m for m in build_nav("agri", is_admin=True, features={"associates"})}
    assert {"purchases", "sales", "associates"} <= nav.keys()
    assert not {"donations", "simple_operations"} & nav.keys()  # partie double
    simple = {m["key"] for m in build_nav("agri", is_admin=True, bookkeeping="simple")}
    assert {"simple_operations", "simple_reports"} <= simple and "donations" not in simple
    assert external_config.recommended("agri") == ["qonto"]
    assert not external_config.applies("helloasso", "agri")


def _as(chart, bookkeeping="double"):
    inst = Instance.query.filter_by(slug="test").one()
    inst.chart, inst.bookkeeping = chart, bookkeeping
    db.session.commit()


def test_default_accounts_of_a_farm(instance):
    _as("agri")
    from app.models import Account
    db.session.add_all([Account(code=c, label=c) for c in ("657", "6578", "757", "7578", "658")])
    db.session.commit()
    assert account_roles.default_account("disposal_book_value").code == "6578"
    assert account_roles.default_account("disposal_proceeds").code == "7578"


def test_simple_categories_of_a_farm(instance):
    _as("agri", "simple")
    from app.models import Account
    db.session.add_all([Account(code=a["code"], label=a["label"], account_type=a["account_type"],
                                is_header=a["is_header"]) for a in load_chart("agri")])
    db.session.commit()
    simple_categories.ensure_defaults()
    cats = {c.code: c for c in SimpleCategory.query}
    assert cats["ventes_animaux"].account.code == "7014"
    assert cats["engrais"].account.code == "60111"
    assert cats["ichn"].excluded_from_micro and cats["cessions"].excluded_from_micro
    assert not cats["aides_pac"].excluded_from_micro and cats["aides_pac"].account.code == "745"
    assert "cotisations" not in cats  # catégories d'association absentes


def test_simple_api_open_to_farm_not_receipts(app, login_as):
    client = login_as(role="admin")
    _as("agri", "simple")
    assert client.get("/api/v1/simple-categories").status_code == 200
    assert client.get("/api/v1/receipts").status_code == 403
    _as("sci", "double")
    assert client.get("/api/v1/simple-categories").status_code == 403


@pytest.fixture()
def admin(app, tmp_path, monkeypatch, login_as):
    monkeypatch.setattr(app, "instance_path", str(tmp_path / "instance"))
    monkeypatch.setattr(instance_provisioning, "BASE_DIR", tmp_path)

    def provision(url, chart):  # schéma tenant sans sous-processus (migrations testées à part)
        path = tmp_path / "instance" / url[len("sqlite:///"):]
        path.parent.mkdir(parents=True, exist_ok=True)
        db.metadata.create_all(create_engine(f"sqlite:///{path}"))

    monkeypatch.setattr("app.api.instances.provision_sqlite_database", provision)
    return login_as(is_admin=True)


def _tenant_rows(slug, model):
    from app.tenant import get_tenant_engine
    from sqlalchemy.orm import Session
    inst = Instance.query.filter_by(slug=slug).one()
    with Session(get_tenant_engine(inst)) as session:
        return [r for r in session.query(model)]


def test_create_farm_instance(admin):
    resp = admin.post("/api/v1/instances", json={
        "slug": "gaec-pres", "label": "GAEC des Prés", "chart": "agri", "legal_form_code": "GAEC",
        "income_tax": "IR", "ba_regime": "simplified", "fy_start": "2026-05-01", "fy_end": "2027-04-30"})
    assert resp.status_code == 201, resp.get_json()
    inst = Instance.query.filter_by(slug="gaec-pres").one()
    assert inst.chart == "agri" and inst.bookkeeping == "double" and inst.has_associates
    (org,) = _tenant_rows("gaec-pres", Organization)
    assert org.legal_form_code == "GAEC"
    profiles = {(p.kind, p.value, p.start_date) for p in _tenant_rows("gaec-pres", TaxProfile)}
    assert profiles == {("income_tax", "IR", date(2026, 5, 1)), ("ba_regime", "simplified", date(2026, 5, 1))}
    (fy,) = _tenant_rows("gaec-pres", FiscalYear)
    assert (fy.label, fy.start_date, fy.end_date) == ("2026-2027", date(2026, 5, 1), date(2027, 4, 30))
    from app.models import Product
    assert _tenant_rows("gaec-pres", Product) == []  # base sans plan dans ce test : aucun article (comptes absents)


def test_create_micro_farm_is_simple(admin):
    resp = admin.post("/api/v1/instances", json={
        "slug": "ferme-micro", "label": "Ferme", "chart": "agri", "legal_form_code": "EI", "ba_regime": "micro",
        "fy_start": "2027-01-01", "fy_end": "2027-12-31"})
    assert resp.status_code == 201, resp.get_json()
    inst = Instance.query.filter_by(slug="ferme-micro").one()
    assert inst.bookkeeping == "simple" and not inst.has_associates


@pytest.mark.parametrize("extra,field", [
    ({"legal_form_code": ""}, "legal_form_code"),
    ({"ba_regime": ""}, "ba_regime"),
    ({"ba_regime": "micro", "fy_start": "2026-05-01", "fy_end": "2027-04-30"}, "fy_end"),
    ({"legal_form_code": "SCEA", "ba_regime": "micro", "fy_start": "2027-01-01", "fy_end": "2027-12-31",
      "created_on": "2012-01-01"}, "ba_regime"),
    ({"legal_form_code": "SAS", "income_tax": "IR"}, "income_tax"),
    ({"fy_end": "2026-04-30"}, "fy_end"),
])
def test_create_farm_validation(admin, extra, field):
    body = {"slug": "ferme-x", "label": "Ferme", "chart": "agri", "legal_form_code": "EARL", "income_tax": "IR",
            "ba_regime": "normal", "fy_start": "2026-05-01", "fy_end": "2027-04-30", **extra}
    resp = admin.post("/api/v1/instances", json=body)
    assert resp.status_code == 422, resp.get_json()
    assert field in resp.get_json()["error"]["fields"]
    assert Instance.query.filter_by(slug="ferme-x").first() is None


def test_create_farm_at_is(admin):
    resp = admin.post("/api/v1/instances", json={
        "slug": "sas-ferme", "label": "SAS", "chart": "agri", "legal_form_code": "SAS",
        "fy_start": "2026-07-01", "fy_end": "2027-06-30"})
    assert resp.status_code == 201, resp.get_json()
    assert {(p.kind, p.value) for p in _tenant_rows("sas-ferme", TaxProfile)} == {("income_tax", "IS")}
