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
from app.services import organization, receipts
from app.services.ledger import post_entry

YEAR = 2026
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
       b"\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82")


def _error(resp, status):
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()["error"]


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
    body = client.post("/api/v1/receipts/issue", json={"year": YEAR}).get_json()
    assert [(r["number"], r["donor"], r["total_cents"]) for r in body["items"]] == [
        ("2026-00001", "ACME SAS", 100000), ("2026-00002", "Alice Martin", 7500)]
    assert body["refused"][0]["name"] == "Bob Sans Adresse" and "adresse" in body["refused"][0]["reason"]
    pdf = client.get(f"/receipts/{body['items'][1]['id']}.pdf")
    assert pdf.status_code == 200 and pdf.mimetype == "application/pdf"
    text = _text(pdf.data)
    for mention in ("11580*05", "2026-00002", "Les Amis du Jardin", "RNA W123456789", "Alice Martin", "1 rue A",
                    "75,00 €", "soixante-quinze euros", "200 du CGI", "Déclaration de don manuel", "Camille Martin"):
        assert mention in text, mention
    company = _text(client.get(f"/receipts/{body['items'][0]['id']}.pdf").data)
    assert "16216*01" in company and "SIREN 732829320" in company and "mille euros" in company
    # Déjà reçus : plus rien à émettre pour eux ; liste des reçus de l'année.
    again = client.post("/api/v1/receipts/issue", json={"year": YEAR, "entity_ids": [books["alice"].id]}).get_json()
    assert again["items"] == []
    listing = client.get(f"/api/v1/receipts?year={YEAR}").get_json()["items"]
    assert [r["number"] for r in listing] == ["2026-00001", "2026-00002"]


def test_single_mode_and_donor_assignment(books, login_as):
    client = _activate(login_as(role="admin"))
    line_id = client.get(f"/api/v1/receipts/candidates?year={YEAR}").get_json()["unassigned"][0]["id"]
    assert client.put(f"/api/v1/receipts/lines/{line_id}/donor", json={"entity_id": books["alice"].id}).status_code == 200
    body = client.post("/api/v1/receipts/issue", json={"year": YEAR, "entity_ids": [books["alice"].id],
                                                       "mode": "single"}).get_json()
    assert [(r["number"], r["total_cents"]) for r in body["items"]] == [
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
    body = client.post("/api/v1/receipts/issue", json={"year": YEAR}).get_json()
    assert [r["number"] for r in body["items"]] == ["2026-00001"]  # Alice : le numéro d'ACME n'est pas consommé
    assert any(r["name"] == "ACME SAS" for r in body["refused"])
    assert ReceiptCounter.query.get(YEAR).last_number == 1 and DonationReceipt.query.count() == 1
    monkeypatch.setattr(receipts, "render_pdf", real)
    assert client.post("/api/v1/receipts/issue", json={"year": YEAR}).get_json()["items"][0]["number"] == "2026-00002"


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
    issued = client.post("/api/v1/receipts/issue", json={"year": YEAR, "entity_ids": [books["acme"].id]}).get_json()["items"][0]
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
