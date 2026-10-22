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


# ------------------------------------------------------------------ saisie (lot 2b)

import io  # noqa: E402

import pytest  # noqa: E402

from app.models import Account, FiscalYear, Journal  # noqa: E402
from test_invoice_reader import FREE, _pdf  # noqa: E402


@pytest.fixture()
def entry_books(app, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "instance_path", str(tmp_path))
    for code in ("401", "44566", "6068", "6061"):
        db.session.add(Account(code=code, label=f"Compte {code}", account_type="EXPENSE"))
    db.session.add_all([FiscalYear(label="2026", start_date=date(2026, 1, 1),
                                   end_date=date(2026, 12, 31), vat_liable=True),
                        Journal(code="AC", label="Achats")])
    db.session.commit()
    return tmp_path


def _save_form(token, **overrides):
    data = {"step": "save", "token": token, "source": "text", "entity_id": "new",
            "new_name": "Free", "supplier_name": "Free", "supplier_vat": "FR60421938861",
            "invoice_number": "1400000013", "issue_date": "2026-09-02", "due_date": "2026-09-04",
            "total": "39,99", "untaxed": "33,33", "tax": "6,66",
            "product_id[]": [""], "account_code[]": ["6061"], "label[]": ["Freebox"],
            "untaxed[]": ["33,33"], "vat_rate[]": ["20"], "vat[]": ["6,66"]}
    data.update(overrides)
    return data


def _read(client, tmp_path, body=None, name="free.pdf"):
    if body is None:
        body = _pdf(tmp_path / "src.pdf", FREE).read_bytes()
    return client.post("/purchases/new", data={"step": "read", "invoice_file": (io.BytesIO(body), name)},
                       content_type="multipart/form-data")


def test_new_invoice_flow(entry_books, login_as):
    client = login_as()
    assert "Lire la facture" in client.get("/purchases/new").get_data(as_text=True)
    assert "+ Nouvelle facture" in client.get("/purchases/").get_data(as_text=True)

    page = _read(client, entry_books).get_data(as_text=True)
    assert 'value="1400000013"' in page and 'value="39,99"' in page
    assert "Valeurs lues dans le texte du PDF" in page and "<iframe" in page
    token = page.split('name="token" value="')[1].split('"')[0]
    assert client.get(f"/purchases/staged/{token}").data.startswith(b"%PDF")

    response = client.post("/purchases/new", data=_save_form(token))
    assert response.status_code == 302
    p = Purchase.query.one()
    assert p.source == "manual" and p.journal_entry is not None and p.entity.name == "Free"
    detail = client.get(f"/purchases/{p.id}").get_data(as_text=True)
    assert "free.pdf" in detail and "Saisie" in detail and "Aperçu de la pièce" in detail
    pdf = client.get(f"/purchases/{p.id}/attachment")
    assert pdf.mimetype == "application/pdf" and pdf.data.startswith(b"%PDF")
    download = client.get(f"/purchases/{p.id}/attachment?download=1")
    assert "attachment" in download.headers["Content-Disposition"]
    assert "saisie" in client.get("/purchases/?source=manual").get_data(as_text=True)
    assert "1400000013" not in client.get("/purchases/?source=qonto").get_data(as_text=True)


def test_duplicate_needs_confirmation(entry_books, login_as):
    client = login_as()
    client.post("/purchases/new", data=_save_form(""))
    page = client.post("/purchases/new", data=_save_form("")).get_data(as_text=True)
    assert "Doublon possible" in page and Purchase.query.count() == 1
    client.post("/purchases/new", data=_save_form("", confirm_duplicate="1"))
    assert Purchase.query.count() == 2


def test_new_invoice_errors_keep_form(entry_books, login_as):
    client = login_as()
    page = client.post("/purchases/new", data=_save_form("", total="", invoice_number="ABC-1"))
    page = page.get_data(as_text=True)
    assert "Le montant TTC est obligatoire." in page and 'value="ABC-1"' in page
    page = client.post("/purchases/new", data=_save_form("", **{"account_code[]": ["999"]}))
    assert "Compte « 999 » introuvable" in page.get_data(as_text=True)
    assert Purchase.query.count() == 0


def test_rejected_upload_and_manual_entry(entry_books, login_as):
    client = login_as()
    page = _read(client, entry_books, body=b"MZ exe", name="virus.pdf").get_data(as_text=True)
    assert "Type de fichier non accepté" in page
    page = client.get("/purchases/new?manual=1").get_data(as_text=True)
    assert 'name="invoice_number"' in page and "<iframe" not in page


