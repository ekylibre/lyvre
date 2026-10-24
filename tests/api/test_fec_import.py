"""Lot F6 : reprise d'historique (FEC : historique complet, soldes d'ouverture ; tableur)."""
import io
from datetime import date

import pytest
from sqlalchemy import delete

from app.extensions import db
from app.models import (
    Account, AccountMapping, Entity, EntryEvent, FiscalYear, ImportProfile, Journal, JournalEntry, JournalLine,
    Lettering, ValidationBatch,
)
from app.services import fec, fec_import, lettering, organization, validation
from app.services.ledger import post_entry, trial_balance

SIREN = "732829320"


def _error(resp, status):
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()["error"]


@pytest.fixture()
def books(app, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "instance_path", str(tmp_path))
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    accounts = {c: Account(code=c, label=l, account_type="OTHER") for c, l in (
        ("401001", "EDF"), ("512100", "Banque"), ("6061", "Énergie"), ("706", "Prestations"), ("120", "Excédent"),
        ("129", "Déficit"), ("110", "Report"))}
    db.session.add_all([fy, Journal(code="AC", label="Achats"), Journal(code="BQ", label="Banque"), *accounts.values(),
                        Entity(name="EDF", entity_type="FOURNISSEUR", account_code="401001")])
    db.session.commit()
    org = organization.get()
    org.siren = SIREN
    db.session.commit()
    a = {c: x.id for c, x in accounts.items()}
    j = {x.code: x.id for x in Journal.query.all()}
    invoice = post_entry(fy.id, j["AC"], date(2026, 2, 1), "Facture EDF", [
        {"account_id": a["6061"], "label": "Électricité", "debit_cents": 5000},
        {"account_id": a["401001"], "label": "EDF", "credit_cents": 5000}])
    paid = post_entry(fy.id, j["BQ"], date(2026, 2, 15), "Règlement EDF", [
        {"account_id": a["401001"], "label": "EDF", "debit_cents": 5000},
        {"account_id": a["512100"], "label": "EDF", "credit_cents": 5000}])
    post_entry(fy.id, j["AC"], date(2026, 11, 2), "Facture EDF novembre", [
        {"account_id": a["6061"], "label": "Électricité", "debit_cents": 7000},
        {"account_id": a["401001"], "label": "EDF", "credit_cents": 7000}])
    post_entry(fy.id, j["BQ"], date(2026, 3, 5), "Prestation", [
        {"account_id": a["512100"], "label": "Client", "debit_cents": 123456},
        {"account_id": a["706"], "label": "Prestation", "credit_cents": 123456}])
    lettering.letter([next(l for l in invoice.lines if l.account_id == a["401001"]),
                      next(l for l in paid.lines if l.account_id == a["401001"])])
    db.session.commit()
    return fy


def _balance(fy_id):
    rows, _fy = trial_balance(fy_id)
    return {r["account"].code: (r["debit_cents"], r["credit_cents"]) for r in rows}


def _export(fy):
    fy.status = "provisional"
    db.session.flush()
    fec.validate(fy)
    db.session.commit()
    return fec.build(fy)


def _wipe():
    for model in (Lettering, EntryEvent):
        db.session.execute(delete(model))
    db.session.execute(delete(JournalLine))
    db.session.execute(delete(JournalEntry))
    db.session.execute(delete(ValidationBatch))
    db.session.execute(delete(FiscalYear))
    db.session.commit()


def _post(client, url, content, filename, **form):
    data = {"file": (io.BytesIO(content), filename), **form}
    return client.post(url, data=data, content_type="multipart/form-data")


