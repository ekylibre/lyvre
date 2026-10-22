"""API des factures d'achat : liste, filtres, synchro, fiche, saisie, suppression."""
import io
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, Entity, FiscalYear, Journal, Purchase, SyncCursor, SyncJob
from app.models.sync_job import SYNC_KIND_QONTO_INVOICES
from app.services import external_config, purchase_sync
from test_invoice_reader import FREE, _pdf

API = "/api/v1/purchases"


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


def numbers(client, qs=""):
    return sorted(r["invoice_number"] for r in client.get(f"{API}?{qs}").get_json()["items"])


def messages(resp):
    return " ".join(n["message"] for n in resp.get_json().get("notices", []))


def error(resp):
    return resp.get_json()["error"]["message"]


def test_list_and_filters(app, login_as):
    edf = _purchases()
    client = login_as()
    body = client.get(API).get_json()
    assert sorted(r["invoice_number"] for r in body["items"]) == ["AV-001", "F-001", "F-002"]
    row = next(r for r in body["items"] if r["invoice_number"] == "F-002")
    assert row["supplier"] is None and row["state"]["code"] and row["qonto_status_label"]
    assert body["meta"]["counters"]["without_supplier"] == 1 and body["meta"]["counters"]["hidden"] == 1
    assert body["meta"]["suppliers"] == [{"value": str(edf.id), "label": "EDF"}]

    assert numbers(client, "hidden=1") == ["AV-001", "F-001", "F-002", "F-003"]
    assert numbers(client, "unpaid=1") == ["F-002"]
    assert numbers(client, "no_supplier=1") == ["F-002"]
    assert numbers(client, f"entity_id={edf.id}") == ["AV-001", "F-001"]
    assert numbers(client, "status=to_review") == ["F-002"]
    assert numbers(client, "q=inconnu") == ["F-002"]
    assert numbers(client, "month=2026-07") == ["F-001"]


def test_spa_shell_serves_purchase_urls(app, login_as):
    client = login_as()
    for url in ("/purchases/", "/purchases/new", "/purchases/1", "/purchases/1/edit",
                "/purchases/settlements", "/purchases/suppliers"):
        assert 'id="root"' in client.get(url).get_data(as_text=True), url


def test_sync_refused_when_qonto_not_configured(app, login_as):
    resp = login_as().post(f"{API}/sync")
    assert resp.status_code == 409 and "Qonto" in error(resp)
    assert SyncJob.query.count() == 0


def test_sync_starts_job(app, login_as, monkeypatch):
    external_config.set_many("qonto", {"login": "org", "secret_key": "secret"})

    def fake_start(app_):
        job = SyncJob(kind=SYNC_KIND_QONTO_INVOICES, status="running", message="…")
        db.session.add(job)
        db.session.commit()
        return job

    monkeypatch.setattr(purchase_sync, "start_sync", fake_start)
    client = login_as()
    job = client.post(f"{API}/sync").get_json()["job"]
    assert job["status"] == "running"
    assert client.get(API).get_json()["meta"]["sync"]["job"]["id"] == job["id"]
    assert client.get(f"/api/v1/jobs/{job['id']}").get_json()["job"]["kind"] == SYNC_KIND_QONTO_INVOICES


def test_sync_from_settings(app, login_as):
    resp = login_as().patch(f"{API}/sync-from", json={"sync_from": "2026-03-01"})
    assert resp.status_code == 403 and SyncCursor.query.count() == 0


def test_sync_from_settings_admin(app, login_as):
    client = login_as(is_admin=True)
    assert client.patch(f"{API}/sync-from", json={"sync_from": "2026-03-01"}).status_code == 200
    assert purchase_sync.sync_from_date() == date(2026, 3, 1)
    assert client.get(API).get_json()["meta"]["sync"]["from"] == "2026-03-01"
    assert client.patch(f"{API}/sync-from", json={"sync_from": "pas une date"}).status_code == 422
    assert purchase_sync.sync_from_date() == date(2026, 3, 1)


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


# ------------------------------------------------------------------ fiche et comptabilisation

def _books():
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


LINE = {"account_code": "6061", "label": "Électricité", "untaxed": "100,00", "vat_rate": "20"}


