"""Lot T1 : référentiel `societe` (SAS, SASU) — plan PCG 2026, menus, création d'instance, comptes par
défaut, états 2050 / 2052 et statut JEI de la Structure (claudedocs/design_societe_tva.md § 3.1)."""
from datetime import date

import pytest

from app.extensions import db
from app.menu_config import build_nav
from app.models import Account, FiscalYear, Instance, Journal, JournalEntry, JournalLine
from app.services import account_roles, assets, external_config, instance_provisioning
from app.services.reports import build_bilan, build_compte_resultat, compte_resultat_rows
from seed_accounts import load_chart


def _as(chart):
    Instance.query.filter_by(slug="test").one().chart = chart
    db.session.commit()


def test_chart_from_the_pcg_2026():
    codes = {a["code"]: a for a in load_chart("societe")}
    for code in ("101", "120", "129", "2154", "44551", "44562", "44566", "44567", "44571", "44574", "4452",
                 "455", "457", "6411", "657", "695", "757"):
        assert code in codes, code
    assert "675" not in codes and "775" not in codes  # PCG 2025 : cessions en 657 / 757
    assert [a["code"] for a in codes.values() if a["is_header"]] == list("1234567")
    assert all(a["label"] and len(a["label"]) <= 255 for a in codes.values())


def test_menus_of_a_company():
    nav = {m["key"]: m for m in build_nav("societe", is_admin=True, features={"associates"})}
    assert {"purchases", "sales", "associates"} <= nav.keys()
    assert not {"donations", "indicateurs", "simple_operations"} & nav.keys()
    assert "members" not in [i.get("key") for i in nav["tiers"]["items"]]
    assert "receipts_settings" not in [i.get("key") for i in nav["configuration"]["items"]]


def test_provisioning_without_rules(monkeypatch, tmp_path):
    ran = []
    monkeypatch.setattr(instance_provisioning, "_run", lambda cmd, url: ran.append(cmd[1:]))
    instance_provisioning.provision_sqlite_database(f"sqlite:///{tmp_path / 's'}.db", chart="societe")
    assert ran == [["-m", "flask", "db", "upgrade"], ["seed_accounts.py", "societe"]]


def test_qonto_recommended_and_associations_integrations_off():
    assert external_config.recommended("societe") == ["qonto"]
    assert not external_config.applies("helloasso", "societe")


def test_default_accounts_and_depreciation(instance):
    _as("societe")
    db.session.add_all([Account(code=c, label=c) for c in ("657", "757", "658", "758", "6811")])
    db.session.commit()
    assert account_roles.default_account("disposal_book_value").code == "657"
    assert account_roles.default_account("disposal_proceeds").code == "757"
    assert account_roles.default_account("lettering_gap_expense").code == "658"
    assert assets.enabled()  # une société amortit (une SCI à l'IR non)


def _year(session):
    fy = FiscalYear(label="2026-2027", start_date=date(2026, 7, 1), end_date=date(2027, 6, 30))
    journal = Journal(code="OD", label="OD")
    session.add_all([fy, journal])
    session.flush()
    for lines in (
        [("101", 0, 2908100), ("1041", 0, 148591200), ("119", 138773600, 0), ("512", 12825700, 0),
         ("203", 214923200, 0), ("2803", 0, 214923200), ("455", 0, 500000), ("4561", 400000, 0)],
        [("411", 120000, 0), ("706", 0, 100000), ("44571", 0, 20000)],
        [("657", 50000, 0), ("757", 0, 80000), ("462", 30000, 0)],
        [("695", 10000, 0), ("444", 0, 10000)],
    ):
        entry = JournalEntry(fiscal_year_id=fy.id, journal_id=journal.id, entry_date=date(2026, 7, 1))
        session.add(entry)
        session.flush()
        for code, debit, credit in lines:
            account = Account.query.filter_by(code=code).first() or Account(code=code, label=code)
            session.add(account)
            session.flush()
            session.add(JournalLine(entry_id=entry.id, account_id=account.id, debit_cents=debit, credit_cents=credit))
    session.flush()
    return fy


def test_income_statement_like_the_2052(session):
    rows = {label.strip(): n for kind, label, n, _p in compte_resultat_rows(
        build_compte_resultat(_year(session), chart="societe"), "societe") if kind != "section"}
    assert rows["Production vendue — services"] == 100000
    assert rows["Produits des cessions d'immobilisations incorporelles et corporelles"] == 80000
    assert rows["Valeurs comptables des immobilisations incorporelles et corporelles cédées"] == 50000
    assert rows["1 — RÉSULTAT D'EXPLOITATION (I - II)"] == 130000
    assert rows["Impôts sur les bénéfices (VIII)"] == 10000
    assert rows["BÉNÉFICE"] == 120000


def test_balance_sheet_like_the_2050(session):
    data = build_bilan(_year(session), chart="societe")
    actif = {l["label"]: l["n"] for l in data["actif"] if l["kind"] != "section"}
    passif = {l["label"]: l["n"] for l in data["passif"] if l["kind"] != "section"}
    # Brut, amortissements et net par ligne (2050) ; la ligne globale ne garde que le non rapproché.
    dev = next(l for l in data["actif"] if l["label"] == "Frais de développement")
    assert (dev["gross"], dev["depreciation"], dev["n"]) == (214923200, 214923200, 0)
    rest = next(l for l in data["actif"] if l.get("unallocated"))
    assert rest["n"] == 0 and rest["label"].endswith("non rapprochés d'une ligne")
    assert passif["Primes d'émission, de fusion, d'apport"] == 148591200
    assert passif["Report à nouveau"] == -138773600
    assert passif["Associés — comptes courants"] == 500000
    assert actif["Autres créances"] == 400000 + 30000  # 4561 et 462, pas le compte courant créditeur
    assert actif["TOTAL ACTIF"] == passif["TOTAL PASSIF"]


@pytest.fixture()
def company(login_as):
    client = login_as(role="admin")
    _as("societe")
    return client


def test_structure_holds_the_jei_date(company):
    resp = company.put("/api/v1/organization", json={"name": "Ekylibre", "jei_since": "2015-01-05"})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["item"]["jei_since"] == "2015-01-05"
    resp = company.put("/api/v1/organization", json={"name": "Ekylibre", "jei_since": "05/01/2015"})
    assert resp.status_code == 422
    assert "jei_since" in resp.get_json()["error"]["fields"]
    assert company.put("/api/v1/organization", json={"name": "Ekylibre", "jei_since": ""}).get_json()["item"]["jei_since"] is None


def test_jei_ignored_for_an_association(login_as):
    client = login_as(role="admin")
    resp = client.put("/api/v1/organization", json={"name": "Asso", "jei_since": "2015-01-05"})
    assert resp.get_json()["item"]["jei_since"] is None
