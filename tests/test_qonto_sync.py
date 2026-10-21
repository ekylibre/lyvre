"""Synchronisation des transactions Qonto (client simulé, aucun appel réseau)."""
from datetime import date, datetime, timedelta

import pytest

from app.extensions import db
from app.models import (
    Account, BankAccount, BankTransaction, FiscalYear, Journal, JournalEntry, Rule, SyncJob,
)
from app.services import external_config, qonto_client, qonto_sync, sync_jobs
from app.services.qonto_client import QontoError

SYNC_FROM = date(2026, 7, 1)


def tx(id_, amount_cents, side="debit", settled_at="2026-07-22T13:34:01.989Z", status="completed",
       **extra):
    return {
        "id": id_, "transaction_id": f"org-{id_}", "amount_cents": amount_cents, "side": side,
        "status": status, "settled_at": settled_at if status == "completed" else None,
        "updated_at": "2026-10-20T08:00:00.000Z", "label": extra.pop("label", "Fournisseur SA"),
        "clean_counterparty_name": extra.pop("clean_counterparty_name", "Fournisseur"),
        "reference": extra.pop("reference", None), "operation_type": extra.pop("operation_type", "transfer"),
        "note": extra.pop("note", None), "attachment_ids": extra.pop("attachment_ids", []),
        "attachment_required": extra.pop("attachment_required", True),
        "attachment_lost": extra.pop("attachment_lost", False), **extra,
    }


class FakeClient:
    """Renvoie les transactions de `self.transactions` filtrées comme l'API (statut, fenêtre)."""

    def __init__(self, transactions=(), per_page=None, fail_on_page=None, total_override=None):
        self.transactions = list(transactions)
        self.calls = []
        self.per_page = per_page
        self.fail_on_page = fail_on_page
        self.total_override = total_override

    def list_transactions(self, account_id, *, statuses, page=1, per_page=100, **window):
        self.calls.append({"account": account_id, "statuses": statuses, "page": page, **window})
        if self.fail_on_page and len(self.calls) >= self.fail_on_page:
            raise QontoError("Qonto rencontre une erreur (HTTP 503).")
        size = self.per_page or per_page
        key = "settled" if "settled_from" in window else "updated"
        start, end = window[f"{key}_from"], window[f"{key}_to"]

        def stamp(t):
            value = t["settled_at"] if key == "settled" else t["updated_at"]
            return qonto_sync._parse_utc(value) if value else None

        rows = [t for t in self.transactions
                if t["status"] in statuses and stamp(t) and start <= stamp(t) < end]
        chunk = rows[(page - 1) * size: page * size]
        total = self.total_override(start, end, len(rows)) if self.total_override else len(rows)
        return chunk, {"total_count": total, "next_page": page + 1 if page * size < len(rows) else None}


@pytest.fixture()
def ba(app):
    gl = Account(code="512", label="Banques")
    db.session.add(gl)
    db.session.commit()
    account = BankAccount(label="Qonto", account_id=gl.id, qonto_account_id="acc-1",
                          qonto_sync_from=SYNC_FROM)
    db.session.add(account)
    db.session.commit()
    return account


def _sync(ba, client):
    return qonto_sync.sync_bank_account(ba.id, client=client)


# ---------------------------------------------------------------- correspondance

def test_mapping_of_fields(ba):
    client = FakeClient([
        tx("t1", 12000, "debit", label="EDF", reference="Facture 42", operation_type="direct_debit",
           note="Électricité", attachment_ids=["a1", "a2"], clean_counterparty_name="EDF"),
        tx("t2", 50000, "credit", label="Locataire", settled_at="2026-07-31T22:30:00.000Z",
           attachment_required=False),
    ])
    result = _sync(ba, client)
    assert result["created"] == 2
    t1 = BankTransaction.query.filter_by(fitid="t1").one()
    assert (t1.amount_cents, t1.source, t1.label, t1.counterparty, t1.raw_type, t1.note) == (
        -12000, "qonto", "EDF — Facture 42", "EDF", "direct_debit", "Électricité")
    assert (t1.attachment_count, t1.attachment_required, t1.attachment_lost) == (2, True, False)
    assert t1.transaction_date == date(2026, 7, 22) and t1.value_date is None
    t2 = BankTransaction.query.filter_by(fitid="t2").one()
    assert t2.amount_cents == 50000
    assert t2.transaction_date == date(2026, 8, 1)  # 22 h 30 UTC le 31/07 = 1er août à Paris


