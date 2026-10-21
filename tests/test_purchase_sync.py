"""Synchronisation des factures d'achat Qonto (client simulé, aucun appel réseau)."""
from datetime import date, datetime

import pytest

from app.extensions import db
from app.models import Account, Entity, Product, Purchase, SyncCursor, SyncJob
from app.models.sync_job import SYNC_KIND_QONTO_INVOICES
from app.services import external_config, purchase_sync, qonto_client, sync_jobs
from app.services.qonto_client import QontoError
from app.services.qonto_sync import _parse_utc

SYNC_FROM = date(2026, 7, 1)


def now_iso():
    """Modification « maintenant » : dans la fenêtre incrémentale de la synchro suivante."""
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def money(value):
    return {"value": value, "currency": "EUR"} if value is not None else None


def inv(id_, total="3480.00", untaxed="3163.64", tax="316.36", taxes=(("10", "316.36"),),
        supplier="SARL PAPIN", created_at="2026-09-02T12:18:38Z",
        updated_at="2026-09-02T12:24:23Z", **extra):
    """Facture au format réel de Qonto (relevé sur le compte SCI)."""
    return {
        "id": id_, "status": extra.pop("status", "paid"),
        "invoice_number": extra.pop("invoice_number", f"FAC-{id_}"),
        "supplier_id": extra.pop("supplier_id", f"sup-{supplier}"),
        "supplier_name": supplier, "issuer_name": supplier,
        "supplier_snapshot": extra.pop("supplier_snapshot", {
            "id": f"sup-{supplier}", "name": supplier, "iban": "FR76 3000 4000 0312 3456 7890 143",
            "vat_number": "FR 12345678901", "tin": None, "currency": "EUR", "status": "active"}),
        "issue_date": extra.pop("issue_date", "2026-07-25"), "due_date": "2026-08-25",
        "payment_date": extra.pop("payment_date", "2026-09-02"),
        "total_amount": money(total), "total_amount_excluding_taxes": money(untaxed),
        "total_tax_amount": money(tax),
        "taxes": [{"tax_rate": r, "tax_amount": money(a)} for r, a in taxes],
        "payable_amount": money(total), "is_credit_note": extra.pop("is_credit_note", False),
        "is_einvoice": False, "source": "supplier_invoices", "attachment_id": "att-1",
        "attachment_category": extra.pop("attachment_category", "INVOICE"),
        "is_attachment_non_financial": False, "related_invoices": None,
        "matched_transactions": [], "currency": None,
        "created_at": created_at, "updated_at": updated_at, **extra,
    }


class FakeClient:
    """Renvoie les factures filtrées comme l'API (fenêtre created_at ou updated_at)."""

    def __init__(self, invoices=(), per_page=None, fail_on_call=None):
        self.invoices = list(invoices)
        self.calls = []
        self.per_page = per_page
        self.fail_on_call = fail_on_call

    def list_supplier_invoices(self, *, page=1, per_page=100, **window):
        self.calls.append({"page": page, **window})
        if self.fail_on_call and len(self.calls) >= self.fail_on_call:
            raise QontoError("Qonto rencontre une erreur (HTTP 503).")
        size = self.per_page or per_page
        key = "created" if "created_from" in window else "updated"
        start, end = window[f"{key}_from"], window[f"{key}_to"]
        rows = [i for i in self.invoices if start <= _parse_utc(i[f"{key}_at"]) < end]
        chunk = rows[(page - 1) * size: page * size]
        return chunk, {"total_count": len(rows),
                       "next_page": page + 1 if page * size < len(rows) else None}


@pytest.fixture()
def chart(app):
    for code in ("6068", "613213", "6061"):
        db.session.add(Account(code=code, label=f"Compte {code}", account_type="EXPENSE"))
    db.session.add(SyncCursor(key="qonto_supplier_invoices", sync_from=SYNC_FROM))
    db.session.commit()


def _sync(client):
    return purchase_sync.sync_supplier_invoices(client=client)


# ------------------------------------------------------------------ correspondance

