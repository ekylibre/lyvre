"""Phase A.3 : validation (numérotation) des écritures et fichier des écritures comptables (FEC)."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, Entity, FiscalYear, Journal, JournalEntry
from app.services import fec, organization
from app.services.ledger import post_entry

SIREN = "732829320"


@pytest.fixture()
def books(app, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "instance_path", str(tmp_path))
    prev = FiscalYear(label="2025", start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    journals = {c: Journal(code=c, label=l) for c, l in (("AN", "À-nouveaux"), ("BQ", "Banque"), ("AC", "Achats"))}
    accounts = {c: Account(code=c, label=l, account_type=t) for c, l, t in (
        ("512100", "Banque CIC", "ASSET"), ("6061", "Fournitures — énergie", "EXPENSE"),
        ("401001", "Fournisseur EDF", "TIERS"), ("110", "Report à nouveau", "EQUITY"), ("706", "Prestations", "REVENUE"))}
    db.session.add_all([prev, fy, *journals.values(), *accounts.values(),
                        Entity(name="EDF œuvre", account_code="401001")])
    db.session.commit()
    a, j = {c: x.id for c, x in accounts.items()}, {c: x.id for c, x in journals.items()}

    def entry(journal, day, desc, lines, source="MANUAL"):
        return post_entry(fy.id, j[journal], day, desc, lines, source=source)

    entry("BQ", date(2026, 3, 5), "Prestation\tclient", [
        {"account_id": a["512100"], "label": "Virement 😀 reçu", "debit_cents": 123456},
        {"account_id": a["706"], "label": "Prestation", "credit_cents": 123456}])
    entry("AC", date(2026, 2, 1), "Facture EDF", [
        {"account_id": a["6061"], "label": "Électricité €", "debit_cents": 5000},
        {"account_id": a["401001"], "label": "EDF", "credit_cents": 5000}])
    entry("BQ", date(2026, 1, 15), "Règlement EDF", [
        {"account_id": a["401001"], "label": "EDF", "debit_cents": 5000},
        {"account_id": a["512100"], "label": "EDF", "credit_cents": 5000}])
    entry("AN", date(2026, 1, 1), "À-nouveaux", [
        {"account_id": a["512100"], "label": "Solde", "debit_cents": 1000},
        {"account_id": a["110"], "label": "Report", "credit_cents": 1000}], source="OPENING")
    return fy


def _provisional(fy):
    fy.status = "provisional"
    db.session.flush()
    fec.validate(fy)
    db.session.commit()


def _set_siren():
    org = organization.get()
    org.siren = SIREN
    db.session.commit()


def test_checks_before_export(books):
    errors, _ = fec.check(books)
    assert any("SIREN" in e for e in errors) and any("Exercice ouvert" in e for e in errors)
    with pytest.raises(fec.FecError):
        fec.build(books)


def test_validation_numbers_each_journal_continuously_by_date(books):
    _provisional(books)
    rows = {(e.journal.code, e.validation_number): e.entry_date for e in JournalEntry.query.all()}
    assert rows == {("AN", 1): date(2026, 1, 1), ("AC", 1): date(2026, 2, 1),
                    ("BQ", 1): date(2026, 1, 15), ("BQ", 2): date(2026, 3, 5)}
    assert all(e.validated_at is not None for e in JournalEntry.query.all())
    before = {e.id: e.validation_number for e in JournalEntry.query.all()}
    fec.validate(books)  # déterministe
    assert {e.id: e.validation_number for e in JournalEntry.query.all()} == before
    fec.unvalidate(books)
    assert {e.validation_number for e in JournalEntry.query.all()} == {None}


def test_fec_file_format(books):
    _set_siren()
    _provisional(books)
    fec_file = fec.build(books)
    assert fec_file.filename == f"{SIREN}FEC20261231.txt"
    assert (fec_file.lines, fec_file.entries, fec_file.total_debit_cents) == (8, 4, 134456)
    text = fec_file.content.decode("iso-8859-15")
    rows = [r.split("\t") for r in text.split("\r\n") if r]
    assert rows[0] == list(fec.FIELDS) and all(len(r) == 18 for r in rows)
    body = [dict(zip(fec.FIELDS, r)) for r in rows[1:]]
    assert [b["EcritureNum"] for b in body] == ["AN000001", "AN000001", "BQ000001", "BQ000001",
                                                  "AC000001", "AC000001", "BQ000002", "BQ000002"]
    first_bq = body[6]
    assert first_bq["EcritureDate"] == "20260305" and first_bq["Debit"] == "1234,56" and first_bq["Credit"] == "0,00"
    assert first_bq["EcritureLib"] == "Virement ? reçu"  # émoji hors ISO-8859-15 remplacé
    assert next(b for b in body if b["CompteNum"] == "6061")["CompteLib"] == "Fournitures - énergie"
    supplier = next(b for b in body if b["CompteNum"] == "401001")
    assert (supplier["CompAuxNum"], supplier["CompAuxLib"]) == ("401001", "EDF œuvre")
    assert next(b for b in body if b["CompteNum"] == "6061")["EcritureLib"] == "Électricité €"
    assert all(b["ValidDate"] and b["PieceRef"] for b in body)
    assert fec.verify(fec_file.content) == []


def test_verify_detects_anomalies(books):
    _set_siren()
    _provisional(books)
    good = fec.build(books).content.decode("iso-8859-15")
    unbalanced = good.replace("\t1234,56\t0,00\t", "\t1234,57\t0,00\t", 1)
    assert any("déséquilibrée" in p for p in fec.verify(unbalanced.encode("iso-8859-15")))
    gap = good.replace("BQ000002", "BQ000003")
    assert any("discontinue" in p for p in fec.verify(gap.encode("iso-8859-15")))
    assert fec.verify(good.replace("JournalCode", "Journal", 1).encode("iso-8859-15"))
    assert "Caractères de contrôle dans le fichier." in fec.verify(good.replace("Banque CIC", "Banque\x01CIC").encode("iso-8859-15"))


def test_warning_without_opening_entries(books):
    _set_siren()
    JournalEntry.query.filter_by(source="OPENING").delete()
    db.session.commit()
    _provisional(books)
    _, warnings = fec.check(books)
    assert any("à-nouveau" in w for w in warnings)


def test_api_check_and_download_for_accountant(books, login_as):
    client = login_as(role="accountant")
    body = client.get(f"/api/v1/fiscal-years/{books.id}/fec/check").get_json()
    assert body["errors"] and body["download_url"] is None
    assert client.get(f"/fiscal-years/{books.id}/fec").status_code == 409
    _set_siren()
    _provisional(books)
    body = client.get(f"/api/v1/fiscal-years/{books.id}/fec/check").get_json()
    assert body["errors"] == [] and body["problems"] == [] and body["stats"]["entries"] == 4
    resp = client.get(body["download_url"])
    assert resp.status_code == 200 and resp.headers["Content-Disposition"].endswith(f'{SIREN}FEC20261231.txt')
    assert resp.data.decode("iso-8859-15").startswith("JournalCode\tJournalLib")


def test_provisional_close_numbers_entries(books, login_as, closing_ready):
    client = login_as()
    closing_ready(books)
    client.post(f"/api/v1/fiscal-years/{books.id}/close")
    assert {e.validation_number for e in JournalEntry.query.all()} == {1, 2}


def test_freeze_on_final_close(books, login_as, app):
    _set_siren()
    _provisional(books)
    books.status = "closed"
    fec_file = fec.freeze(books)
    db.session.commit()
    assert books.fec_sha256 == fec_file.sha256 and books.fec_path.endswith(f"fec/{SIREN}FEC20261231.txt")
    client = login_as(role="accountant")
    assert client.get(f"/fiscal-years/{books.id}/fec").data == fec_file.content
    import os
    with open(os.path.join(app.instance_path, books.fec_path), "ab") as fh:
        fh.write(b"x")
    assert client.get(f"/fiscal-years/{books.id}/fec").status_code == 409  # altéré
    with pytest.raises(fec.FecError):
        fec.unvalidate(books)