def test_paris_date_winter_and_summer():
    assert qonto_sync.paris_date("2026-12-31T23:30:00.000Z") == date(2027, 1, 1)
    assert qonto_sync.paris_date("2026-06-30T21:59:00.000Z") == date(2026, 6, 30)
    assert qonto_sync.paris_date(None) is None


# ------------------------------------------------------------------ idempotence

def test_second_sync_creates_nothing_and_moves_cursor(ba):
    client = FakeClient([tx("t1", 1000), tx("t2", 2000)])
    first = _sync(ba, client)
    assert first["created"] == 2
    assert ba.qonto_synced_at is not None
    second = _sync(ba, client)
    assert second["created"] == 0
    assert BankTransaction.query.count() == 2


def test_update_keeps_reconciliation_and_classification(ba):
    client = FakeClient([tx("t1", 1000, note=None)])
    _sync(ba, client)
    t1 = BankTransaction.query.filter_by(fitid="t1").one()
    t1.reconciled, t1.category = True, "Énergie"
    db.session.commit()

    client.transactions = [tx("t1", 1000, note="Ajoutée", attachment_ids=["a1"],
                              updated_at=(datetime.utcnow() - timedelta(minutes=1)).isoformat() + "Z")]
    result = _sync(ba, client)
    assert result["updated"] == 1
    db.session.refresh(t1)
    assert (t1.note, t1.attachment_count, t1.reconciled, t1.category) == ("Ajoutée", 1, True, "Énergie")


def test_amount_conflict_reported_not_applied(ba):
    client = FakeClient([tx("t1", 1000)])
    _sync(ba, client)
    client.transactions = [tx("t1", 1500, updated_at=datetime.utcnow().isoformat() + "Z")]
    ba.qonto_synced_at = datetime.utcnow() - timedelta(minutes=1)
    db.session.commit()
    result = _sync(ba, client)
    assert result["conflicts"] == 1 and "1000 → -1500" in result["errors"][0]
    assert BankTransaction.query.filter_by(fitid="t1").one().amount_cents == -1000


# ------------------------------------------------------------- annulations

def test_reversed_transaction_flagged(ba):
    client = FakeClient([tx("t1", 1000), tx("t2", 2000)])
    _sync(ba, client)
    t1 = BankTransaction.query.filter_by(fitid="t1").one()
    t1.reconciled = True
    db.session.commit()
    now = datetime.utcnow().isoformat() + "Z"
    client.transactions = [tx("t1", 1000, status="reversed", updated_at=now),
                           tx("t2", 2000, status="reversed", updated_at=now),
                           tx("t3", 3000, status="reversed", updated_at=now)]
    result = _sync(ba, client)
    assert (result["reversed"], result["reversed_reconciled"], result["skipped"]) == (2, 1, 1)
    assert BankTransaction.query.filter_by(is_reversed=True).count() == 2
    assert BankTransaction.query.filter_by(fitid="t3").first() is None


# ----------------------------------------------------------------- fenêtres

def test_initial_sync_reads_monthly_windows_from_start_date(ba):
    client = FakeClient([tx("old", 1000, settled_at="2026-06-30T10:00:00.000Z"),
                         tx("t1", 1000, settled_at="2026-07-01T08:00:00.000Z")])
    result = _sync(ba, client)
    assert result["created"] == 1
    first = client.calls[0]
    assert first["statuses"] == ("completed",)
    assert first["settled_from"] == datetime(2026, 6, 30, 22, 0)  # 01/07 minuit Paris
    assert first["settled_to"] == datetime(2026, 7, 31, 22, 0)
    months = {c["settled_from"].month for c in client.calls}
    assert len(months) >= 4  # juillet → aujourd'hui