def test_mapping_of_real_invoice(chart):
    result = _sync(FakeClient([inv("si-1")]))
    assert result["created"] == 1 and result["read"] == 1
    p = Purchase.query.one()
    assert (p.qonto_id, p.source, p.invoice_number, p.supplier_name) == \
        ("si-1", "qonto", "FAC-si-1", "SARL PAPIN")
    assert (p.total_cents, p.untaxed_cents, p.tax_cents, p.payable_cents) == \
        (348000, 316364, 31636, 348000)
    assert p.issue_date == date(2026, 7, 25) and p.payment_date == date(2026, 9, 2)
    assert p.currency == "EUR" and p.qonto_status == "paid" and not p.is_hidden
    assert p.supplier_vat == "FR12345678901" and p.supplier_iban == "FR7630004000031234567890143"
    assert p.source_updated_at == datetime(2026, 9, 2, 12, 24, 23) and p.raw_payload


def test_single_rate_line_keeps_qonto_untaxed_amount(chart):
    """316,36 ÷ 10 % = 3 163,60 : le HT de Qonto (3 163,64) est conservé."""
    _sync(FakeClient([inv("si-1")]))
    (line,) = Purchase.query.one().lines
    assert (line.untaxed_cents, line.vat_rate_bp, line.vat_cents, line.total_cents) == \
        (316364, 1000, 31636, 348000)
    assert line.product.name == "Achats divers" and line.account.code == "6068"


def test_lines_per_rate_sum_to_total(chart):
    invoice = inv("si-1", total="134.25", untaxed="117.25", tax="17.00",
                  taxes=(("5.5", "2.75"), ("20", "14.25")))
    _sync(FakeClient([invoice]))
    lines = Purchase.query.one().lines
    assert [(l.vat_rate_bp, l.untaxed_cents, l.vat_cents) for l in lines] == \
        [(550, 5000, 275), (2000, 6725, 1425)]
    assert sum(l.total_cents for l in lines) == 13425


def test_zero_rate_goes_last_and_absorbs(chart):
    invoice = inv("si-1", total="150.00", untaxed="130.00", tax="20.00",
                  taxes=(("0", "0"), ("20", "20.00")))
    _sync(FakeClient([invoice]))
    lines = Purchase.query.one().lines
    assert [(l.vat_rate_bp, l.untaxed_cents, l.vat_cents) for l in lines] == \
        [(2000, 10000, 2000), (0, 3000, 0)]


def test_unanalysed_invoice_gets_ttc_line_to_confirm(chart):
    _sync(FakeClient([inv("si-1", total="99.90", untaxed=None, tax=None, taxes=())]))
    (line,) = Purchase.query.one().lines
    assert (line.untaxed_cents, line.vat_rate_bp, line.vat_cents, line.total_cents) == \
        (9990, None, 0, 9990)


def test_rate_taken_from_product_when_consistent(chart):
    product = Product(name="Électricité", kind="purchase", vat_rate_bp=2000,
                      purchase_account=Account.query.filter_by(code="6061").one())
    db.session.add(Entity(name="EDF", entity_type="FOURNISSEUR", default_product=product))
    db.session.commit()
    _sync(FakeClient([inv("si-1", supplier="EDF", total="120.00", untaxed="100.00", tax="20.00",
                          taxes=())]))
    (line,) = Purchase.query.one().lines
    assert line.product.name == "Électricité" and line.account.code == "6061"
    assert line.vat_rate_bp == 2000


def test_credit_note_amounts_are_positive(chart):
    _sync(FakeClient([inv("si-1", total="-50.00", untaxed="-41.67", tax="-8.33",
                          taxes=(("20", "-8.33"),), is_credit_note=True)]))
    p = Purchase.query.one()
    assert p.is_credit_note and p.total_cents == 5000 and p.lines[0].untaxed_cents == 4167


def test_hidden_documents(chart):
    result = _sync(FakeClient([
        inv("si-1", status="rejected"), inv("si-2", status="discarded"),
        inv("si-3", attachment_category="OTHER_NON_FINANCIAL_DOCUMENT"), inv("si-4"),
    ]))
    assert result["hidden"] == 3
    assert [p.qonto_id for p in Purchase.query.filter_by(is_hidden=False)] == ["si-4"]


