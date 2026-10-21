"""Écran des factures d'achat : liste, filtres, synchro, date de début."""
from datetime import date

from app.extensions import db
from app.models import Entity, Purchase, SyncCursor, SyncJob
from app.models.sync_job import SYNC_KIND_QONTO_INVOICES
from app.services import external_config, purchase_sync


def _purchases():
    edf = Entity(name="EDF", entity_type="FOURNISSEUR")
    db.session.add_all([
        edf,
        Purchase(qonto_id="si-1", invoice_number="F-001", supplier_name="EDF", entity=edf,
                 issue_date=date(2026, 7, 25), total_cents=12000, qonto_status="paid"),
        Purchase(qonto_id="si-2", invoice_number="F-002", supplier_name="Inconnu SARL",
                 issue_date=date(2026, 8, 3), total_cents=5000, qonto_status="to_review"),
        Purchase(qonto_id="si-3", invoice_number="F-003", supplier_name="Spam", is_hidden=True,
                 issue_date=date(2026, 8, 4), total_cents=100, qonto_status="discarded"),
        Purchase(qonto_id="si-4", invoice_number="AV-001", supplier_name="EDF", entity=edf,
                 issue_date=date(2026, 8, 5), total_cents=2000, is_credit_note=True,
                 qonto_status="paid"),
    ])
    db.session.commit()
    return edf


def _rows(page):
    return [n for n in ("F-001", "F-002", "F-003", "AV-001") if n in page]


def test_list_and_filters(app, login_as):
    edf = _purchases()
    client = login_as()
    page = client.get("/purchases/").get_data(as_text=True)
    assert _rows(page) == ["F-001", "F-002", "AV-001"]
    assert "à rattacher" in page and "-20,00 €" in page and "Payée" in page
    assert "1 sans fournisseur rattaché" in page and "facture(s) à compléter" in page

    get = lambda qs: _rows(client.get(f"/purchases/?{qs}").get_data(as_text=True))
    assert get("hidden=1") == ["F-001", "F-002", "F-003", "AV-001"]
    assert get("unpaid=1") == ["F-002"]
    assert get("no_supplier=1") == ["F-002"]
    assert get(f"entity_id={edf.id}") == ["F-001", "AV-001"]
    assert get("status=to_review") == ["F-002"]
    assert get("q=inconnu") == ["F-002"]
    assert get("month=2026-07") == ["F-001"]


def test_menu_entry(app, login_as):
    page = login_as().get("/purchases/").get_data(as_text=True)
    assert 'href="/purchases/"' in page and "Factures d&#39;achat" in page


def test_sync_refused_when_qonto_not_configured(app, login_as):
    client = login_as()
    resp = client.post("/purchases/sync", headers={"HX-Request": "true"})
    assert "purchase-sync-status" in resp.get_data(as_text=True)
    assert SyncJob.query.count() == 0


def test_sync_starts_job_and_status_fragment(app, login_as, monkeypatch):
    external_config.set_many("qonto", {"login": "org", "secret_key": "secret"})
    started = []

    def fake_start(app_):
        job = SyncJob(kind=SYNC_KIND_QONTO_INVOICES, status="running", message="…")
        db.session.add(job)
        db.session.commit()
        started.append(job)
        return job

    monkeypatch.setattr(purchase_sync, "start_sync", fake_start)
    client = login_as()
    page = client.post("/purchases/sync", headers={"HX-Request": "true"}).get_data(as_text=True)
    assert started and "Synchronisation en cours" in page

    job = started[0]
    job.status, job.result_json = "done", '{"created": 2, "read": 3, "without_supplier": 1}'
    db.session.commit()
    page = client.get(f"/purchases/sync/{job.id}").get_data(as_text=True)
    assert "2 nouvelle(s)" in page and "1 sans fournisseur" in page
    assert client.get("/purchases/sync/999").status_code == 404


def test_sync_from_settings_admin_only(app, login_as):
    client = login_as()
    client.post("/purchases/sync/settings", data={"sync_from": "2026-03-01"})
    assert SyncCursor.query.count() == 0


def test_sync_from_settings(app, login_as):
    client = login_as(is_admin=True)
    assert "Date de début" in client.get("/purchases/").get_data(as_text=True)
    client.post("/purchases/sync/settings", data={"sync_from": "2026-03-01"})
    assert purchase_sync.sync_from_date() == date(2026, 3, 1)
    client.post("/purchases/sync/settings", data={"sync_from": "pas une date"})
    assert purchase_sync.sync_from_date() == date(2026, 3, 1)