def test_round_trip_history(books, login_as):
    before = _balance(books.id)
    fec_file = _export(books)
    _wipe()
    client = login_as(is_admin=True)
    analysis = _post(client, "/api/v1/imports/fec/analyze", fec_file.content, fec_file.filename).get_json()
    assert analysis["entries"] == 4 and analysis["problems"] == [] and analysis["fiscal_year"]["end_date"] == "2026-12-31"
    assert analysis["letterings"] == 1
    plan = {r["key"]: r for r in analysis["accounts"]}
    assert plan["aux:401001:401001"]["action"] in ("existing", "mapped") and plan["6061"]["action"] == "existing"
    resp = _post(client, "/api/v1/imports/fec", fec_file.content, fec_file.filename, mode="history",
                 start_date="2026-01-01", end_date="2026-12-31")
    assert resp.status_code == 200, resp.get_json()
    fy = FiscalYear.query.one()
    assert _balance(fy.id) == before
    assert fy.status == "provisional" and fy.locked_until == date(2026, 12, 31)
    assert JournalEntry.query.filter(JournalEntry.validation_number.is_(None)).count() == 0
    (item,) = Lettering.query.all()
    assert item.code == "A" and item.origin == "import" and not item.partial
    # Réimporté, le FEC redonne le même fichier (mêmes numéros, mêmes lettrages).
    again = fec.build(fy)
    strip = lambda f: [r.split("\t")[:15] for r in f.content.decode("iso-8859-15").split("\r\n")[1:] if r]
    assert sorted(strip(again)) == sorted(strip(fec_file))
    # Exercice déjà importé : refus.
    assert "existe déjà" in _error(_post(client, "/api/v1/imports/fec", fec_file.content, fec_file.filename, mode="history",
                                        start_date="2026-01-01", end_date="2026-12-31"), 409)["message"]


def _fec_text(rows):
    header = "\t".join(fec.FIELDS)
    lines = [header] + ["\t".join(r) for r in rows]
    return ("\r\n".join(lines) + "\r\n").encode("iso-8859-15")


def _row(journal, num, day, account, label, debit, credit, aux="", aux_label="", letter=""):
    return [journal, journal, num, day, account, label, aux, aux_label, f"P{num}", day, label, debit, credit, letter, "", day, "", ""]


def test_analysis_aux_accounts_and_overrides(books, login_as):
    content = _fec_text([
        _row("AC", "1", "20250105", "401", "Fournisseurs", "0,00", "100,00", "DUPONT", "Dupont SARL"),
        _row("AC", "1", "20250105", "60610000", "Eau", "100,00", "0,00"),
    ])
    client = login_as(is_admin=True)
    plan = {r["key"]: r for r in _post(client, "/api/v1/imports/fec/analyze", content, "x.txt").get_json()["accounts"]}
    assert plan["aux:401:DUPONT"]["action"] == "create" and plan["aux:401:DUPONT"]["target_code"] == "401002"
    assert plan["60610000"]["action"] == "create"
    six = Account.query.filter_by(code="6061").one()
    resp = _post(client, "/api/v1/imports/fec/analyze", content, "x.txt", mappings=f'{{"60610000": {six.id}}}')
    assert {r["key"]: r for r in resp.get_json()["accounts"]}["60610000"]["action"] == "mapped"