# ------------------------------------------------------------------ fournisseurs

def test_supplier_matched_by_qonto_id_then_vat_then_name(chart):
    by_id = Entity(name="Papin (ancien nom)", entity_type="FOURNISSEUR", qonto_supplier_id="sup-A")
    by_vat = Entity(name="Dupré", entity_type="FOURNISSEUR", vat_number="FR99")
    by_name = Entity(name="  edf ", entity_type="FOURNISSEUR")
    db.session.add_all([by_id, by_vat, by_name])
    db.session.commit()
    snapshot = lambda id_, name, vat: {"id": id_, "name": name, "vat_number": vat,
                                       "iban": f"FR76 {id_[-1]}"}
    _sync(FakeClient([
        inv("si-1", supplier="SARL PAPIN", supplier_snapshot=snapshot("sup-A", "SARL PAPIN", None)),
        inv("si-2", supplier="DUPRE MAINTENANCE", supplier_snapshot=snapshot("sup-B", "DUPRE MAINTENANCE", "fr 99")),
        inv("si-3", supplier="EDF", supplier_snapshot=snapshot("sup-C", "EDF", None)),
        inv("si-4", supplier="Inconnu", supplier_snapshot=snapshot("sup-D", "Inconnu", None)),
    ]))
    linked = {p.qonto_id: p.entity for p in Purchase.query.all()}
    assert linked == {"si-1": by_id, "si-2": by_vat, "si-3": by_name, "si-4": None}
    # L'entité trouvée reçoit les identifiants qui lui manquaient, sans écraser les siens.
    assert by_vat.qonto_supplier_id == "sup-B" and by_vat.vat_number == "FR99"
    assert by_name.iban == "FR76C" and by_id.vat_number is None


def test_find_supplier_order(chart):
    by_vat = Entity(name="A", vat_number="FR11")
    by_siret = Entity(name="B", siret="12345678900011")
    by_iban = Entity(name="C", iban="FR7612")
    by_name = Entity(name="Dupré Maintenance")
    db.session.add_all([by_vat, by_siret, by_iban, by_name])
    db.session.commit()
    find = purchase_sync.find_supplier
    assert find(vat="fr 11", siret="12345678900011") == by_vat
    assert find(vat="FR00", siret="123 456 789 00011", iban="FR7612") == by_siret
    assert find(siret="99999999999999", iban="fr76 12", name="Dupré Maintenance") == by_iban
    assert find(iban="FR0000", name="  dupré   maintenance ") == by_name
    assert find(name="Inconnu") is None and find() is None


def test_siret_normalized():
    assert purchase_sync.normalize_siret("123 456 789 00011") == "12345678900011"
    assert purchase_sync.normalize_siret("123.456.789.00011") == "12345678900011"
    assert purchase_sync.normalize_siret("123456789") is None
    assert purchase_sync.normalize_siret("1234567890001A") is None
    assert purchase_sync.normalize_siret("") is None


def test_matched_supplier_receives_siret(chart):
    entity = Entity(name="EDF")
    db.session.add(entity)
    p = Purchase(source="manual", supplier_name="EDF", supplier_siret="55208131766522",
                 total_cents=100)
    db.session.add(p)
    db.session.flush()
    assert purchase_sync.match_entity(p) == entity and entity.siret == "55208131766522"


def test_without_supplier_counted(chart):
    result = _sync(FakeClient([inv("si-1"), inv("si-2", status="rejected")]))
    assert result["without_supplier"] == 1


# ------------------------------------------------------------------ idempotence, mises à jour

def test_resync_creates_nothing(chart):
    client = FakeClient([inv("si-1"), inv("si-2", supplier="DUPRE")])
    _sync(client)
    assert SyncCursor.query.one().synced_at is not None
    result = _sync(client)
    assert result["created"] == 0 and Purchase.query.count() == 2