def test_detail_save_lines_posts_and_unpost(app, login_as):
    p = _incomplete_purchase(_books())
    client = login_as()
    body = client.get(f"{API}/{p.id}").get_json()
    assert body["item"]["state"]["code"] == "to_complete" and body["lines"][0]["account_code"] == "6061"
    assert body["fiscal_year"]["label"] == "2026" and body["meta"]["charge_accounts"]
    assert client.get(API).get_json()["meta"]["counters"]["to_complete"] == 1

    resp = client.put(f"{API}/{p.id}/lines", json={"rows": [LINE]})
    assert "comptabilisée" in messages(resp)
    db.session.refresh(p)
    assert p.lines_edited and p.journal_entry_id is not None
    body = client.get(f"{API}/{p.id}").get_json()
    assert body["item"]["state"]["code"] == "posted" and body["item"]["entry"]["reference"].startswith("AC")

    assert client.post(f"{API}/{p.id}/unpost").status_code == 200
    db.session.refresh(p)
    assert p.journal_entry_id is None
    assert client.get(f"{API}/999").status_code == 404


def test_invalid_lines(app, login_as):
    p = _incomplete_purchase(_books())
    resp = login_as().put(f"{API}/{p.id}/lines", json={"rows": [{"untaxed": "abc"}]})
    assert resp.status_code == 422 and "Montant invalide" in error(resp)
    db.session.refresh(p)
    assert not p.lines_edited


def test_post_ready_and_state_filter(app, login_as):
    p = _incomplete_purchase(_books())
    p.lines[0].total_cents = 12000
    db.session.commit()
    client = login_as()
    assert numbers(client, "state=ready") == ["F-009"]
    assert numbers(client, "state=to_complete") == []
    assert client.get(API).get_json()["meta"]["counters"]["ready"] == 1
    assert "1 facture(s) comptabilisée(s)." in messages(client.post(f"{API}/post-ready"))
    assert numbers(client, "state=posted") == ["F-009"]


def test_post_single(app, login_as):
    p = _incomplete_purchase(_books())
    client = login_as()
    assert client.post(f"{API}/{p.id}/post").status_code == 422  # à compléter
    p.lines[0].total_cents = 12000
    db.session.commit()
    assert "Facture comptabilisée." in messages(client.post(f"{API}/{p.id}/post"))


# ------------------------------------------------------------------ saisie

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


def _save(token, **overrides):
    data = {"token": token, "entity_id": "new", "new_name": "Free", "supplier_name": "Free",
            "supplier_vat": "FR60421938861", "invoice_number": "1400000013", "issue_date": "2026-09-02",
            "due_date": "2026-09-04", "total": "39,99", "untaxed": "33,33", "tax": "6,66",
            "rows": [{"account_code": "6061", "label": "Freebox", "untaxed": "33,33", "vat_rate": "20",
                      "vat": "6,66"}]}
    data.update(overrides)
    return data


def _read(client, tmp_path, body=None, name="free.pdf", url=f"{API}/read"):
    if body is None:
        body = _pdf(tmp_path / "src.pdf", FREE).read_bytes()
    return client.post(url, data={"invoice_file": (io.BytesIO(body), name)}, content_type="multipart/form-data")


def test_new_invoice_flow(entry_books, login_as):
    client = login_as()
    body = _read(client, entry_books).get_json()
    form = body["form"]
    assert form["values"]["invoice_number"] == "1400000013" and form["values"]["total"] == "39,99"
    assert form["source"] == "text" and body["preview"]["mime"] == "application/pdf"
    token = body["token"]
    assert client.get(body["preview"]["url"]).data.startswith(b"%PDF")

    resp = client.post(API, json=_save(token))
    assert resp.status_code == 201 and "Facture enregistrée et comptabilisée." in messages(resp)
    p = Purchase.query.one()
    assert resp.get_json()["item"]["url"] == f"/purchases/{p.id}"
    assert p.source == "manual" and p.journal_entry is not None and p.entity.name == "Free"
    item = client.get(f"{API}/{p.id}").get_json()["item"]
    assert item["attachment"]["name"] == "free.pdf" and item["source"] == "manual"
    pdf = client.get(item["attachment"]["url"])
    assert pdf.mimetype == "application/pdf" and pdf.data.startswith(b"%PDF")
    download = client.get(f"/purchases/{p.id}/attachment?download=1")
    assert "attachment" in download.headers["Content-Disposition"]
    assert numbers(client, "source=manual") == ["1400000013"]
    assert numbers(client, "source=qonto") == []


def test_duplicate_needs_confirmation(entry_books, login_as):
    client = login_as()
    client.post(API, json=_save(""))
    resp = client.post(API, json=_save(""))
    assert resp.status_code == 409 and resp.get_json()["error"]["code"] == "duplicate"
    assert resp.get_json()["error"]["duplicates"][0]["label"] == "Facture 1400000013"
    assert Purchase.query.count() == 1
    assert client.post(API, json=_save("", confirm_duplicate=True)).status_code == 201
    assert Purchase.query.count() == 2


