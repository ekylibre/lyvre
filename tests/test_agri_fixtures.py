"""Lot AG1.f : jeu d'essai fictif de la comptabilité agricole (tests/fixtures/agri, claudedocs/design_compta_agricole.md
§ 10). Contrôle du vocabulaire des fichiers (aucune donnée d'origine) ; chargement des exploitations fictives et
comparaison des états de Lyvre aux agrégats calculés directement sur les fichiers (expected.json)."""
import json
import re
from pathlib import Path

import pytest

from app.extensions import db
from app.models import Account, FiscalYear, Instance, JournalLine
from app.services import agri_reports
from app.services.reports import bilan_layout_key, build_bilan, build_compte_resultat, compte_resultat_rows
from scripts.agri_fixtures.anonymize import allowed_tokens
from scripts.agri_fixtures.load import FIXTURES, load
from scripts.agri_fixtures.vocabulary import tokens
from seed_accounts import load_chart

FEC_FARMS = ["A_earl_porcs_rs", "B_scea_legumes_rn", "C_gaec_ateliers"]
TEXT_FIELDS = (1, 2, 5, 6, 7, 8, 10)


def _fec_rows(path: Path):
    lines = path.read_text("utf-8").splitlines()
    return [line.split("\t") for line in lines[1:]]


@pytest.mark.parametrize("farm", FEC_FARMS)
def test_fec_text_is_generic_vocabulary(farm):
    allowed = allowed_tokens()
    for path in (FIXTURES / farm).glob("*_FEC*.txt"):
        words = set()
        for row in _fec_rows(path):
            for index in TEXT_FIELDS:
                words |= {t for t in tokens(row[index]) if not t.isdigit()}
                assert not re.search(r"\d{9}", row[index]), (path.name, row[index])
        assert words <= allowed, sorted(words - allowed)[:20]


def test_ateliers_and_profiles_are_generic():
    allowed = allowed_tokens() | {"ATELIER"}
    items = json.loads((FIXTURES / "C_gaec_ateliers" / "ateliers.json").read_text("utf-8"))
    assert {t for item in items for t in tokens(item["label"])} <= allowed
    assert any(item["quantity"] for item in items)
    for farm in [*FEC_FARMS, "D_micro_rfa"]:
        profile = json.loads((FIXTURES / farm / "profile.json").read_text("utf-8"))
        assert re.search(r"fictif|fictive", profile["label"].lower())


def _agri_instance(bookkeeping="double"):
    inst = Instance.query.filter_by(slug="test").one()
    inst.chart, inst.bookkeeping = "agri", bookkeeping
    db.session.add_all([Account(code=a["code"], label=a["label"], account_type=a["account_type"],
                                is_header=a["is_header"]) for a in load_chart("agri")])
    db.session.commit()


def _rows(fy, prev=None):
    return {label.strip(): n for kind, label, n, _p in
            compte_resultat_rows(build_compte_resultat(fy, prev, "agri"), "agri") if kind != "section"}


def _check_year(fy, prev, expected):
    rows = _rows(fy, prev)
    result = rows.get("BÉNÉFICE", None)
    result = result if result is not None else rows["PERTE"]
    assert result == expected["result_cents"]
    lines = expected["lines_cents"]
    assert rows["Ventes d'animaux (hors biens vivants immobilisés)"] == lines["ventes_animaux_7014"]
    assert rows["Indemnités et subventions d'exploitation"] == lines["subventions_74"]
    assert rows["Achats d'animaux"] == lines["achats_animaux_60117"]
    assert rows["Dotations aux amortissements sur immobilisations"] == lines["dotations_6811"]
    data = build_bilan(fy, prev, bilan_layout_key("agri"))
    actif = next(l for l in data["actif"] if l["kind"] == "total")["n"]
    passif = next(l for l in data["passif"] if l["kind"] == "total")["n"]
    assert actif == passif
    sig = {r["key"]: r["n"] for r in agri_reports.sig(fy, prev)}
    assert sig["resultat_net"] == expected["result_cents"]


@pytest.mark.parametrize("farm", ["B_scea_legumes_rn", "C_gaec_ateliers"])
def test_load_fec_farm_and_compare(app, instance, farm):
    _agri_instance()
    directory = FIXTURES / farm
    loaded = load(directory)
    expected = json.loads((directory / "expected.json").read_text("utf-8"))
    profile = json.loads((directory / "profile.json").read_text("utf-8"))
    years = FiscalYear.query.order_by(FiscalYear.start_date).all()
    assert len(years) == len(profile["fiscal_years"])
    first = profile["fiscal_years"][0]
    assert loaded[first["file"]] > 0
    _check_year(years[0], None, expected[first["file"]])
    if len(years) > 1:  # exercice suivant : à-nouveaux générés, bilan équilibré
        data = build_bilan(years[1], years[0], bilan_layout_key("agri"))
        assert next(l for l in data["actif"] if l["kind"] == "total")["n"] == \
            next(l for l in data["passif"] if l["kind"] == "total")["n"]


def test_load_largest_farm(app, instance):
    _agri_instance()
    directory = FIXTURES / "A_earl_porcs_rs"
    load(directory)
    expected = json.loads((directory / "expected.json").read_text("utf-8"))
    fy = FiscalYear.query.one()
    _check_year(fy, None, expected["A_FEC20250131.txt"])


def test_load_micro_farm(app, instance):
    _agri_instance("simple")
    directory = FIXTURES / "D_micro_rfa"
    load(directory)
    expected = json.loads((directory / "expected.json").read_text("utf-8"))
    from app.models import SimpleCategory
    excluded = {c.account_id for c in SimpleCategory.query.filter_by(kind="income", excluded_from_micro=True)}
    income = [l for l in JournalLine.query.join(Account).filter(Account.code.like("7%"))]
    assert sum(l.credit_cents for l in income) == expected["receipts_cents"]
    assert sum(l.credit_cents for l in income if l.account_id in excluded) == expected["excluded_cents"]
    charges = JournalLine.query.join(Account).filter(Account.code.like("6%")).all()
    assert sum(l.debit_cents for l in charges) == expected["expenses_cents"]