def test_update_regenerates_lines_unless_edited(chart):
    client = FakeClient([inv("si-1", status="to_review", total="100.00", untaxed=None, tax=None,
                             taxes=())])
    _sync(client)
    p = Purchase.query.one()
    assert p.lines[0].vat_rate_bp is None
    # Qonto termine son analyse : HT et TVA arrivent, les lignes sont refaites.
    client.invoices = [inv("si-1", status="paid", total="100.00", untaxed="83.33", tax="16.67",
                           taxes=(("20", "16.67"),), updated_at=now_iso())]
    result = _sync(client)
    assert result["updated"] == 1
    db.session.refresh(p)
    assert p.qonto_status == "paid" and p.lines[0].vat_rate_bp == 2000

    p.lines_edited = True
    p.lines[0].label = "Saisie du trésorier"
    db.session.commit()
    client.invoices[0]["updated_at"] = now_iso()
    _sync(client)
    db.session.refresh(p)
    assert p.lines[0].label == "Saisie du trésorier"


def test_posted_invoice_change_is_flagged_not_applied(chart):
    from app.models import FiscalYear, Journal, JournalEntry
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    journal = Journal(code="AC", label="Achats")
    db.session.add_all([fy, journal])
    db.session.flush()
    entry = JournalEntry(fiscal_year_id=fy.id, journal_id=journal.id, entry_date=date(2026, 7, 25),
                         description="Facture")
    db.session.add(entry)
    db.session.commit()
    client = FakeClient([inv("si-1")])
    _sync(client)
    p = Purchase.query.one()
    p.journal_entry_id = entry.id
    db.session.commit()

    client.invoices = [inv("si-1", total="3500.00", status="discarded",
                           updated_at=now_iso())]
    result = _sync(client)
    db.session.refresh(p)
    assert result["to_review"] == 1
    assert p.total_cents == 348000  # montant comptabilisé conservé
    assert "montant TTC" in p.review_reason and "Écartée" in p.review_reason
    assert p.qonto_status == "discarded" and p.is_hidden


# ------------------------------------------------------------------ fenêtres, reprise

def test_first_sync_monthly_windows_on_created_at(chart):
    client = FakeClient([inv("si-old", created_at="2026-06-30T10:00:00Z"),
                         inv("si-1", created_at="2026-07-02T10:00:00Z")])
    _sync(client)
    assert {c.get("created_from") is not None for c in client.calls} == {True}
    assert client.calls[0]["created_from"] == datetime(2026, 6, 30, 22, 0)  # 1er juillet, Paris
    assert [p.qonto_id for p in Purchase.query.all()] == ["si-1"]


def test_incremental_sync_uses_updated_at(chart):
    client = FakeClient([inv("si-1")])
    _sync(client)
    client.calls.clear()
    _sync(client)
    assert all("updated_from" in c for c in client.calls)


def test_pagination(chart):
    client = FakeClient([inv(f"si-{n}", created_at=f"2026-07-0{n}T10:00:00Z") for n in range(1, 6)],
                        per_page=2)
    assert _sync(client)["created"] == 5


def test_failure_keeps_cursor(chart):
    client = FakeClient([inv("si-1")], fail_on_call=2)
    with pytest.raises(QontoError):
        _sync(client)
    assert SyncCursor.query.one().synced_at is None


# ------------------------------------------------------------------ fil d'exécution

def test_start_sync_records_job(chart, monkeypatch, app):
    external_config.set_many("qonto", {"login": "org", "secret_key": "secret"})
    monkeypatch.setattr(qonto_client, "from_app_config", lambda **kw: FakeClient([inv("si-1")]))
    monkeypatch.setattr(sync_jobs.threading, "Thread", _InlineThread)
    job = purchase_sync.start_sync(app)
    db.session.refresh(job)
    assert job.kind == SYNC_KIND_QONTO_INVOICES and job.status == "done"
    assert purchase_sync.latest_job().id == job.id
    assert Purchase.query.count() == 1


class _InlineThread:
    def __init__(self, target, args, daemon):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)