def test_new_invoice_errors(entry_books, login_as):
    client = login_as()
    resp = client.post(API, json=_save("", total="", invoice_number="ABC-1"))
    assert resp.status_code == 422 and "Le montant TTC est obligatoire." in resp.get_json()["error"]["fields"]["form"]
    resp = client.post(API, json=_save("", rows=[{"account_code": "999", "untaxed": "33,33"}]))
    assert resp.status_code == 422 and "Compte « 999 » introuvable" in error(resp)
    assert Purchase.query.count() == 0


def test_rejected_upload(entry_books, login_as):
    resp = _read(login_as(), entry_books, body=b"MZ exe", name="virus.pdf")
    assert resp.status_code == 422 and "Type de fichier non accepté" in error(resp)


def test_form_options(entry_books, login_as):
    body = login_as().get(f"{API}/form-options").get_json()
    assert [a["value"] for a in body["charge_accounts"]] == ["6061", "6068"]
    assert body["qonto"]["upload"] is False


def test_edit_header_and_replace_attachment(entry_books, login_as):
    client = login_as()
    client.post(API, json=_save("", entity_id=""))
    p = Purchase.query.one()
    assert p.journal_entry is None
    body = client.get(f"{API}/{p.id}/header").get_json()
    assert body["values"]["invoice_number"] == "1400000013" and body["preview"] is None
    assert body["can_replace_attachment"] is True

    token = _read(client, entry_books, body=b"\x89PNG\r\n\x1a\nxx", name="photo.png", url=f"{API}/stage").get_json()["token"]
    resp = client.patch(f"{API}/{p.id}", json=_save(token, invoice_number="F-9"))
    assert resp.status_code == 200, resp.get_json()
    db.session.refresh(p)
    assert p.invoice_number == "F-9" and p.attachment_mime == "image/png" and p.journal_entry
    # Comptabilisée : plus modifiable.
    assert client.get(f"{API}/{p.id}/header").status_code == 409
    assert client.patch(f"{API}/{p.id}", json=_save("")).status_code == 409


def test_qonto_invoice_not_editable(entry_books, login_as):
    client = login_as()
    _purchases()
    p = Purchase.query.filter_by(qonto_id="si-2").one()
    assert client.get(f"{API}/{p.id}/header").status_code == 409
    assert client.get(f"/purchases/{p.id}/attachment").status_code == 404


def test_send_to_qonto_from_form_and_resend(entry_books, login_as, monkeypatch):
    from app.services import qonto_client
    from app.services.qonto_client import QontoError

    client = login_as()
    assert _read(client, entry_books).status_code == 200
    external_config.set_many("qonto", {"login": "org", "secret_key": "secret"})
    assert client.get(f"{API}/form-options").get_json()["qonto"]["upload"] is True
    token = _read(client, entry_books).get_json()["token"]

    calls = []

    class Fake:
        def create_supplier_invoice(self, content, name, mime, key):
            calls.append(key)
            if len(calls) == 1:
                raise QontoError("Qonto a refusé la facture : wrong content type")
            return {"id": "si-99", "status": "to_review"}

    monkeypatch.setattr(qonto_client, "from_app_config", lambda **kw: Fake())
    resp = client.post(API, json=_save(token, send_to_qonto=True))
    assert "Envoi à Qonto en échec" in messages(resp) and "Renvoyer à Qonto" in messages(resp)
    p = Purchase.query.one()
    assert client.get(f"{API}/{p.id}").get_json()["item"]["qonto_upload_status"] == "failed"
    assert "Facture déposée dans Qonto." in messages(client.post(f"{API}/{p.id}/qonto"))
    db.session.refresh(p)
    assert p.qonto_id == "si-99" and calls == [p.idempotency_key] * 2
    resp = client.post(f"{API}/{p.id}/qonto")
    assert resp.status_code == 409 and "ne peut pas être envoyée" in error(resp) and len(calls) == 2


def test_unchecked_send_to_qonto(entry_books, login_as, monkeypatch):
    from app.services import qonto_client
    external_config.set_many("qonto", {"login": "org", "secret_key": "secret"})
    monkeypatch.setattr(qonto_client, "from_app_config", lambda **kw: pytest.fail("aucun envoi"))
    client = login_as()
    token = _read(client, entry_books).get_json()["token"]
    client.post(API, json=_save(token))
    p = Purchase.query.one()
    assert p.qonto_upload_status is None
    assert client.get(f"{API}/{p.id}").get_json()["can_send"] is True


