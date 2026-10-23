"""Lot B.2 : dons à reprendre (donateur résolu), dons en nature, émission annuelle ou par don,
numérotation continue sans trou, PDF figé avec les mentions des modèles CERFA."""
from datetime import date
from io import BytesIO

import fitz
import pytest

from app.extensions import db
from app.models import (
    Account, BankAccount, BankTransaction, DonationReceipt, Entity, FiscalYear, InKindDonation, Journal, ReceiptCounter,
)
from app.services import organization, receipts, sync_jobs
from app.services.ledger import post_entry

YEAR = 2026
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
       b"\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82")


def _error(resp, status):
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()["error"]


class _InlineThread:
    """Les jobs d'émission s'exécutent au démarrage (tests déterministes)."""

    def __init__(self, target, args=(), daemon=None):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


@pytest.fixture(autouse=True)
def _inline_jobs(monkeypatch):
    monkeypatch.setattr(sync_jobs.threading, "Thread", _InlineThread)


def _issue(client, **body):
    """Lance l'émission (job) ; renvoie (reçus émis par ce job, refus « donateur : motif »)."""
    resp = client.post("/api/v1/receipts/issue", json={"year": YEAR, **body})
    assert resp.status_code == 202, resp.get_json()
    # Le job s'exécute dans son propre contexte (sa propre session) ; la session du test, partagée
    # par les requêtes du client de test, garde l'objet lu au lancement : on la rafraîchit.
    db.session.expire_all()
    job = client.get(f"/api/v1/jobs/{resp.get_json()['job']['id']}").get_json()["job"]
    assert job["status"] == "done", job
    numbers = job["result"]["numbers"]
    listing = client.get(f"/api/v1/receipts?year={body.get('year', YEAR)}").get_json()["items"]
    return [r for r in listing if r["number"] in numbers], job["result"]["errors"]


def _text(pdf: bytes) -> str:
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        return " ".join(page.get_text() for page in doc).replace("\n", " ")


@pytest.fixture()
def books(app, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "instance_path", str(tmp_path))
    fy = FiscalYear(label=str(YEAR), start_date=date(YEAR, 1, 1), end_date=date(YEAR, 12, 31))
    accounts = {c: Account(code=c, label=f"Compte {c}", account_type="OTHER") for c in ("512", "530", "4110001", "7541")}
    alice = Entity(name="Alice Martin", person_kind="individual", address_line1="1 rue A", postal_code="35000", city="Rennes",
                   email="alice@example.org")
    acme = Entity(name="ACME SAS", person_kind="company", address_line1="2 bd B", postal_code="75002", city="Paris",
                  siret="73282932000074", account_code="4110001")
    bob = Entity(name="Bob Sans Adresse", person_kind="individual")
    db.session.add_all([fy, Journal(code="BQ", label="Banque"), *accounts.values(), alice, acme, bob])
    db.session.commit()
    org = organization.get()
    org.name, org.rna, org.purpose = "Les Amis du Jardin", "W123456789", "Jardinage partagé"
    org.address_line1, org.postal_code, org.city = "1 rue des Lilas", "35000", "Rennes"
    org.signatory_name, org.signatory_title = "Camille Martin", "Présidente"
    db.session.commit()
    ids = {c: a.id for c, a in accounts.items()}
    bq = Journal.query.one().id
    ba = BankAccount(label="CIC", account_id=ids["512"])
    db.session.add(ba)
    db.session.commit()

    def gift(day, cents, treasury="512", donor=None, via_tiers=False):
        lines = [{"account_id": ids[treasury], "debit_cents": cents}, {"account_id": ids["7541"], "credit_cents": cents}]
        if via_tiers:  # don passé par le compte du tiers (411)
            lines = [{"account_id": ids["4110001"], "debit_cents": cents}, {"account_id": ids["7541"], "credit_cents": cents}]
        entry = post_entry(fy.id, bq, day, "Don", lines)
        if donor is not None:
            bank_line = next(l for l in entry.lines if l.account_id == ids[treasury])
            db.session.add(BankTransaction(bank_account_id=ba.id, fitid=f"F{entry.id}", transaction_date=day,
                                           amount_cents=cents, label="VIR DON", reconciled=True,
                                           journal_line_id=bank_line.id, entity_id=donor.id))
            db.session.commit()
        return entry

    gift(date(YEAR, 2, 1), 5000, donor=alice)
    gift(date(YEAR, 6, 1), 2500, treasury="530", donor=alice)
    gift(date(YEAR, 3, 1), 100000, via_tiers=True)
    gift(date(YEAR, 4, 1), 1500)                       # sans donateur
    gift(date(YEAR - 1, 12, 31), 999, donor=alice)     # autre année
    db.session.add(InKindDonation(entity_id=bob.id, date=date(YEAR, 5, 5), description="Ordinateur", valuation_cents=30000))
    db.session.commit()
    return {"alice": alice, "acme": acme, "bob": bob}