def test_edit_header_and_replace_attachment(entry_books, login_as):
    client = login_as()
    client.post("/purchases/new", data=_save_form("", entity_id=""))
    p = Purchase.query.one()
    assert p.journal_entry is None
    page = client.get(f"/purchases/{p.id}/edit").get_data(as_text=True)
    assert 'value="1400000013"' in page and "Joindre la pièce" in page

    data = _save_form("", invoice_number="F-9", step="save")
    data["invoice_file"] = (io.BytesIO(b"\x89PNG\r\n\x1a\nxx"), "photo.png")
    response = client.post(f"/purchases/{p.id}/edit", data=data, content_type="multipart/form-data")
    assert response.status_code == 302
    db.session.refresh(p)
    assert p.invoice_number == "F-9" and p.attachment_mime == "image/png" and p.journal_entry
    # Comptabilisée : plus modifiable ici.
    assert client.get(f"/purchases/{p.id}/edit").status_code == 302


def test_qonto_invoice_not_editable(entry_books, login_as):
    client = login_as()
    _purchases()
    p = Purchase.query.filter_by(qonto_id="si-2").one()
    assert client.get(f"/purchases/{p.id}/edit").status_code == 302
    assert client.get(f"/purchases/{p.id}/attachment").status_code == 404


def test_send_to_qonto_from_form_and_resend(entry_books, login_as, monkeypatch):
    from app.services import purchase_entry, qonto_client
    from app.services.qonto_client import QontoError

    client = login_as()
    page = _read(client, entry_books).get_data(as_text=True)
    assert "Envoyer à Qonto" not in page  # instance sans Qonto
    external_config.set_many("qonto", {"login": "org", "secret_key": "secret"})
    page = _read(client, entry_books).get_data(as_text=True)
    assert 'name="send_to_qonto" value="1"\n               checked' in page
    token = page.split('name="token" value="')[1].split('"')[0]

    calls = []

    class Fake:
        def create_supplier_invoice(self, content, name, mime, key):
            calls.append(key)
            if len(calls) == 1:
                raise QontoError("Qonto a refusé la facture : wrong content type")
            return {"id": "si-99", "status": "to_review"}

    monkeypatch.setattr(qonto_client, "from_app_config", lambda **kw: Fake())
    page = client.post("/purchases/new", data=_save_form(token, send_to_qonto="1"),
                       follow_redirects=True).get_data(as_text=True)
    assert "Envoi à Qonto en échec" in page and "Renvoyer à Qonto" in page
    assert "envoi Qonto en échec" in client.get("/purchases/").get_data(as_text=True)
    p = Purchase.query.one()
    page = client.post(f"/purchases/{p.id}/qonto", follow_redirects=True).get_data(as_text=True)
    assert "Facture déposée dans Qonto." in page and "Déposée dans Qonto" in page
    db.session.refresh(p)
    assert p.qonto_id == "si-99" and calls == [p.idempotency_key] * 2
    page = client.post(f"/purchases/{p.id}/qonto", follow_redirects=True).get_data(as_text=True)
    assert "ne peut pas être envoyée" in page and len(calls) == 2


def test_unchecked_send_to_qonto(entry_books, login_as, monkeypatch):
    from app.services import qonto_client
    external_config.set_many("qonto", {"login": "org", "secret_key": "secret"})
    monkeypatch.setattr(qonto_client, "from_app_config", lambda **kw: pytest.fail("aucun envoi"))
    client = login_as()
    page = _read(client, entry_books).get_data(as_text=True)
    token = page.split('name="token" value="')[1].split('"')[0]
    client.post("/purchases/new", data=_save_form(token))
    p = Purchase.query.one()
    assert p.qonto_upload_status is None
    assert "Envoyer à Qonto" in client.get(f"/purchases/{p.id}").get_data(as_text=True)


def test_edit_shows_preview_and_locks_sent_attachment(entry_books, login_as):
    client = login_as()
    page = _read(client, entry_books).get_data(as_text=True)
    token = page.split('name="token" value="')[1].split('"')[0]
    client.post("/purchases/new", data=_save_form(token, entity_id=""))
    p = Purchase.query.one()
    page = client.get(f"/purchases/{p.id}/edit").get_data(as_text=True)
    assert f"/purchases/{p.id}/attachment" in page and "Remplacer la pièce" in page
    p.qonto_upload_status = "sent"
    db.session.commit()
    assert "Remplacer la pièce" not in client.get(f"/purchases/{p.id}/edit").get_data(as_text=True)
    data = _save_form("", entity_id="")
    data["invoice_file"] = (io.BytesIO(b"%PDF-1.4 autre"), "autre.pdf")
    page = client.post(f"/purchases/{p.id}/edit", data=data, content_type="multipart/form-data")
    assert "ne peut plus être remplacée" in page.get_data(as_text=True)


