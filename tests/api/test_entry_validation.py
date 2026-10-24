"""Lot F1 : validation des écritures par lots, garde, contrepassation, historique."""
import json
from datetime import date

import pytest

from app.extensions import db
from app.models import (
    Account, BankAccount, BankTransaction, EntryEvent, FiscalYear, Journal, JournalEntry, JournalLine, Project,
    ValidationBatch,
)
from app.services import closing, fec, organization, projects, validation
from app.services.ledger import LedgerError, LedgerGuardError, delete_entries, post_entry, reverse
from app.services.reconciler import reconcile, suggest_matches


def _error(resp, status):
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()["error"]


@pytest.fixture()
def books(app, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "instance_path", str(tmp_path))
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    accounts = {c: Account(code=c, label=f"Compte {c}", account_type="OTHER") for c in ("512100", "6061", "706")}
    db.session.add_all([fy, Journal(code="BQ", label="Banque"), Journal(code="OD", label="Opérations diverses"),
                        *accounts.values()])
    db.session.commit()
    db.session.add(BankAccount(label="Banque", account_id=accounts["512100"].id))
    db.session.commit()
    return fy


def _ids():
    return {c: a.id for c, a in ((a.code, a) for a in Account.query.all())}


def _entry(fy, journal, day, cents=1000, desc="Vente"):
    a = _ids()
    j = Journal.query.filter_by(code=journal).one()
    return post_entry(fy.id, j.id, day, desc, [
        {"account_id": a["512100"], "debit_cents": cents}, {"account_id": a["706"], "credit_cents": cents}])


def _numbers():
    return {e.description: (e.journal.code, e.validation_number) for e in JournalEntry.query.all()}


def test_batches_number_after_existing_numbers(books, login_as):
    _entry(books, "BQ", date(2026, 3, 1), desc="mars")
    feb = _entry(books, "BQ", date(2026, 2, 1), desc="février")
    _entry(books, "OD", date(2026, 1, 10), desc="od")
    client = login_as()
    assert client.post("/api/v1/entries/validation", json={"ids": [feb.id]}).get_json()["validated"] == 1
    _entry(books, "BQ", date(2026, 1, 5), desc="janvier")  # antérieure, saisie après
    resp = client.post("/api/v1/entries/validation", json={"fiscal_year_id": books.id, "until": "2026-03-31"})
    assert resp.get_json()["validated"] == 3
    # Numéros à la suite du lot précédent, ordre (date, id) dans le lot : jamais renumérotés.
    assert _numbers() == {"février": ("BQ", 1), "janvier": ("BQ", 2), "mars": ("BQ", 3), "od": ("OD", 1)}
    assert [b.kind for b in ValidationBatch.query.order_by(ValidationBatch.id)] == ["manual", "until"]
    assert validation.draft_counts(books)["drafts"] == 0


def test_validated_entry_is_intangible(books, login_as):
    entry = _entry(books, "BQ", date(2026, 3, 1))
    validation.validate(books, [entry], "manual")
    db.session.commit()
    client = login_as()
    base = f"/api/v1/entries/{entry.id}"
    payload = {"fiscal_year_id": books.id, "journal_id": entry.journal_id, "entry_date": "2026-03-02",
               "lines": [{"account_id": l.account_id, "debit_cents": l.debit_cents, "credit_cents": l.credit_cents}
                         for l in entry.lines]}
    assert _error(client.put(base, json=payload), 409)["code"] == "entry_validated"
    assert "validée" in _error(client.delete(base), 409)["message"]
    assert _error(client.get(f"/api/v1/entries/form?entry_id={entry.id}"), 409)["code"] == "entry_validated"
    # N'importe quel chemin : la garde refuse au flush.
    entry.lines[0].label = "modifié"
    with pytest.raises(LedgerGuardError):
        db.session.flush()
    db.session.rollback()
    db.session.add(JournalLine(entry_id=entry.id, account_id=_ids()["6061"], debit_cents=1))
    with pytest.raises(LedgerGuardError):
        db.session.flush()
    db.session.rollback()
    entry.validation_number = 7  # hors validation
    with pytest.raises(LedgerGuardError):
        db.session.flush()
    db.session.rollback()
    # Colonnes libres : projet.
    project = Project(name="Jardin")
    db.session.add(project)
    db.session.commit()
    projects.set_line_project(entry.lines[1], project.id)
    assert entry.lines[1].project_id == project.id
    with pytest.raises(projects.ProjectError):
        projects.split_line(entry.lines[1], [{"project_id": project.id, "amount_cents": 500},
                                              {"project_id": None, "amount_cents": 500}])
    detail = client.get(base).get_json()
    assert detail["validated"] and not detail["editable"] and detail["validation_number"] == 1