def test_opening_balances(books, login_as):
    content = _fec_text([
        _row("AC", "1", "20251105", "401", "Fournisseurs", "0,00", "300,00", "DUPONT", "Dupont SARL"),
        _row("AC", "1", "20251105", "6061", "Eau", "300,00", "0,00"),
        _row("AC", "2", "20250201", "401", "Fournisseurs", "0,00", "50,00", "DUPONT", "Dupont SARL", "AB"),
        _row("AC", "2", "20250201", "6061", "Eau", "50,00", "0,00"),
        _row("BQ", "3", "20250210", "401", "Fournisseurs", "50,00", "0,00", "DUPONT", "Dupont SARL", "AB"),
        _row("BQ", "3", "20250210", "512100", "Banque", "0,00", "50,00"),
        _row("BQ", "4", "20250301", "512100", "Banque", "1000,00", "0,00"),
        _row("BQ", "4", "20250301", "706", "Prestation", "0,00", "1000,00"),
    ])
    client = login_as(is_admin=True)
    resp = _post(client, "/api/v1/imports/fec", content, "000FEC20251231.txt", mode="opening", fiscal_year_id=str(books.id))
    assert resp.status_code == 200, resp.get_json()
    entry = JournalEntry.query.filter_by(source="OPENING").one()
    rows = sorted((l.account.code, l.debit_cents, l.credit_cents) for l in entry.lines)
    # Fournisseur Dupont : seule la facture non lettrée de novembre est reprise ; banque en un solde ;
    # résultat (1 000 − 350) en 120.
    assert rows == [("120", 0, 65000), ("401002", 0, 30000), ("512100", 95000, 0)]
    assert entry.entry_date == date(2026, 1, 1)
    assert Entity.query.filter_by(name="Dupont SARL").one().account_code == "401002"
    assert AccountMapping.query.filter_by(source_code="aux:401:DUPONT").one().account.code == "401002"
    assert "à-nouveaux" in _error(_post(client, "/api/v1/imports/fec", content, "x.txt", mode="opening",
                                        fiscal_year_id=str(books.id)), 409)["message"]


def test_unbalanced_file_refused(books, login_as):
    content = _fec_text([_row("AC", "1", "20250105", "6061", "Eau", "100,00", "0,00")])
    error = _error(_post(login_as(is_admin=True), "/api/v1/imports/fec", content, "x.txt", mode="history",
                         start_date="2025-01-01", end_date="2025-12-31"), 409)
    assert error["problems"] and "déséquilibrée" in error["problems"][0]
    assert FiscalYear.query.count() == 1


def test_treasurer_cannot_import(books, login_as):
    _error(_post(login_as(), "/api/v1/imports/fec/analyze", b"x", "x.txt"), 403)


def test_sheet_csv_import_with_profile(books, login_as):
    content = ("Date;Journal;Pièce;Compte;Libellé;Débit;Crédit\n"
               "05/04/2026;OD;R-1;6061;Gaz;120,50;\n"
               "05/04/2026;OD;R-1;512100;Gaz;;120,50\n"
               "06/04/2026;OD;R-2;6062;Fioul;10;\n"
               "06/04/2026;OD;R-2;512100;Fioul;;10\n").encode("utf-8")
    client = login_as(is_admin=True)
    analysis = _post(client, "/api/v1/imports/sheet/analyze", content, "releve.csv").get_json()
    assert analysis["mapping"] == {"date": "Date", "journal": "Journal", "piece": "Pièce", "account": "Compte",
                                   "label": "Libellé", "debit": "Débit", "credit": "Crédit"}
    assert analysis["entries"] == 2 and {r["key"]: r["action"] for r in analysis["accounts"]}["6062"] == "create"
    import json
    resp = _post(client, "/api/v1/imports/sheet", content, "releve.csv", columns=json.dumps(analysis["mapping"]),
                 profile_name="Banque")
    assert resp.status_code == 200, resp.get_json()
    entries = JournalEntry.query.filter_by(source="SHEET_IMPORT").all()
    assert len(entries) == 2 and all(e.validation_number is None for e in entries)
    assert Account.query.filter_by(code="6062").one().label == "6062"
    assert ImportProfile.query.one().name == "Banque"


def test_sheet_xlsx_and_problems(books, login_as):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["Date", "Compte", "Libellé", "Montant", "Pièce"])
    ws.append([date(2026, 4, 5), "6061", "Gaz", 30, "X"])
    ws.append([date(2026, 4, 5), "512100", "Gaz", -20, "X"])
    buffer = io.BytesIO()
    wb.save(buffer)
    client = login_as(is_admin=True)
    analysis = _post(client, "/api/v1/imports/sheet/analyze", buffer.getvalue(), "ecritures.xlsx").get_json()
    assert analysis["mapping"]["amount"] == "Montant" and analysis["entries"] == 1
    assert any("déséquilibrée" in p for p in analysis["problems"])