def test_incremental_sync_uses_updated_window_with_overlap(ba):
    ba.qonto_synced_at = datetime(2026, 10, 1, 12, 0)
    db.session.commit()
    client = FakeClient([])
    _sync(ba, client)
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["statuses"] == ("completed", "reversed")
    assert call["updated_from"] == datetime(2026, 10, 1, 11, 50)


def test_large_window_is_split(ba):
    ba.qonto_synced_at = datetime(2026, 10, 1)
    db.session.commit()
    client = FakeClient([], total_override=lambda start, end, n: 20000 if end - start > timedelta(days=5) else n)
    _sync(ba, client)
    assert len(client.calls) > 2
    assert all(c["updated_to"] - c["updated_from"] <= timedelta(days=5) for c in client.calls[-2:])


def test_pagination_commits_per_page(ba):
    client = FakeClient([tx(f"t{i}", 100 + i, settled_at=f"2026-07-{10 + i:02d}T10:00:00.000Z")
                         for i in range(5)], per_page=2)
    result = _sync(ba, client)
    assert result["created"] == 5 and result["read"] == 5


def test_failure_keeps_cursor_and_committed_pages(ba):
    rows = [tx(f"t{i}", 100 + i, settled_at=f"2026-07-{10 + i:02d}T10:00:00.000Z") for i in range(5)]
    client = FakeClient(rows, per_page=2, fail_on_page=3)
    with pytest.raises(QontoError):
        _sync(ba, client)
    db.session.rollback()
    assert BankTransaction.query.count() == 4  # deux pages validées
    assert db.session.get(BankAccount, ba.id).qonto_synced_at is None
    client.fail_on_page = None
    result = _sync(ba, client)
    assert result["created"] == 1 and BankTransaction.query.count() == 5


def test_future_start_date_reads_nothing(ba):
    ba.qonto_sync_from = date.today() + timedelta(days=30)
    db.session.commit()
    client = FakeClient([tx("t1", 1000)])
    assert _sync(ba, client)["created"] == 0
    assert client.calls == []


def test_unlinked_account_refused(ba):
    ba.qonto_account_id = None
    db.session.commit()
    with pytest.raises(RuntimeError, match="pas rattaché"):
        _sync(ba, FakeClient())


# --------------------------------------------------------------------- règles

def test_rules_applied_to_new_transactions_only(ba):
    db.session.add(Rule(position=1, name="EDF", label_contains="EDF", category="Énergie"))
    db.session.commit()
    client = FakeClient([tx("t1", 1000, label="EDF")])
    result = _sync(ba, client)
    assert result["rules_matched"] == 1
    assert BankTransaction.query.filter_by(fitid="t1").one().category == "Énergie"


def test_rules_can_target_operation_type_via_raw_type(ba):
    db.session.add(Rule(position=1, name="Frais", raw_type="qonto_fee", category="Frais bancaires"))
    db.session.commit()
    _sync(ba, FakeClient([tx("t1", 500, operation_type="qonto_fee", label="Qonto")]))
    assert BankTransaction.query.filter_by(fitid="t1").one().category == "Frais bancaires"


def test_rule_entry_marked_as_qonto_import(ba):
    db.session.add_all([
        FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)),
        Journal(code="BQ", label="Banque"), Account(code="627", label="Frais bancaires"),
        Rule(position=1, name="Frais", raw_type="qonto_fee", category="Frais bancaires",
             account_code="627"),
    ])
    db.session.commit()
    _sync(ba, FakeClient([tx("t1", 500, operation_type="qonto_fee", label="Qonto")]))
    entry = JournalEntry.query.one()
    assert (entry.source, entry.source_ref) == ("QONTO_IMPORT", "FITID:t1")