def test_undo_only_last_batch(books, login_as):
    first = _entry(books, "BQ", date(2026, 1, 1), desc="un")
    validation.validate(books, [first], "manual")
    second = _entry(books, "BQ", date(2026, 2, 1), desc="deux")
    validation.validate(books, [second], "manual")
    db.session.commit()
    base = f"/api/v1/fiscal-years/{books.id}/validation-batches"
    admin = login_as(is_admin=True)
    batches = admin.get(base).get_json()["items"]
    assert [b["undoable"] for b in batches] == [True, False]
    assert "Motif" in _error(admin.post(f"{base}/last/undo", json={}), 409)["message"]
    assert admin.post(f"{base}/last/undo", json={"reason": "erreur de date"}).status_code == 200
    assert _numbers() == {"un": ("BQ", 1), "deux": ("BQ", None)}
    validation.validate(books, [db.session.get(JournalEntry, second.id)], "manual")
    assert _numbers()["deux"] == ("BQ", 2)


def test_undo_reserved_to_admin(books, login_as):
    validation.validate(books, [_entry(books, "BQ", date(2026, 1, 1))], "manual")
    db.session.commit()
    _error(login_as().post(f"/api/v1/fiscal-years/{books.id}/validation-batches/last/undo", json={"reason": "x"}), 403)


def test_fec_numbers_unchanged_by_provisional_close(books):
    org = organization.get()
    org.siren = "732829320"
    db.session.commit()
    _entry(books, "BQ", date(2026, 3, 1), desc="mars")
    validation.validate_until(books, date(2026, 3, 31))
    _entry(books, "BQ", date(2026, 2, 1), desc="février")
    _entry(books, "OD", date(2026, 1, 1), desc="od")
    db.session.commit()
    preview, errors, _warnings, problems = fec.preview(books)
    assert not errors and not problems
    assert _numbers()["février"] == ("BQ", None)  # essai à blanc annulé
    books.status = "provisional"
    db.session.flush()
    fec.validate(books)
    db.session.commit()
    final = fec.build(books)
    numbers = lambda f: [row.split("\t")[2] for row in f.content.decode("iso-8859-15").split("\r\n")[1:] if row]
    assert numbers(preview) == numbers(final)
    assert _numbers() == {"mars": ("BQ", 1), "février": ("BQ", 2), "od": ("OD", 1)}
    assert fec.verify(final.content) == []


