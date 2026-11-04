"""Lot AG1.c : états de l'exploitation agricole — bilan (passif sociétés / entreprise individuelle), compte de
résultat (art. 121-3), soldes intermédiaires de gestion, tableau des biens vivants (art. 121-4), API et exports
(claudedocs/design_compta_agricole.md § 5)."""
import json
import os
from datetime import date

import pytest

from app.extensions import db
from app.models import FiscalYear, Instance, Organization
from app.models.journal_entry import SOURCE_OPENING
from app.services import agri_reports
from app.services.reports import bilan_layout_key, build_bilan, build_compte_resultat, compte_resultat_rows
from app.views.reports import _build_cdr_ods
from test_reports_charts import _fy, _post, _rows_by_label

PLAN = os.path.join(os.path.dirname(__file__), "..", "data", "plan_comptable_agri.json")


def _codes(classes):
    with open(PLAN, encoding="utf-8") as fh:
        return [a["code"] for a in json.load(fh) if a["code"][0] in classes and not a["is_header"]]


def test_compte_resultat_counts_every_account_exactly_once(session):
    codes = _codes("67")
    fy = _fy(session)
    lines = [(c, 100, 0) if c.startswith("6") else (c, 0, 100) for c in codes]
    n_charges = sum(1 for c in codes if c.startswith("6"))
    n_produits = len(codes) - n_charges
    lines.append(("512", n_produits * 100, n_charges * 100))
    _post(session, fy, lines)
    rows = _rows_by_label(compte_resultat_rows(build_compte_resultat(fy, chart="agri"), "agri"))
    assert rows["Total des charges (II+IV+VI+VII+VIII)"][0] == n_charges * 100
    assert rows["Total des produits (I+III+V)"][0] == n_produits * 100


@pytest.mark.parametrize("layout", ["agri", "agri_ei"])
def test_bilan_balances_with_every_account(session, layout):
    codes = [c for c in _codes("1234567") if c != "512"]
    fy = _fy(session)
    lines, counter = [], 0
    for i, code in enumerate(codes):
        amount = 100 + i
        if i % 2:
            lines.append((code, amount, 0))
            counter -= amount
        else:
            lines.append((code, 0, amount))
            counter += amount
    lines.append(("512", max(counter, 0), max(-counter, 0)))
    _post(session, fy, lines)
    data = build_bilan(fy, chart=layout)
    actif = next(l for l in data["actif"] if l["kind"] == "total")["n"]
    passif = next(l for l in data["passif"] if l["kind"] == "total")["n"]
    assert actif == passif


def _farm_year(session):
    """Exploitation d'élevage et de cultures : ventes, aides, stocks, biens vivants, cession d'une vache."""
    fy = _fy(session)
    _post(session, fy, [("241", 2000000, 0), ("31151", 300000, 0), ("3112", 400000, 0), ("512", 1000000, 0),
                        ("108", 0, 3700000)])
    _post(session, fy, [("512", 5000000, 0), ("7011", 0, 3000000), ("7014", 0, 1500000), ("7012", 0, 500000)])
    _post(session, fy, [("512", 800000, 0), ("745", 0, 600000), ("741", 0, 200000)])
    _post(session, fy, [("60111", 700000, 0), ("60117", 300000, 0), ("6051", 200000, 0), ("6131", 400000, 0),
                        ("63512", 50000, 0), ("646", 600000, 0), ("512", 0, 2250000)])
    _post(session, fy, [("73", 0, 100000), ("108", 100000, 0)])  # autoconsommation
    _post(session, fy, [("713554", 0, 150000), ("35511", 150000, 0)])  # récolte en stock
    _post(session, fy, [("6811", 400000, 0), ("2841", 0, 400000)])
    _post(session, fy, [("512", 250000, 0), ("7571", 0, 250000), ("6571", 180000, 0), ("241", 0, 180000)])
    return fy


def test_compte_resultat_lines(session):
    fy = _farm_year(session)
    rows = _rows_by_label(compte_resultat_rows(build_compte_resultat(fy, chart="agri"), "agri"))
    assert rows["Ventes d'animaux (hors biens vivants immobilisés)"][0] == 1500000
    assert rows["Autre production vendue (biens et services)"][0] == 3500000
    assert rows["Montant net du chiffre d'affaires"][0] == 5000000
    assert rows["Indemnités et subventions d'exploitation"][0] == 800000
    assert rows["dont remboursement forfaitaire de TVA"][0] == 200000
    assert rows["Production autoconsommée"][0] == 100000
    assert rows["Produits de cession sur biens vivants immobilisés"][0] == 250000
    assert rows["Achats d'animaux"][0] == 300000
    assert rows["Achats d'approvisionnements"][0] == 700000
    assert rows["Valeur comptable des biens vivants immobilisés cédés"][0] == 180000
    # TOTAL I : le sous-total du chiffre d'affaires et la ligne « dont » ne sont pas comptés deux fois.
    assert rows["TOTAL I — Produits d'exploitation"][0] == 5000000 + 800000 + 100000 + 150000 + 250000
    assert rows["BÉNÉFICE"][0] == 6300000 - (700000 + 300000 + 200000 + 400000 + 50000 + 600000 + 400000 + 180000)