def _activate(client):
    """Signature et activation par l'API : les fichiers vont dans le dossier de l'instance."""
    assert client.post("/api/v1/receipts/settings/signature", data={"signature": (BytesIO(PNG), "sig.png")},
                       content_type="multipart/form-data").status_code == 200
    assert client.put("/api/v1/receipts/settings", json={
        "enabled": True, "eligibility": "general_interest", "cgi_articles": ["200", "238bis"],
        "donation_prefixes": ["7541"], "acknowledged": True}).status_code == 200
    return client


def test_candidates_by_donor(books, login_as):
    data = _activate(login_as(role="admin")).get(f"/api/v1/receipts/candidates?year={YEAR}").get_json()
    donors = {d["name"]: d for d in data["donors"]}
    assert set(donors) == {"ACME SAS", "Alice Martin", "Bob Sans Adresse"}
    assert donors["Alice Martin"]["total_cents"] == 7500
    assert [i["payment_method"] for i in donors["Alice Martin"]["items"]] == ["transfer", "cash"]
    assert donors["ACME SAS"]["total_cents"] == 100000 and donors["ACME SAS"]["problems"] == []
    assert donors["Bob Sans Adresse"]["problems"] == ["adresse"] and donors["Bob Sans Adresse"]["items"][0]["kind"] == "in_kind"
    assert [u["amount_cents"] for u in data["unassigned"]] == [1500]


def test_issue_annual_numbers_and_pdf(books, login_as, app):
    client = _activate(login_as(role="admin"))
    items, refused = _issue(client)
    assert [(r["number"], r["donor"], r["total_cents"]) for r in items] == [
        ("2026-00001", "ACME SAS", 100000), ("2026-00002", "Alice Martin", 7500)]
    assert len(refused) == 1 and refused[0].startswith("Bob Sans Adresse") and "adresse" in refused[0]
    pdf = client.get(f"/receipts/{items[1]['id']}.pdf")
    assert pdf.status_code == 200 and pdf.mimetype == "application/pdf"
    text = _text(pdf.data)
    for mention in ("11580*05", "2026-00002", "Les Amis du Jardin", "RNA W123456789", "Alice Martin", "1 rue A",
                    "75,00 €", "soixante-quinze euros", "200 du CGI", "Déclaration de don manuel", "Camille Martin"):
        assert mention in text, mention
    company = _text(client.get(f"/receipts/{items[0]['id']}.pdf").data)
    assert "16216*01" in company and "SIREN 732829320" in company and "mille euros" in company
    # Déjà reçus : plus rien à émettre pour eux ; liste des reçus de l'année.
    assert _issue(client, entity_ids=[books["alice"].id]) == ([], [])
    listing = client.get(f"/api/v1/receipts?year={YEAR}").get_json()["items"]
    assert [r["number"] for r in listing] == ["2026-00001", "2026-00002"]


def test_single_mode_and_donor_assignment(books, login_as):
    client = _activate(login_as(role="admin"))
    line_id = client.get(f"/api/v1/receipts/candidates?year={YEAR}").get_json()["unassigned"][0]["id"]
    assert client.put(f"/api/v1/receipts/lines/{line_id}/donor", json={"entity_id": books["alice"].id}).status_code == 200
    items, _ = _issue(client, entity_ids=[books["alice"].id], mode="single")
    assert [(r["number"], r["total_cents"]) for r in items] == [
        ("2026-00001", 5000), ("2026-00002", 1500), ("2026-00003", 2500)]
    _error(client.put(f"/api/v1/receipts/lines/{line_id}/donor", json={"entity_id": None}), 409)