def test_entry_error_paths(entry_books, login_as):
    client = login_as()
    assert client.get("/purchases/staged/" + "0" * 32).status_code == 404
    assert client.get("/purchases/staged/../../etc").status_code == 404
    page = client.post("/purchases/new", data=_save_form("f" * 32)).get_data(as_text=True)
    assert "déposez à nouveau le fichier" in page and Purchase.query.count() == 0
    client.post("/purchases/new", data=_save_form("", entity_id=""))
    p = Purchase.query.one()
    page = client.post(f"/purchases/{p.id}/edit", data=_save_form("", issue_date="2026-13-01"))
    assert "Date de facture invalide." in page.get_data(as_text=True)
    page = client.post(f"/purchases/{p.id}/edit", data=_save_form("", **{"total": "abc"}))
    assert "TTC invalide" in page.get_data(as_text=True)


def test_send_to_qonto_route_guards(entry_books, login_as):
    client = login_as()
    client.post("/purchases/new", data=_save_form("", entity_id=""))
    p = Purchase.query.one()
    page = client.post(f"/purchases/{p.id}/qonto", follow_redirects=True).get_data(as_text=True)
    assert "Intégration Qonto" in page  # non configurée dans cette instance
    external_config.set_many("qonto", {"login": "org", "secret_key": "secret"})
    page = client.post(f"/purchases/{p.id}/qonto", follow_redirects=True).get_data(as_text=True)
    assert "ne peut pas être envoyée" in page  # pas de pièce


# ------------------------------------------------------------------ suppression

def test_delete_entered_invoice_with_entry_and_attachment(entry_books, login_as):
    from app.models import JournalEntry
    from app.services import attachments
    client = login_as()
    token = _read(client, entry_books).get_data(as_text=True).split('name="token" value="')[1].split('"')[0]
    client.post("/purchases/new", data=_save_form(token))
    p = Purchase.query.one()
    path = attachments.path_of(p)
    assert path.is_file() and p.journal_entry_id is not None
    page = client.get("/purchases/").get_data(as_text=True)
    assert f"/purchases/{p.id}/delete" in page and "Son écriture d&#39;achat sera supprimée aussi." in page

    resp = client.post(f"/purchases/{p.id}/delete", follow_redirects=True)
    assert "Facture 1400000013 supprimée, ainsi que son écriture AC-" in resp.get_data(as_text=True)
    assert Purchase.query.count() == 0 and JournalEntry.query.count() == 0
    assert not path.exists()


def test_delete_refused_when_validated_in_qonto_or_linked(app, login_as):
    from app.models import PurchasePayment
    _purchases()
    client = login_as()
    paid = Purchase.query.filter_by(invoice_number="F-001").one()
    resp = client.post(f"/purchases/{paid.id}/delete", follow_redirects=True)
    assert "validée dans Qonto (statut « Payée »)" in resp.get_data(as_text=True)

    pending = Purchase.query.filter_by(invoice_number="F-002").one()
    pending.payments.append(PurchasePayment(qonto_transaction_id="tx-1"))
    credit = Purchase(qonto_id="si-5", invoice_number="AV-002", supplier_name="Inconnu SARL",
                      issue_date=date(2026, 8, 6), total_cents=500, is_credit_note=True,
                      qonto_status="to_review", related_qonto_ids='["si-2"]')
    db.session.add(credit)
    db.session.commit()
    page = client.post(f"/purchases/{pending.id}/delete", follow_redirects=True).get_data(as_text=True)
    assert "liée à un paiement" in page and "liée à une autre facture (avoir)" in page
    page = client.post(f"/purchases/{credit.id}/delete", follow_redirects=True).get_data(as_text=True)
    assert "liée à une autre facture (avoir)" in page
    assert Purchase.query.count() == 5


def test_delete_qonto_invoice_to_review(app, login_as):
    _purchases()
    client = login_as()
    p = Purchase.query.filter_by(invoice_number="F-002").one()
    assert "Elle reste dans Qonto." in client.get("/purchases/").get_data(as_text=True)
    page = client.post(f"/purchases/{p.id}/delete", follow_redirects=True).get_data(as_text=True)
    assert "Facture F-002 supprimée." in page
    assert Purchase.query.filter_by(invoice_number="F-002").count() == 0


def test_delete_refused_in_closed_fiscal_year(app, login_as):
    from app.models import FiscalYear
    accounts = _books()
    p = _incomplete_purchase(accounts)
    p.qonto_status = "to_review"
    client = login_as()
    client.post(f"/purchases/{p.id}/lines", data=form_lines(
        {"account_code": "6061", "label": "Électricité", "untaxed": "100,00", "vat_rate": "20"}))
    FiscalYear.query.one().closed = True
    db.session.commit()
    page = client.post(f"/purchases/{p.id}/delete", follow_redirects=True).get_data(as_text=True)
    assert "exercice clôturé" in page and Purchase.query.count() == 1
