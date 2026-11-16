"""Lot AG1.e : catégories d'articles agricoles (Lexicon → catalogue), règles bancaires d'une exploitation."""
import json
import re
from pathlib import Path

import pytest
import yaml

from app.extensions import db
from app.models import Account, Instance, Product
from app.services import agri_catalog, instance_provisioning
from seed_accounts import load_chart

ROOT = Path(__file__).resolve().parents[1]
CHART = {a["code"] for a in load_chart("agri")}


def test_categories_file():
    data = json.loads((ROOT / "data" / "agri_purchase_categories.json").read_text("utf-8"))
    assert "CC-BY-SA" in data["_attribution"]
    items = {c["key"]: c for c in data["categories"]}
    for item in items.values():
        assert item["purchase_account"] or item["sale_account"], item["key"]
        assert item["purchase_account"] is None or (item["purchase_account"] in CHART
                                                     and item["purchase_account"][:2] in ("60", "61", "62"))
        assert item["sale_account"] is None or (item["sale_account"] in CHART and item["sale_account"].startswith("70"))
        assert item["vat_rate_bp"] in (None, 210, 550, 1000, 2000), item["key"]
        assert item["vat_to_validate"]
    assert items["fertilizer"]["purchase_account"] == "60111" and items["animal_food"]["vat_rate_bp"] == 1000
    assert items["short_cycle_animal"]["purchase_account"] == "60117" and items["short_cycle_animal"]["sale_account"] == "7014"
    assert items["land_rent"]["purchase_account"] == "6131"  # correction de Lyvre (titre 5 : fermages)
    assert items["insurance"]["vat_rate_bp"] is None and "waste_tax" not in items


def _agri():
    Instance.query.filter_by(slug="test").one().chart = "agri"
    db.session.add_all([Account(code=a["code"], label=a["label"], account_type=a["account_type"],
                                is_header=a["is_header"]) for a in load_chart("agri")])
    db.session.commit()


def test_seed_catalog_is_idempotent(app, instance):
    _agri()
    first = agri_catalog.seed_catalog()
    assert first["created"] == len(agri_catalog.categories())
    seeds = Product.query.filter_by(name="Semence et plant").one()
    assert seeds.kind == "both" and seeds.purchase_account.code == "60112" and seeds.sale_account.code == "7011"
    assert seeds.vat_rate_bp == 1000 and seeds.nature == "goods"
    assert Product.query.filter_by(name="Engrais et amendement").one().kind == "purchase"
    seeds.vat_rate_bp = 550  # adapté par l'exploitant : conservé
    db.session.commit()
    assert agri_catalog.seed_catalog() == {"created": 0, "skipped": first["created"]}
    assert Product.query.filter_by(name="Semence et plant").one().vat_rate_bp == 550


def test_api(app, login_as):
    client = login_as()
    assert client.post("/api/v1/products/agri-catalog", json={}).status_code == 404
    _agri()
    body = client.post("/api/v1/products/agri-catalog", json={}).get_json()
    assert body["result"]["created"] > 40 and "TVA" in body["notices"][0]["message"]


def test_api_read_only_for_accountant(app, login_as):
    client = login_as(role="accountant")
    _agri()
    assert client.post("/api/v1/products/agri-catalog", json={}).status_code == 403


def test_bank_rules_template():
    rules = yaml.safe_load((ROOT / "data" / "rules_agri.yml").read_text("utf-8"))["rules"]
    samples = {"Cotisations MSA": "PRLV SEPA MSA DORDOGNE COTISATIONS", "Aides PAC (ASP)": "VIR ASP PAIEMENT PAC 2026",
               "Aides FranceAgriMer": "VIREMENT FRANCEAGRIMER AIDE", "Fermage": "VIR FERMAGE SAINT MICHEL"}
    for rule in rules:
        assert rule["account"] in CHART, rule["name"]
        assert re.search(rule["label_regex"], samples[rule["name"]]), rule["name"]
    assert not re.search(rules[0]["label_regex"], "PRLV ASSURANCE MSAFE")  # mot entier


def test_provisioning_seeds_agri_rules(monkeypatch, tmp_path):
    ran = []
    monkeypatch.setattr(instance_provisioning, "_run", lambda cmd, url: ran.append(cmd[1:]))
    instance_provisioning.provision_sqlite_database(f"sqlite:///{tmp_path / 'f'}.db", chart="agri")
    assert ran == [["-m", "flask", "db", "upgrade"], ["seed_accounts.py", "agri"], ["seed_rules.py", "agri"]]
    ran.clear()
    instance_provisioning.provision_sqlite_database(f"sqlite:///{tmp_path / 'a'}.db", chart="asso")
    assert ran[-1] == ["seed_rules.py"]