def test_no_gap_when_issue_fails(books, login_as, monkeypatch):
    client = _activate(login_as(role="admin"))
    real = receipts.render_pdf

    def flaky(receipt):
        if receipt.entity.name == "ACME SAS":
            raise RuntimeError("PDF")
        return real(receipt)
    monkeypatch.setattr(receipts, "render_pdf", flaky)
    items, refused = _issue(client)
    assert [r["number"] for r in items] == ["2026-00001"]  # Alice : le numéro d'ACME n'est pas consommé
    assert any(r.startswith("ACME SAS") for r in refused)
    assert ReceiptCounter.query.get(YEAR).last_number == 1 and DonationReceipt.query.count() == 1
    monkeypatch.setattr(receipts, "render_pdf", real)
    assert _issue(client)[0][0]["number"] == "2026-00002"


def test_issue_guards(books, login_as):
    client = _activate(login_as(role="admin"))
    _error(client.post("/api/v1/receipts/issue", json={"year": YEAR + 1}), 422)
    _error(client.post("/api/v1/receipts/issue", json={}), 422)
    settings = receipts.get()
    settings.enabled = False
    db.session.commit()
    assert "activés" in _error(client.post("/api/v1/receipts/issue", json={"year": YEAR}), 409)["message"]


def test_in_kind_and_pdf_tamper(books, login_as, app):
    client = _activate(login_as(role="admin"))
    _error(client.post("/api/v1/receipts/in-kind", json={"entity_id": books["bob"].id, "date": "2026-05-05",
                                                         "description": "", "valuation_cents": 1}), 422)
    assert client.post("/api/v1/receipts/in-kind", json={"entity_id": books["acme"].id, "date": "2026-07-01",
                                                         "description": "Matériel", "valuation_cents": 2000,
                                                         "valuation_method": "Valeur nette comptable"}).status_code == 201
    issued = _issue(client, entity_ids=[books["acme"].id])[0][0]
    assert issued["total_cents"] == 102000
    gift = InKindDonation.query.filter_by(description="Matériel").one()
    _error(client.delete(f"/api/v1/receipts/in-kind/{gift.id}"), 409)
    receipt = db.session.get(DonationReceipt, issued["id"])
    path = receipts.receipt_file(receipt)
    path.write_bytes(b"%PDF-altered")
    assert client.get(f"/receipts/{receipt.id}.pdf").status_code == 409


def test_accountant_cannot_issue(books, login_as):
    client = login_as(role="accountant")
    assert client.get(f"/api/v1/receipts/candidates?year={YEAR}").status_code == 200
    _error(client.post("/api/v1/receipts/issue", json={"year": YEAR}), 403)


# ------------------------------------------------------------------ lot B.3 : envoi, annulation, état annuel


class _FakeSMTP:
    sent = []

    def send_message(self, message):
        _FakeSMTP.sent.append(message)

    def quit(self):
        pass


@pytest.fixture()
def smtp(monkeypatch):
    from app.services import membership_reminders
    _FakeSMTP.sent = []
    monkeypatch.setattr(membership_reminders, "smtp_configured", lambda: True)
    monkeypatch.setattr(membership_reminders, "smtp_settings", lambda: {"sender": "tresorier@asso.test"})
    monkeypatch.setattr(membership_reminders, "_open_smtp", lambda settings: _FakeSMTP())
    return _FakeSMTP


def _job(client, resp):
    assert resp.status_code == 202, resp.get_json()
    db.session.expire_all()
    return client.get(f"/api/v1/jobs/{resp.get_json()['job']['id']}").get_json()["job"]


