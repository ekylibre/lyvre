"""Solde bancaire (Banque › Comptes bancaires) : somme des transactions, solde d'ouverture saisi et
écriture d'apport initial."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, BankAccount, BankTransaction, FiscalYear, JournalEntry, Journal
from app.models.journal_entry import SOURCE_OPENING
from app.services import bank_balance
from app.services.bank_balance import BankBalanceError
from app.services.ledger import post_entry

TODAY = date(2026, 11, 2)


@pytest.fixture()
def setup(app):
    bank = Account(code="512000", label="Banque")
    fonds = Account(code="102", label="Fonds propres sans droit de reprise", account_type="EQUITY")
    fy25 = FiscalYear(label="2025", start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
    fy26 = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    db.session.add_all([bank, fonds, fy25, fy26])
    db.session.flush()
    ba = BankAccount(label="CIC", account_id=bank.id)
    db.session.add(ba)
    db.session.flush()
    for i, (day, amount, reversed_) in enumerate([
        (date(2025, 12, 15), 5000, False), (date(2026, 1, 10), 10000, False),
        (date(2026, 3, 5), -2500, False), (date(2026, 4, 1), -999, True), (date(2026, 12, 20), 700, False),
    ]):
        db.session.add(BankTransaction(bank_account_id=ba.id, fitid=f"t{i}", transaction_date=day,
                                       amount_cents=amount, is_reversed=reversed_))
    db.session.commit()
    return {"ba": ba, "bank": bank, "fonds": fonds, "fy25": fy25, "fy26": fy26}


def test_without_opening_sums_fiscal_year(setup):
    result = bank_balance.bank_balance(setup["ba"], setup["fy26"], today=TODAY)
    # Transactions de 2026 jusqu'à aujourd'hui, hors annulée et hors future.
    assert result == {"balance_cents": 7500, "at": "2026-11-02", "opening_missing": True, "fiscal_year": "2026"}


def test_opening_is_chained_across_fiscal_years(setup):
    ba = setup["ba"]
    ba.opening_balance_cents, ba.opening_balance_date = 100000, date(2025, 1, 1)
    db.session.commit()
    result = bank_balance.bank_balance(ba, setup["fy26"], today=TODAY)
    assert result["balance_cents"] == 100000 + 5000 + 10000 - 2500
    assert result["opening_missing"] is False
    # Solde d'ouverture postérieur à la période : manquant pour 2025.
    ba.opening_balance_date = date(2026, 1, 1)
    db.session.commit()
    assert bank_balance.bank_balance(ba, setup["fy25"], today=TODAY)["opening_missing"] is True


def test_display_fiscal_year(setup):
    assert bank_balance.display_fiscal_year(TODAY) == setup["fy26"]
    assert bank_balance.display_fiscal_year(date(2030, 1, 1)) == setup["fy26"]
    assert bank_balance.display_fiscal_year(date(2020, 1, 1)) == setup["fy25"]


def test_default_opening_date(setup):
    # Exercice de la première transaction (15/12/2025).
    assert bank_balance.default_opening_date(setup["ba"]) == date(2025, 1, 1)
    setup["ba"].qonto_sync_from = date(2026, 1, 1)
    assert bank_balance.default_opening_date(setup["ba"]) == date(2026, 1, 1)


def test_set_opening_posts_contribution_entry(setup):
    ba = setup["ba"]
    entry = bank_balance.set_opening(ba, {"amount_cents": 50000, "date": "2025-01-01", "post_entry": True,
                                          "counterpart": str(setup["fonds"].id)}, "asso")
    assert ba.opening_balance_cents == 50000 and ba.opening_entry_id == entry.id
    lines = {l.account.code: (l.debit_cents, l.credit_cents) for l in entry.lines}
    assert lines == {"512000": (50000, 0), "102": (0, 50000)}
    assert entry.source == bank_balance.SOURCE_BANK_OPENING and entry.journal.code == "OD"

    # Nouvelle saisie : l'ancienne écriture est remplacée, découvert → crédit 512.
    entry2 = bank_balance.set_opening(ba, {"amount_cents": -3000, "date": "2025-01-01", "post_entry": True,
                                           "counterpart": str(setup["fonds"].id)}, "asso")
    assert JournalEntry.query.count() == 1  # (SQLite peut redonner le même id)
    assert {l.account.code: (l.debit_cents, l.credit_cents) for l in entry2.lines} == \
        {"512000": (0, 3000), "102": (3000, 0)}

    # Retrait : solde et écriture supprimés.
    assert bank_balance.set_opening(ba, {"amount_cents": None}, "asso") is None
    assert ba.opening_balance_date is None and ba.opening_entry_id is None
    assert JournalEntry.query.count() == 0


def test_set_opening_without_entry(setup):
    ba = setup["ba"]
    assert bank_balance.set_opening(ba, {"amount_cents": 1234, "date": "2026-01-01"}, "asso") is None
    assert ba.opening_balance_cents == 1234 and ba.opening_entry_id is None


def test_entry_refused_when_ledger_already_open(setup):
    ba = setup["ba"]
    journal = Journal(code="AN", label="À-nouveaux")
    db.session.add(journal)
    db.session.flush()
    post_entry(setup["fy26"].id, journal.id, date(2026, 1, 1), "À-nouveaux", [
        {"account_id": setup["bank"].id, "debit_cents": 800, "credit_cents": 0},
        {"account_id": setup["fonds"].id, "debit_cents": 0, "credit_cents": 800},
    ], source=SOURCE_OPENING)
    assert bank_balance.opening_payload(ba)["entry_allowed"] is False
    with pytest.raises(BankBalanceError, match="déjà repris"):
        bank_balance.set_opening(ba, {"amount_cents": 800, "date": "2026-01-01", "post_entry": True,
                                      "counterpart": str(setup["fonds"].id)}, "asso")
    assert ba.opening_balance_date is None


def test_counterpart_options_and_creation(setup):
    asso = bank_balance.counterpart_options("asso")
    assert [o["label"] for o in asso] == ["102 — Fonds propres sans droit de reprise",
                                          "103 — Fonds propres avec droit de reprise (à créer)"]
    societe = bank_balance.counterpart_options("societe")
    assert [o["value"] for o in societe] == ["new:101", "new:108"]

    entry = bank_balance.set_opening(setup["ba"], {"amount_cents": 1000, "date": "2025-01-01", "post_entry": True,
                                                   "counterpart": "new:101"}, "societe")
    assert Account.query.filter_by(code="101").one().label == "Capital"
    assert "101" in {l.account.code for l in entry.lines}
    # Un compte hors des préfixes de la structure est refusé.
    with pytest.raises(BankBalanceError):
        bank_balance.set_opening(setup["ba"], {"amount_cents": 1000, "date": "2025-01-01", "post_entry": True,
                                               "counterpart": str(setup["fonds"].id)}, "societe")


def test_api_list_and_opening(setup, login_as):
    client = login_as()
    item = client.get("/api/v1/bank-accounts").get_json()["items"][0]
    assert item["bank_balance"]["opening_missing"] is True

    opening = client.get(f"/api/v1/bank-accounts/{setup['ba'].id}/opening").get_json()
    assert opening["item"]["proposed_date"] == "2025-01-01" and opening["item"]["entry_allowed"] is True
    assert opening["meta"]["counterparts"][0]["label"].startswith("102")

    resp = client.put(f"/api/v1/bank-accounts/{setup['ba'].id}/opening",
                      json={"amount_cents": 50000, "date": "2025-01-01", "post_entry": True,
                            "counterpart": str(setup["fonds"].id)})
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["item"]["bank_balance"]["opening_missing"] is False
    assert body["opening"]["entry"]["counterpart"].startswith("102")
    assert len(body["notices"]) == 2

    bad = client.put(f"/api/v1/bank-accounts/{setup['ba'].id}/opening", json={"amount_cents": 1, "date": "x"})
    assert bad.status_code == 422 and "date" in bad.get_json()["error"]["fields"]