def test_rule_against_transaction_direction_is_refused(ba):
    db.session.add_all([
        FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)),
        Journal(code="BQ", label="Banque"), Account(code="613", label="Locations"),
        Account(code="706", label="Prestations"),
        Rule(position=1, name="Loyers", label_contains="CHENES", entity_name="Chênes",
             category="Location", account_code="613"),
        Rule(position=2, name="Ventes", label_contains="CLIENT", category="Vente", account_code="706"),
    ])
    db.session.commit()
    result = _sync(ba, FakeClient([
        tx("t1", 500000, side="credit", label="S.C.I. LES CHENES VERTS"),
        tx("t2", 1000, label="CLIENT REMBOURSE"),
    ]))
    assert result["rules_matched"] == 0 and JournalEntry.query.count() == 0
    assert [e.split(": ", 1)[1] for e in result["errors"]] == [
        "Compte « 613 » (charge) incompatible avec un encaissement — règle non appliquée.",
        "Compte « 706 » (produit) incompatible avec un décaissement — règle non appliquée.",
    ]
    t1 = BankTransaction.query.filter_by(fitid="t1").one()
    assert (t1.category, t1.entity_id, t1.reconciled) == (None, None, False)


# ------------------------------------------------------------- arrière-plan

class ImmediateThread:
    def __init__(self, target, args=(), daemon=None):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


@pytest.fixture()
def admin(login_as, ba, monkeypatch):
    external_config.set_many("qonto", {"login": "org", "secret_key": "qonto-secret-xyz"})
    monkeypatch.setattr(sync_jobs.threading, "Thread", ImmediateThread)
    return login_as(is_admin=True)


def test_sync_route_runs_job_and_shows_summary(admin, ba, monkeypatch):
    fake = FakeClient([tx("t1", 1000)])
    monkeypatch.setattr(qonto_client, "from_app_config", lambda **kw: fake)
    resp = admin.post(f"/bank-accounts/{ba.id}/qonto/sync", headers={"HX-Request": "true"})
    assert resp.status_code == 200
    job = SyncJob.query.filter_by(kind="qonto_transactions").one()
    assert (job.status, job.bank_account_id) == ("done", ba.id)
    html = admin.get(f"/bank-accounts/{ba.id}/qonto/sync/{job.id}").get_data(as_text=True)
    assert "1 nouvelle(s)" in html
    page = admin.get(f"/bank-accounts/{ba.id}/transactions").get_data(as_text=True)
    assert "Synchroniser Qonto" in page and "1 nouvelle(s)" in page


def test_sync_route_failure_message_is_masked(admin, ba, monkeypatch):
    def boom(**kw):
        raise QontoError("clé qonto-secret-xyz refusée")
    monkeypatch.setattr(qonto_client, "from_app_config", boom)
    admin.post(f"/bank-accounts/{ba.id}/qonto/sync", headers={"HX-Request": "true"})
    db.session.expire_all()  # le job a été finalisé par le fil d'exécution
    job = SyncJob.query.filter_by(kind="qonto_transactions").one()
    assert job.status == "failed"
    assert job.message == "clé •••• refusée"


def test_sync_route_refused_when_disabled(admin, ba):
    external_config.set_enabled("qonto", False)
    resp = admin.post(f"/bank-accounts/{ba.id}/qonto/sync", headers={"HX-Request": "true"})
    assert "Qonto désactivée" in resp.get_data(as_text=True)
    assert SyncJob.query.count() == 0


def test_status_route_rejects_other_jobs(admin, ba):
    job = SyncJob(kind="payouts", status="done")
    db.session.add(job)
    db.session.commit()
    assert admin.get(f"/bank-accounts/{ba.id}/qonto/sync/{job.id}").status_code == 404


def test_last_sync_shown_in_integration(admin, ba, monkeypatch):
    monkeypatch.setattr(qonto_client, "from_app_config", lambda **kw: FakeClient([]))
    admin.post(f"/bank-accounts/{ba.id}/qonto/sync")
    html = admin.get("/configuration/integrations/qonto").get_data(as_text=True)
    assert "Terminée" in html and "Comptes bancaires →" in html


def test_sync_links_existing_entities_and_counts_proposals(ba):
    from app.models import Entity

    db.session.add(Entity(name="EDF"))
    db.session.commit()
    client = FakeClient([tx("t1", 1000, clean_counterparty_name="EDF"),
                         tx("t2", 2000, clean_counterparty_name="SARL Papin"),
                         tx("t3", 122, operation_type="qonto_fee", clean_counterparty_name="Qonto")])
    result = _sync(ba, client)
    assert result["linked_entities"] == 1
    assert result["proposed_counterparties"] == 1  # SARL Papin ; les frais Qonto ne sont pas proposés