def test_sig(session):
    fy = _farm_year(session)
    sig = {r["key"]: r["n"] for r in agri_reports.sig(fy)}
    assert sig["production"] == 5000000 + 150000 + 100000
    assert sig["consommations"] == 700000 + 300000 + 200000 + 400000
    assert sig["valeur_ajoutee"] == sig["production"] - sig["consommations"]
    assert sig["ebe"] == sig["valeur_ajoutee"] + 800000 - 50000 - 600000
    assert sig["resultat_net"] == 3470000
    assert sig["resultat_exploitation"] == sig["ebe"] - 400000 + 250000 - 180000


def test_living_assets_table(session):
    fy = _farm_year(session)
    table = agri_reports.living_assets_table(fy)
    groups = {g["key"]: {r["key"]: r for r in g["rows"]} for g in table["groups"]}
    # Vaches 20 000 € − cédée 1 800 € − amortissement 4 000 € (2841) + génisses en stock 4 000 €.
    assert groups["long"]["animaux"]["closing"] == 2000000 - 180000 - 400000 + 400000
    assert groups["court"]["vegetaux"]["closing"] == 300000
    assert table["total"]["closing"] == 1820000 + 300000
    assert groups["long"]["animaux"]["opening"] == 0  # ni exercice précédent ni à-nouveaux


def test_living_assets_opening_from_previous_year(session):
    prev = FiscalYear(label="2024", start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
    session.add(prev)
    session.flush()
    from app.models import Account, Journal, JournalEntry, JournalLine
    jr = Journal(code="OD", label="OD")
    session.add_all([jr, Account(code="3113", label="3113"), Account(code="512", label="512")])
    session.flush()
    entry = JournalEntry(fiscal_year_id=prev.id, journal_id=jr.id, entry_date=date(2024, 6, 1))
    session.add(entry)
    session.flush()
    for code, d, c in (("3113", 50000, 0), ("512", 0, 50000)):
        session.add(JournalLine(entry_id=entry.id, account_id=Account.query.filter_by(code=code).one().id,
                                debit_cents=d, credit_cents=c))
    session.flush()
    fy = _fy(session)
    table = agri_reports.living_assets_table(fy, prev)
    court = {r["key"]: r for r in table["groups"][1]["rows"]}
    assert court["animaux"]["opening"] == 50000 and court["animaux"]["closing"] == 0


def test_bilan_layout_key_by_legal_form(app, instance):
    assert bilan_layout_key("societe") == "societe"
    db.session.add(Organization(name="Ferme", legal_form_code="EI"))
    db.session.commit()
    assert bilan_layout_key("agri") == "agri_ei"
    Organization.query.first().legal_form_code = "GAEC"
    db.session.commit()
    assert bilan_layout_key("agri") == "agri"


def test_ei_passif_has_individual_capital(session):
    fy = _farm_year(session)
    passif = [l["label"] for l in build_bilan(fy, chart="agri_ei")["passif"]]
    assert "Capital individuel" in passif and "Capital social" not in passif
    actif = [l["label"] for l in build_bilan(fy, chart="agri")["actif"]]
    assert "Biens vivants et en-cours (cycle long)" in actif and "Améliorations des sols et des milieux" in actif


def test_ods_export(session):
    fy = _farm_year(session)
    assert _build_cdr_ods(build_compte_resultat(fy, chart="agri"), fy, None, "agri")[:2] == b"PK"


def _as_agri(legal_form="GAEC"):
    inst = Instance.query.filter_by(slug="test").one()
    inst.chart = "agri"
    db.session.add(Organization(name="Ferme", legal_form_code=legal_form))
    db.session.commit()


def test_api(app, login_as):
    client = login_as()
    assert client.get("/api/v1/reports/sig").status_code == 404  # plan associatif
    _as_agri("EI")
    fy = _farm_year(db.session)
    db.session.commit()
    body = client.get(f"/api/v1/reports/sig?fy_id={fy.id}").get_json()
    assert {r["key"] for r in body["items"]} >= {"valeur_ajoutee", "ebe", "resultat_net"}
    assert body["meta"]["export_url"].endswith(f"fy_id={fy.id}")
    assets = client.get(f"/api/v1/reports/living-assets?fy_id={fy.id}").get_json()["item"]
    assert assets["total"]["closing"] == 2120000
    bilan = client.get(f"/api/v1/reports/bilan?fy_id={fy.id}").get_json()
    assert bilan["meta"]["layout"] == "agri_ei"
    xlsx = client.get(body["meta"]["export_url"])
    assert xlsx.status_code == 200 and xlsx.data[:2] == b"PK"
    nav = client.get("/api/v1/session").get_json()["nav"]
    compta = next(m for m in nav if m["key"] == "compta")
    assert any(i.get("key") == "sig" for i in compta["items"])