def test_send_by_email(books, login_as, smtp):
    client = _activate(login_as(role="admin"))
    items, _ = _issue(client)
    job = _job(client, client.post("/api/v1/receipts/send", json={"year": YEAR}))
    assert job["result"]["sent"] == 1 and job["result"]["skipped"] == 0  # ACME, sans email, n'est pas visé
    message = smtp.sent[0]
    assert message["To"] == "alice@example.org" and "2026-00002" in message["Subject"]
    attachment = next(message.iter_attachments())
    assert attachment.get_filename() == "recu-fiscal-2026-00002.pdf" and attachment.get_content().startswith(b"%PDF")
    alice = next(r for r in client.get(f"/api/v1/receipts?year={YEAR}").get_json()["items"] if r["donor"] == "Alice Martin")
    assert alice["sent_to"] == "alice@example.org" and alice["sent_at"]
    # Déjà envoyés : rien à renvoyer pour l'année (sauf demande explicite).
    assert client.post("/api/v1/receipts/send", json={"year": YEAR}).get_json()["notices"][0]["message"] == "Aucun reçu à envoyer."


def test_send_needs_smtp(books, login_as, monkeypatch):
    from app.services import membership_reminders
    monkeypatch.setattr(membership_reminders, "smtp_configured", lambda: False)  # jamais de vrai serveur en test
    client = _activate(login_as(role="admin"))
    _issue(client)
    assert "SMTP" in _error(client.post("/api/v1/receipts/send", json={"year": YEAR}), 409)["message"]


def test_cancel_and_reissue(books, login_as):
    client = _activate(login_as(role="admin"))
    items, _ = _issue(client)
    alice = next(r for r in items if r["donor"] == "Alice Martin")
    url = f"/api/v1/receipts/{alice['id']}/cancel"
    assert "Motif" in _error(client.post(url, json={"reason": "x"}), 422)["message"]
    # Annulation simple : les dons redeviennent à reprendre ; le numéro n'est pas réutilisé.
    cancelled = client.post(url, json={"reason": "Montant erroné"}).get_json()["item"]
    assert cancelled["status"] == "cancelled" and cancelled["cancel_reason"] == "Montant erroné"
    _error(client.post(url, json={"reason": "Encore une fois"}), 409)
    pending = client.get(f"/api/v1/receipts/candidates?year={YEAR}").get_json()
    assert any(d["name"] == "Alice Martin" and d["total_cents"] == 7500 for d in pending["donors"])
    reissued, _ = _issue(client, entity_ids=[books["alice"].id])
    assert reissued[0]["number"] == "2026-00003"
    # Annulation avec réémission immédiate des mêmes dons.
    body = client.post(f"/api/v1/receipts/{reissued[0]['id']}/cancel", json={"reason": "Adresse corrigée", "reissue": True}).get_json()
    assert body["item"]["replaced_by"] == "2026-00004" and "remplacé par le reçu 2026-00004" in body["notices"][0]["message"]
    listing = {r["number"]: r for r in client.get(f"/api/v1/receipts?year={YEAR}").get_json()["items"]}
    assert [n for n, r in listing.items() if r["status"] == "issued"] == ["2026-00001", "2026-00004"]
    assert listing["2026-00004"]["total_cents"] == 7500


def test_annual_summary(books, login_as):
    client = _activate(login_as(role="admin"))
    items, _ = _issue(client)
    client.post(f"/api/v1/receipts/{items[0]['id']}/cancel", json={"reason": "Erreur de donateur"})
    data = client.get(f"/api/v1/receipts/summary?year={YEAR}").get_json()
    assert data["issued"] == {"count": 1, "amount_cents": 7500}
    assert data["cancelled"] == {"count": 1, "amount_cents": 100000}
    assert data["by_kind"]["individual"] == {"count": 1, "amount_cents": 7500}
    # Dons comptabilisés = repris sur un reçu émis + encore à reprendre.
    assert data["booked_donations_cents"] == 5000 + 2500 + 100000 + 1500
    assert data["receipted_donations_cents"] + data["pending_donations_cents"] == data["booked_donations_cents"]
    assert data["numbers"] == ["2026-00001", "2026-00002"]
    xlsx = client.get(data["export_url"])
    assert xlsx.status_code == 200 and "recus-fiscaux-2026.xlsx" in xlsx.headers["Content-Disposition"]


def test_accountant_cannot_cancel_or_send(books, login_as):
    client = login_as(role="accountant")
    assert client.get(f"/api/v1/receipts/summary?year={YEAR}").status_code == 200
    _error(client.post("/api/v1/receipts/1/cancel", json={"reason": "Pas autorisé"}), 403)
    _error(client.post("/api/v1/receipts/send", json={"year": YEAR}), 403)