def test_edit_preview_and_locked_sent_attachment(entry_books, login_as):
    client = login_as()
    token = _read(client, entry_books).get_json()["token"]
    client.post(API, json=_save(token, entity_id=""))
    p = Purchase.query.one()
    body = client.get(f"{API}/{p.id}/header").get_json()
    assert body["preview"]["url"] == f"/purchases/{p.id}/attachment" and body["can_replace_attachment"]
    p.qonto_upload_status = "sent"
    db.session.commit()
    assert client.get(f"{API}/{p.id}/header").get_json()["can_replace_attachment"] is False
    token = _read(client, entry_books, body=b"%PDF-1.4 autre", name="autre.pdf", url=f"{API}/stage").get_json()["token"]
    resp = client.patch(f"{API}/{p.id}", json=_save(token, entity_id=""))
    assert resp.status_code == 422 and "ne peut plus être remplacée" in error(resp)


def test_entry_error_paths(entry_books, login_as):
    client = login_as()
    assert client.get("/purchases/staged/" + "0" * 32).status_code == 404
    assert client.get("/purchases/staged/../../etc").status_code == 404
    resp = client.post(API, json=_save("f" * 32))
    assert resp.status_code == 422 and "déposez à nouveau le fichier" in error(resp)
    assert Purchase.query.count() == 0
    client.post(API, json=_save("", entity_id=""))
    p = Purchase.query.one()
    assert "Date de facture invalide." in error(client.patch(f"{API}/{p.id}", json=_save("", issue_date="2026-13-01")))
    assert "TTC invalide" in error(client.patch(f"{API}/{p.id}", json=_save("", total="abc")))


def test_send_to_qonto_route_guards(entry_books, login_as):
    client = login_as()
    client.post(API, json=_save("", entity_id=""))
    p = Purchase.query.one()
    resp = client.post(f"{API}/{p.id}/qonto")
    assert resp.status_code == 409 and "Intégration Qonto" in error(resp)
    external_config.set_many("qonto", {"login": "org", "secret_key": "secret"})
    assert "ne peut pas être envoyée" in error(client.post(f"{API}/{p.id}/qonto"))  # pas de pièce


# ------------------------------------------------------------------ suppression

def test_delete_entered_invoice_with_entry_and_attachment(entry_books, login_as):
    from app.models import JournalEntry
    from app.services import attachments
    client = login_as()
    token = _read(client, entry_books).get_json()["token"]
    client.post(API, json=_save(token))
    p = Purchase.query.one()
    path = attachments.path_of(p)
    assert path.is_file() and p.journal_entry_id is not None
    resp = client.delete(f"{API}/{p.id}")
    assert "Facture 1400000013 supprimée, ainsi que son écriture AC-" in messages(resp)
    assert Purchase.query.count() == 0 and JournalEntry.query.count() == 0
    assert not path.exists()


def test_delete_refused_when_validated_in_qonto_or_linked(app, login_as):
    from app.models import PurchasePayment
    _purchases()
    client = login_as()
    paid = Purchase.query.filter_by(invoice_number="F-001").one()
    resp = client.delete(f"{API}/{paid.id}")
    assert resp.status_code == 409 and "validée dans Qonto (statut « Payée »)" in error(resp)

    pending = Purchase.query.filter_by(invoice_number="F-002").one()
    pending.payments.append(PurchasePayment(qonto_transaction_id="tx-1"))
    credit = Purchase(qonto_id="si-5", invoice_number="AV-002", supplier_name="Inconnu SARL",
                      issue_date=date(2026, 8, 6), total_cents=500, is_credit_note=True,
                      qonto_status="to_review", related_qonto_ids='["si-2"]')
    db.session.add(credit)
    db.session.commit()
    message = error(client.delete(f"{API}/{pending.id}"))
    assert "liée à un paiement" in message and "liée à une autre facture (avoir)" in message
    assert "liée à une autre facture (avoir)" in error(client.delete(f"{API}/{credit.id}"))
    assert Purchase.query.count() == 5


def test_delete_qonto_invoice_to_review(app, login_as):
    _purchases()
    client = login_as()
    p = Purchase.query.filter_by(invoice_number="F-002").one()
    assert "Facture F-002 supprimée." in messages(client.delete(f"{API}/{p.id}"))
    assert Purchase.query.filter_by(invoice_number="F-002").count() == 0


def test_delete_refused_in_closed_fiscal_year(app, login_as):
    p = _incomplete_purchase(_books())
    p.qonto_status = "to_review"
    client = login_as()
    client.put(f"{API}/{p.id}/lines", json={"rows": [LINE]})
    FiscalYear.query.one().closed = True
    db.session.commit()
    resp = client.delete(f"{API}/{p.id}")
    assert resp.status_code == 409 and "exercice clôturé" in error(resp) and Purchase.query.count() == 1
