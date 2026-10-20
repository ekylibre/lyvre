"""Bilan et compte de résultat selon le plan comptable (asso / sci)."""
import json
import os
from datetime import date
from types import SimpleNamespace

import pytest
from flask import g, render_template

from app.models import Account, FiscalYear, Journal, JournalEntry, JournalLine
from app.services.reports import (
    build_bilan, build_compte_resultat, compte_resultat_rows,
)


def _fy(session):
    fy = FiscalYear(label="2025", start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
    session.add(fy)
    session.flush()
    return fy


def _post(session, fy, lines):
    """lines: [(code, debit_cents, credit_cents)] — comptes créés à la volée."""
    jr = Journal.query.filter_by(code="OD").first()
    if jr is None:
        jr = Journal(code="OD", label="OD")
        session.add(jr)
        session.flush()
    e = JournalEntry(fiscal_year_id=fy.id, journal_id=jr.id, entry_date=date(2025, 6, 1))
    session.add(e)
    session.flush()
    for code, debit, credit in lines:
        acc = Account.query.filter_by(code=code).first()
        if acc is None:
            acc = Account(code=code, label=code)
            session.add(acc)
            session.flush()
        session.add(JournalLine(entry_id=e.id, account_id=acc.id,
                                debit_cents=debit, credit_cents=credit))
    session.flush()


def _sci_year(session):
    fy = _fy(session)
    # Ouverture : immeuble financé par emprunt + apport en compte courant.
    _post(session, fy, [
        ("211", 5000000, 0), ("2131", 15000000, 0), ("512", 1000000, 0),
        ("101", 0, 100000), ("164", 0, 16000000), ("4551", 0, 4900000),
    ])
    # Loyers, charges refacturées, dépôt de garantie.
    _post(session, fy, [("411", 1300000, 0), ("7083", 0, 1200000), ("7085", 0, 100000)])
    _post(session, fy, [("512", 1300000, 0), ("411", 0, 1300000)])
    _post(session, fy, [("512", 200000, 0), ("165", 0, 200000)])
    # Charges : taxe foncière, entretien, assurance, intérêts, cession.
    _post(session, fy, [("63512", 150000, 0), ("615", 80000, 0), ("616", 40000, 0),
                        ("661", 300000, 0), ("4011", 0, 570000)])
    # Un fournisseur réglé en trop (solde débiteur) → créance à l'actif.
    _post(session, fy, [("4012", 30000, 0), ("512", 0, 30000)])
    _post(session, fy, [("775", 0, 50000), ("675", 20000, 0), ("512", 30000, 0)])
    return fy


def _rows_by_label(rows):
    return {label.strip(): (n, p) for kind, label, n, p in rows if kind != "section"}


def test_sci_compte_resultat_lines_and_result(session):
    fy = _sci_year(session)
    data = build_compte_resultat(fy, chart="sci")
    rows = _rows_by_label(compte_resultat_rows(data, "sci"))

    assert rows["Loyers et fermages"][0] == 1200000
    assert rows["Charges refacturées aux locataires"][0] == 100000
    assert rows["Autres ventes et prestations de services"][0] == 0
    assert rows["Taxe foncière"][0] == 150000
    assert rows["Autres impôts et taxes"][0] == 0
    assert rows["Entretien et réparations"][0] == 80000
    assert rows["Intérêts des emprunts"][0] == 300000
    assert rows["TOTAL I — Produits d'exploitation"][0] == 1300000
    assert rows["TOTAL II — Charges d'exploitation"][0] == 270000
    # Résultat = produits (1 300 000 + 50 000) - charges (270 000 + 300 000 + 20 000)
    assert rows["BÉNÉFICE"][0] == 760000
    assert rows["BÉNÉFICE"][1] is None  # pas d'exercice N-1
    assert "EXCÉDENT" not in rows


@pytest.mark.parametrize("chart", ["asso", "sci"])
def test_compte_resultat_counts_every_account_exactly_once(session, chart):
    """Chaque compte de classe 6 / 7 du référentiel est compté une seule fois
    (pas de recouvrement de préfixes, aucun compte oublié)."""
    path = os.path.join(os.path.dirname(__file__), "..", "data", f"plan_comptable_{chart}.json")
    with open(path, encoding="utf-8") as fh:
        codes = [a["code"] for a in json.load(fh) if a["code"][0] in "67" and not a["is_header"]]
    fy = _fy(session)
    lines = []
    for code in codes:
        lines.append((code, 100, 0) if code.startswith("6") else (code, 0, 100))
    n_charges = sum(1 for c in codes if c.startswith("6"))
    n_produits = len(codes) - n_charges
    lines.append(("512", n_produits * 100, n_charges * 100))
    _post(session, fy, lines)

    rows = _rows_by_label(compte_resultat_rows(build_compte_resultat(fy, chart=chart), chart))
    assert rows["Total des charges (II+IV+VI+VII+VIII)"][0] == n_charges * 100
    assert rows["Total des produits (I+III+V)"][0] == n_produits * 100


def test_asso_dont_lines_not_summed(session):
    fy = _fy(session)
    _post(session, fy, [("7073", 0, 1000), ("7063", 0, 500), ("512", 1500, 0)])
    rows = _rows_by_label(compte_resultat_rows(build_compte_resultat(fy), "asso"))
    assert rows["Ventes de biens"][0] == 1000
    assert rows["dont ventes de dons en nature"][0] == 1000
    assert rows["dont parrainages"][0] == 500
    assert rows["TOTAL I — Produits d'exploitation"][0] == 1500


@pytest.mark.parametrize("chart", ["asso", "sci"])
def test_bilan_balances_with_every_account(session, chart):
    """Une écriture équilibrée sur chaque compte (classes 1 à 7) du référentiel
    donne un bilan équilibré : aucun compte oublié ni compté deux fois."""
    path = os.path.join(os.path.dirname(__file__), "..", "data", f"plan_comptable_{chart}.json")
    with open(path, encoding="utf-8") as fh:
        codes = [a["code"] for a in json.load(fh)
                 if a["code"][0] in "1234567" and not a["is_header"] and a["code"] != "512"]
    fy = _fy(session)
    lines, counter = [], 0
    for i, code in enumerate(codes):
        amount = 100 + i  # montants distincts : pas de compensation fortuite
        if i % 2:
            lines.append((code, amount, 0))
            counter -= amount
        else:
            lines.append((code, 0, amount))
            counter += amount
    lines.append(("512", max(counter, 0), max(-counter, 0)))
    _post(session, fy, lines)

    data = build_bilan(fy, chart=chart)
    total_actif = next(l for l in data["actif"] if l["kind"] == "total")["n"]
    total_passif = next(l for l in data["passif"] if l["kind"] == "total")["n"]
    assert total_actif == total_passif


def test_asso_bilan_includes_current_result(session):
    fy = _fy(session)
    _post(session, fy, [("1022", 0, 100000), ("512", 100000, 0)])
    _post(session, fy, [("756", 0, 30000), ("512", 30000, 0)])
    _post(session, fy, [("6063", 5000, 0), ("401", 0, 5000)])
    data = build_bilan(fy, chart="asso")
    passif = {l["label"]: l["n"] for l in data["passif"] if l["kind"] != "section"}
    actif = {l["label"]: l["n"] for l in data["actif"] if l["kind"] != "section"}
    assert passif["Excédent ou déficit de l'exercice"] == 25000
    assert passif["Dettes fournisseurs et comptes rattachés"] == 5000
    assert actif["Autres créances"] == 0
    assert actif["Disponibilités"] == 130000
    assert actif["TOTAL ACTIF"] == passif["TOTAL PASSIF"] == 130000


def test_sci_bilan_balances_and_splits_tiers(session):
    fy = _sci_year(session)
    data = build_bilan(fy, chart="sci")
    actif = {l["label"]: l for l in data["actif"] if l["kind"] != "section"}
    passif = {l["label"]: l for l in data["passif"] if l["kind"] != "section"}

    assert actif["Terrains"]["n"] == 5000000
    assert actif["Constructions"]["n"] == 15000000
    assert actif["Autres créances"]["n"] == 30000          # fournisseur débiteur
    assert passif["Dettes fournisseurs et comptes rattachés"]["n"] == 570000
    assert passif["Associés — comptes courants"]["n"] == 4900000
    assert passif["Dépôts de garantie reçus"]["n"] == 200000
    assert passif["Emprunts auprès des établissements de crédit"]["n"] == 16000000
    assert passif["Résultat de l'exercice"]["n"] == 760000
    assert actif["TOTAL ACTIF"]["n"] == passif["TOTAL PASSIF"]["n"]
    assert actif["TOTAL ACTIF"]["p"] is None


def test_sci_bilan_bank_overdraft_goes_to_passif(session):
    fy = _fy(session)
    _post(session, fy, [("101", 0, 100000), ("5121", 100000, 0)])
    _post(session, fy, [("2131", 300000, 0), ("5122", 0, 300000)])
    data = build_bilan(fy, chart="sci")
    actif = {l["label"]: l["n"] for l in data["actif"] if l["kind"] == "row"}
    passif = {l["label"]: l["n"] for l in data["passif"] if l["kind"] == "row"}
    assert actif["Disponibilités"] == 100000
    assert passif["Concours bancaires courants"] == 300000


def test_asso_layout_unchanged(session):
    fy = _fy(session)
    _post(session, fy, [("756", 0, 5000), ("512", 5000, 0)])
    rows = list(compte_resultat_rows(build_compte_resultat(fy), "asso"))
    labels = [label.strip() for _k, label, _n, _p in rows]
    assert "Cotisations" in labels
    assert "CONTRIBUTIONS VOLONTAIRES EN NATURE" in labels
    assert labels.count("EXCÉDENT") == 1
    bilan = build_bilan(fy)
    assert any(l["label"] == "Fonds dédiés" for l in bilan["passif"])


def test_report_templates_render_for_both_charts(app, session):
    fy = _sci_year(session)
    for chart in ("asso", "sci"):
        with app.test_request_context():
            g.current_instance = SimpleNamespace(chart=chart)
            data = build_compte_resultat(fy, chart=chart)
            html = render_template(
                "reports/compte_resultat.html",
                rows=list(compte_resultat_rows(data, chart)),
                fy=fy, fy_prev=None, fiscal_years=[fy], now_date=date.today(),
            )
            assert ("Loyers et fermages" in html) == (chart == "sci")
            assert ("Cotisations" in html) == (chart == "asso")
            html = render_template(
                "reports/bilan.html", data=build_bilan(fy, chart=chart),
                fy=fy, fy_prev=None, fiscal_years=[fy], chart=chart,
            )
            assert "TOTAL ACTIF" in html
            assert ("Fonds dédiés" in html) == (chart == "asso")


def test_ods_export_for_both_charts(session):
    from app.views.reports import _build_cdr_ods

    fy = _sci_year(session)
    for chart in ("asso", "sci"):
        data = build_compte_resultat(fy, chart=chart)
        assert _build_cdr_ods(data, fy, None, chart)[:2] == b"PK"