# ------------------------------------------------------------------ fiche et comptabilisation

def _books():
    from app.models import Account, FiscalYear, Journal
    accounts = {c: Account(code=c, label=f"Compte {c}", account_type="EXPENSE")
                for c in ("401", "6061", "6068")}
    db.session.add_all([*accounts.values(), Journal(code="AC", label="Achats"),
                        FiscalYear(label="2026", start_date=date(2026, 1, 1),
                                   end_date=date(2026, 12, 31))])
    db.session.commit()
    return accounts


def _incomplete_purchase(accounts):
    from app.models import PurchaseLine
    edf = Entity(name="EDF", entity_type="FOURNISSEUR")
    p = Purchase(qonto_id="si-9", invoice_number="F-009", supplier_name="EDF", entity=edf,
                 issue_date=date(2026, 9, 1), total_cents=12000, qonto_status="paid")
    p.lines = [PurchaseLine(position=0, account=accounts["6061"], label="Électricité",
                            untaxed_cents=10000, vat_rate_bp=2000, vat_cents=2000,
                            total_cents=11000)]  # total faux : à compléter
    db.session.add(p)
    db.session.commit()
    return p


def form_lines(*rows):
    data = {}
    for key in ("product_id", "account_code", "label", "untaxed", "vat_rate", "vat"):
        data[f"{key}[]"] = [row.get(key, "") for row in rows]
    return data


def test_detail_save_lines_posts_and_unpost(app, login_as):
    accounts = _books()
    p = _incomplete_purchase(accounts)
    client = login_as()
    page = client.get(f"/purchases/{p.id}").get_data(as_text=True)
    assert "À compléter" in page and "Total des lignes" in page and 'name="untaxed[]"' in page
    assert "Comptabiliser les factures prêtes" in client.get("/purchases/").get_data(as_text=True)

    client.post(f"/purchases/{p.id}/lines", data=form_lines(
        {"account_code": "6061", "label": "Électricité", "untaxed": "100,00", "vat_rate": "20"}))
    db.session.refresh(p)
    assert p.lines_edited and p.journal_entry_id is not None
    page = client.get(f"/purchases/{p.id}").get_data(as_text=True)
    assert "Comptabilisée" in page and "Annuler la comptabilisation" in page
    assert 'name="untaxed[]"' not in page  # lignes en lecture seule

    client.post(f"/purchases/{p.id}/unpost")
    db.session.refresh(p)
    assert p.journal_entry_id is None


def test_invalid_lines_flash_error(app, login_as):
    p = _incomplete_purchase(_books())
    client = login_as()
    resp = client.post(f"/purchases/{p.id}/lines", data=form_lines({"untaxed": "abc"}),
                       follow_redirects=True)
    assert "Montant invalide" in resp.get_data(as_text=True)
    db.session.refresh(p)
    assert not p.lines_edited


def test_post_ready_button_and_state_filter(app, login_as):
    accounts = _books()
    p = _incomplete_purchase(accounts)
    p.lines[0].total_cents = 12000
    db.session.commit()
    client = login_as()
    assert "F-009" in client.get("/purchases/?state=ready").get_data(as_text=True)
    assert "F-009" not in client.get("/purchases/?state=to_complete").get_data(as_text=True)
    client.post("/purchases/post-ready")
    db.session.refresh(p)
    assert p.journal_entry_id is not None
    assert "F-009" in client.get("/purchases/?state=posted").get_data(as_text=True)


def test_entity_detail_shows_purchases_and_balance(app, login_as):
    from app.services import purchase_posting
    accounts = _books()
    p = _incomplete_purchase(accounts)
    p.lines[0].total_cents = 12000
    db.session.commit()
    purchase_posting.post_ready([p])
    page = login_as().get(f"/entities/{p.entity.id}").get_data(as_text=True)
    assert "Factures d'achat (1)" in page and "F-009" in page
    assert "401001" in page and "120,00 €" in page and "dû" in page


def test_moving_sync_from_back_resets_cursor(app):
    from datetime import datetime
    purchase_sync.set_sync_from(date(2026, 3, 1))
    row = purchase_sync.cursor()
    row.synced_at = datetime(2026, 10, 1)
    db.session.commit()
    purchase_sync.set_sync_from(date(2026, 4, 1))  # avancer : curseur conservé
    assert purchase_sync.cursor().synced_at is not None
    purchase_sync.set_sync_from(date(2026, 1, 1))  # reculer : relecture complète
    assert purchase_sync.cursor().synced_at is None