def test_reverse_reconciled_entry(books, login_as):
    entry = _entry(books, "BQ", date(2026, 3, 1))
    ba = BankAccount.query.one()
    txn = BankTransaction(bank_account_id=ba.id, fitid="T1", transaction_date=date(2026, 3, 1), amount_cents=1000,
                          label="VIR")
    db.session.add(txn)
    db.session.commit()
    bank_line = next(l for l in entry.lines if l.debit_cents)
    reconcile(txn.id, bank_line.id)
    validation.validate(books, [entry], "manual")
    db.session.commit()
    client = login_as()
    resp = client.post(f"/api/v1/entries/{entry.id}/reverse", json={"date": "2026-03-10", "reason": "doublon"})
    assert resp.status_code == 200, resp.get_json()
    reversal = db.session.get(JournalEntry, resp.get_json()["item"]["id"])
    assert reversal.reverses_entry_id == entry.id and reversal.entry_date == date(2026, 3, 10)
    assert "doublon" in reversal.description and not reversal.is_validated
    assert sorted((l.debit_cents, l.credit_cents) for l in reversal.lines) == [(0, 1000), (1000, 0)]
    db.session.refresh(txn)
    assert not txn.reconciled and txn.journal_line_id is None
    assert suggest_matches(txn.id) == []  # ni l'écriture contrepassée ni sa contrepassation
    assert client.get(f"/api/v1/entries/{entry.id}").get_json()["reversal"]["id"] == reversal.id
    assert "déjà" in _error(client.post(f"/api/v1/entries/{entry.id}/reverse", json={}), 409)["message"]
    with pytest.raises(LedgerError):
        reverse(reversal)


def test_services_reverse_validated_entries(books):
    entry = _entry(books, "BQ", date(2026, 3, 1))
    validation.validate(books, [entry], "manual")
    db.session.commit()
    (refused,) = delete_entries([entry.id])
    assert refused["status"] == "error"
    (outcome,) = delete_entries([entry.id], reverse_validated=True)
    assert outcome["status"] == "reversed" and outcome["reversal"]
    assert JournalEntry.query.filter_by(reverses_entry_id=entry.id).count() == 1


def test_history_snapshots(books, login_as):
    client = login_as()
    a = _ids()
    bq = Journal.query.filter_by(code="BQ").one()
    payload = {"fiscal_year_id": books.id, "journal_id": bq.id, "entry_date": "2026-03-01", "description": "Vente",
               "lines": [{"account_id": a["512100"], "debit_cents": 1000}, {"account_id": a["706"], "credit_cents": 1000}]}
    entry_id = client.post("/api/v1/entries", json=payload).get_json()["id"]
    payload["lines"][0]["debit_cents"] = payload["lines"][1]["credit_cents"] = 1500
    assert client.put(f"/api/v1/entries/{entry_id}", json=payload).status_code == 200
    client.post("/api/v1/entries/validation", json={"ids": [entry_id]})
    items = client.get(f"/api/v1/entries/{entry_id}/history").get_json()["items"]
    assert [i["action"] for i in items] == ["create", "update", "validate"]
    assert items[0]["snapshot"]["lines"][0]["debit_cents"] == 1000
    assert items[1]["snapshot"]["lines"][0]["debit_cents"] == 1500
    assert items[0]["user"] == "user@example.org" and items[0]["origin"].startswith("api:")
    other = _entry(books, "BQ", date(2026, 4, 1), desc="à supprimer")
    other_id = other.id
    delete_entries([other_id])
    deleted = EntryEvent.query.filter_by(entry_id=other_id).order_by(EntryEvent.id).all()
    assert [e.action for e in deleted] == ["create", "delete"]
    assert json.loads(deleted[-1].snapshot_json)["description"] == "à supprimer"


def test_reopen_undoes_closing_batch(books):
    early = _entry(books, "BQ", date(2026, 1, 1), desc="validée avant")
    validation.validate(books, [early], "manual")
    _entry(books, "BQ", date(2026, 6, 1), desc="brouillard")
    for step in closing.DECIDED_BEFORE_CLOSE:
        closing.set_step(books, step, "skipped", note="test de réouverture")
    closing.close_provisional(books)
    assert _numbers()["brouillard"] == ("BQ", 2)
    closing.reopen(books, reason="facture oubliée")
    assert _numbers() == {"validée avant": ("BQ", 1), "brouillard": ("BQ", None)}
    assert books.status == "open"


def test_drafts_on_dashboard_and_closing_checks(books, login_as):
    _entry(books, "BQ", date(2026, 1, 1))
    checks = {c.key: c for c in closing.checks(books)}
    assert checks["drafts"].count == 1
    assert login_as().get("/api/v1/dashboard").get_json()["drafts"]["drafts"] == 1
