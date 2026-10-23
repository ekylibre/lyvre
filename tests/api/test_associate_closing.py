"""Module « Associés », lot A4 : intérêts des comptes courants et répartition proposée du résultat."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, FiscalYear, Instance, Journal, JournalEntry
from app.models.associate import ShareMovement, ShareMovementLine
from app.services import associates, closing, organization
from app.services.ledger import post_entry


@pytest.fixture()
def books(app, login_as):
    client = login_as(role="admin")
    Instance.query.one().has_associates = True
    for code, label, kind in (("455", "Associés", "TIERS"), ("512", "Banque", "BANK"), ("66", "Charges financières", "EXPENSE")):
        db.session.add(Account(code=code, label=label, account_type=kind))
    db.session.add_all([FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)),
                        Journal(code="BQ", label="Banque")])
    db.session.commit()
    return client


def _deposit(associate, day, cents):
    fy = FiscalYear.query.filter(FiscalYear.start_date <= day, FiscalYear.end_date >= day).one()
    bank = Account.query.filter_by(code="512").one()
    post_entry(fy.id, Journal.query.filter_by(code="BQ").one().id, day, "Apport", [
        {"account_id": bank.id, "debit_cents": max(cents, 0), "credit_cents": max(-cents, 0)},
        {"account_id": associate.account_id, "debit_cents": max(-cents, 0), "credit_cents": max(cents, 0)}])


def test_interest_day_by_day(books):
    fy = FiscalYear.query.one()
    lender = associates.create({"new_name": "Prêteur", "interest_rate": "2"})
    late = associates.create({"new_name": "Tardif"})
    debtor = associates.create({"new_name": "Débiteur", "interest_rate": "5"})
    _deposit(lender, date(2026, 1, 1), 10_000_000)            # 100 000 € toute l'année
    _deposit(late, date(2026, 7, 2), 3_650_000)               # 36 500 € sur 183 jours au taux de la structure
    _deposit(debtor, date(2026, 1, 1), -100_000)              # solde débiteur : pas d'intérêts
    organization.get().associate_interest_rate_bp = 100  # 1 %
    db.session.commit()

    preview = books.get(f"/api/v1/fiscal-years/{fy.id}/associate-interest").get_json()
    rows = {r["name"]: r for r in preview["rows"]}
    assert rows["Prêteur"]["interest_cents"] == 200_000 and rows["Prêteur"]["rate"] == "2"
    assert rows["Tardif"]["interest_cents"] == round(3_650_000 * 183 * 100 / 10000 / 365) == 18_300
    assert rows["Tardif"]["rate"] == "1"
    assert rows["Débiteur"]["interest_cents"] == 0

    posted = books.post(f"/api/v1/fiscal-years/{fy.id}/associate-interest")
    assert posted.status_code == 200, posted.get_json()
    entries = JournalEntry.query.filter(JournalEntry.source_ref.like("INTEREST:%")).all()
    assert len(entries) == 2 and all(e.entry_date == date(2026, 12, 31) and e.journal.code == "AS" for e in entries)
    assert Account.query.filter_by(code="6615").one().parent.code == "66"
    assert associates.balance(lender.account_id) == 10_200_000

    # Relancer remplace les écritures (les intérêts déjà passés n'entrent pas dans le calcul).
    again = books.post(f"/api/v1/fiscal-years/{fy.id}/associate-interest").get_json()
    assert again["total_cents"] == 218_300 and len(again["entries"]) == 2
    assert JournalEntry.query.filter(JournalEntry.source_ref.like("INTEREST:%")).count() == 2
    statement = books.get(f"/api/v1/associates/{lender.id}/statement").get_json()
    assert statement["lines"][-1]["origin"] == "Intérêts"


def test_no_interest_at_zero_rate_or_closed_year(books):
    fy = FiscalYear.query.one()
    lender = associates.create({"new_name": "Prêteur"})
    _deposit(lender, date(2026, 1, 1), 1_000_000)
    body = books.post(f"/api/v1/fiscal-years/{fy.id}/associate-interest").get_json()
    assert body["total_cents"] == 0 and "Aucun intérêt" in body["notices"][0]["message"]
    assert Account.query.filter_by(code="6615").first() is None
    fy.status = "closed"
    db.session.commit()
    assert books.post(f"/api/v1/fiscal-years/{fy.id}/associate-interest").status_code == 409


def test_allocation_proposal(books, monkeypatch):
    fy = FiscalYear.query.one()
    parent, child, other = (associates.create({"new_name": n}) for n in ("Parent", "Enfant", "Zoé"))
    db.session.add(ShareMovement(movement_date=date(2026, 1, 1), kind="opening", nominal_cents=1000, lines=[
        ShareMovementLine(associate_id=parent.id, nature="usufruct", parts=300),
        ShareMovementLine(associate_id=child.id, nature="bare", parts=300),
        ShareMovementLine(associate_id=child.id, nature="full", parts=700)]))
    db.session.commit()
    monkeypatch.setattr(closing, "result_to_allocate", lambda _fy: 1_200_000)
    body = books.get(f"/api/v1/fiscal-years/{fy.id}/allocation-proposal").get_json()
    assert body["total_parts"] == 1000
    assert [(l["name"], l["account_code"], l["amount_cents"]) for l in body["lines"]] == [
        ("Enfant", "4551002", 840_000), ("Parent", "4551001", 360_000)]   # nu-propriétaire : rien sur ses 300 NP

    # Centimes au plus fort reste, départagés par le nom ; un déficit se répartit de même.
    db.session.add(ShareMovement(movement_date=date(2026, 6, 1), kind="subscription", nominal_cents=1000, lines=[
        ShareMovementLine(associate_id=other.id, nature="full", parts=1000)]))
    db.session.commit()
    monkeypatch.setattr(closing, "result_to_allocate", lambda _fy: -101)
    lines = books.get(f"/api/v1/fiscal-years/{fy.id}/allocation-proposal").get_json()["lines"]
    assert sum(l["amount_cents"] for l in lines) == 101
    # 101 × 700 / 2000 = 35,35 ; × 300 = 15,15 ; × 1000 = 50,5 : le centime restant va à Zoé.
    assert {l["name"]: l["amount_cents"] for l in lines} == {"Enfant": 35, "Parent": 15, "Zoé": 51}
