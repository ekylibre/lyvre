"""Services de saisie : validation centralisée, modification, création + rapprochement atomiques."""
from datetime import date

import pytest

from app.extensions import db
from app.models import (
    Account, BankAccount, BankTransaction, FiscalYear, Journal, JournalEntry, JournalLine,
)
from app.services.ledger import (
    LedgerError, post_validated_entry, update_entry, validate_entry_payload,
)


@pytest.fixture()
def base(session):
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    closed = FiscalYear(label="2025", start_date=date(2025, 1, 1), end_date=date(2025, 12, 31),
                        closed=True)
    jr = Journal(code="BQ", label="Banque")
    bank = Account(code="512", label="Banque")
    expense = Account(code="606", label="Achats non stockés")
    header = Account(code="60", label="Achats", is_header=True)
    session.add_all([fy, closed, jr, bank, expense, header])
    session.flush()
    ba = BankAccount(label="Courant", account_id=bank.id)
    session.add(ba)
    session.commit()
    return {"fy": fy, "closed": closed, "jr": jr, "bank": bank, "expense": expense,
            "header": header, "ba": ba}


def payload(b, **over):
    data = {
        "fiscal_year_id": b["fy"].id, "journal_id": b["jr"].id, "entry_date": "2026-03-15",
        "description": "  Facture EDF  ",
        "lines": [
            {"account_id": b["expense"].id, "label": "EDF", "debit_cents": 8450, "credit_cents": 0},
            {"account_id": b["bank"].id, "label": "EDF", "debit_cents": 0, "credit_cents": 8450},
        ],
    }
    data.update(over)
    return data


def test_valid_payload(base):
    clean, errors = validate_entry_payload(payload(base))
    assert errors == {}
    assert clean["fiscal_year"] is base["fy"] and clean["journal"] is base["jr"]
    assert clean["entry_date"] == date(2026, 3, 15)
    assert clean["description"] == "Facture EDF"
    assert [l["debit_cents"] for l in clean["lines"]] == [8450, 0]


@pytest.mark.parametrize("over, field, fragment", [
    ({"fiscal_year_id": None}, "fiscal_year_id", "obligatoire"),
    ({"fiscal_year_id": 9999}, "fiscal_year_id", "obligatoire"),
    ({"journal_id": "x"}, "journal_id", "obligatoire"),
    ({"entry_date": "15/03/2026"}, "entry_date", "AAAA-MM-JJ"),
    ({"entry_date": "2027-01-02"}, "entry_date", "hors de l'exercice"),
])
def test_header_errors(base, over, field, fragment):
    _clean, errors = validate_entry_payload(payload(base, **over))
    assert fragment in errors[field]


def test_closed_fiscal_year(base):
    _clean, errors = validate_entry_payload(
        payload(base, fiscal_year_id=base["closed"].id, entry_date="2025-06-01"))
    assert "clôturé" in errors["fiscal_year_id"]


def test_line_errors(base):
    lines = [
        {"account_id": base["header"].id, "debit_cents": 100},
        {"account_id": None, "credit_cents": 50},
        {"account_id": base["bank"].id, "debit_cents": 10, "credit_cents": 10},
        {"account_id": base["bank"].id, "debit_cents": -5},
        {},                                     # ligne vide ignorée
        {"account_id": None, "label": "rien"},  # idem
    ]
    _clean, errors = validate_entry_payload(payload(base, lines=lines))
    assert "regroupement" in errors["lines[0].account_id"]
    assert errors["lines[1].account_id"] == "Compte obligatoire."
    assert "soit un débit, soit un crédit" in errors["lines[2].amount"]
    assert errors["lines[3].amount"] == "Montant invalide."
    assert "lines[4].account_id" not in errors and "lines[5].account_id" not in errors


def test_balance_and_minimum_lines(base):
    lines = payload(base)["lines"]
    lines[1]["credit_cents"] = 8000
    _clean, errors = validate_entry_payload(payload(base, lines=lines))
    assert errors["lines"] == "Écriture déséquilibrée (écart de 4.50 €)."

    _clean, errors = validate_entry_payload(payload(base, lines=lines[:1]))
    assert "au moins deux lignes" in errors["lines"]

    _clean, errors = validate_entry_payload(payload(base, lines="pas une liste"))
    assert "au moins deux lignes" in errors["lines"]


def test_post_validated_entry(base):
    clean, _ = validate_entry_payload(payload(base))
    entry = post_validated_entry(clean)
    assert entry.reference == "BQ-2026-0001"
    assert JournalLine.query.filter_by(entry_id=entry.id).count() == 2


def _bank_txn(base, amount_cents, reconciled=False):
    bt = BankTransaction(bank_account_id=base["ba"].id, fitid=f"T{amount_cents}",
                         transaction_date=date(2026, 3, 15), amount_cents=amount_cents,
                         label="PRLV EDF", reconciled=reconciled)
    db.session.add(bt)
    db.session.commit()
    return bt


def test_post_and_reconcile_in_one_transaction(base):
    bt = _bank_txn(base, -8450)
    clean, _ = validate_entry_payload(payload(base))
    entry = post_validated_entry(clean, bank_transaction=bt)
    db.session.refresh(bt)
    bank_line = next(l for l in entry.lines if l.account_id == base["bank"].id)
    assert bt.reconciled and bt.journal_line_id == bank_line.id


def test_failed_reconciliation_saves_nothing(base):
    bt = _bank_txn(base, -9999)  # montant différent de la ligne banque
    clean, _ = validate_entry_payload(payload(base))
    with pytest.raises(LedgerError, match="même montant"):
        post_validated_entry(clean, bank_transaction=bt)
    assert JournalEntry.query.count() == 0
    assert db.session.get(BankTransaction, bt.id).reconciled is False


def test_already_reconciled_transaction_refused(base):
    bt = _bank_txn(base, -8450, reconciled=True)
    clean, _ = validate_entry_payload(payload(base))
    with pytest.raises(LedgerError, match="déjà rapprochée"):
        post_validated_entry(clean, bank_transaction=bt)
    assert JournalEntry.query.count() == 0


def test_update_entry_replaces_lines(base):
    clean, _ = validate_entry_payload(payload(base))
    entry = post_validated_entry(clean)
    lines = payload(base)["lines"]
    lines[0]["debit_cents"] = lines[1]["credit_cents"] = 1000
    clean, errors = validate_entry_payload(payload(base, lines=lines, description="Modifiée"))
    assert errors == {}
    update_entry(entry, clean)
    assert entry.description == "Modifiée"
    assert sorted(l.debit_cents for l in entry.lines) == [0, 1000]
    assert JournalLine.query.count() == 2


def test_update_refused_when_reconciled_or_closed(base):
    bt = _bank_txn(base, -8450)
    clean, _ = validate_entry_payload(payload(base))
    entry = post_validated_entry(clean, bank_transaction=bt)
    with pytest.raises(LedgerError, match="rapprochée"):
        update_entry(entry, clean)

    clean, _ = validate_entry_payload(payload(base))
    other = post_validated_entry(clean)
    base["fy"].closed = True
    db.session.commit()
    with pytest.raises(LedgerError, match="clôturé"):
        update_entry(other, clean)
