"""Saisie d'une facture d'achat : préremplissage, validation, doublons, création, modification."""
import io
from datetime import date

import pytest
from werkzeug.datastructures import FileStorage, MultiDict

from app.extensions import db
from app.models import Account, BankAccount, Entity, FiscalYear, Journal, Product, Purchase
from app.services import attachments, catalog, invoice_reader, organization, purchase_entry, purchase_posting
from app.services.ledger import LedgerError
from test_invoice_reader import FREE, TICKET, _pdf


@pytest.fixture()
def books(app, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "instance_path", str(tmp_path))
    for code in ("401", "44566", "6068", "6061", "609"):
        db.session.add(Account(code=code, label=f"Compte {code}", account_type="EXPENSE"))
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
                    vat_liable=True)
    db.session.add_all([fy, Journal(code="AC", label="Achats")])
    db.session.commit()
    return fy


def header(**overrides):
    form = {"entity_id": "new", "new_name": "Free", "supplier_name": "Free",
            "supplier_vat": "FR60421938861", "supplier_siret": "", "supplier_iban": "",
            "invoice_number": "1400000013", "issue_date": "2026-09-02", "due_date": "2026-09-04",
            "total": "39,99", "untaxed": "33,33", "tax": "6,66"}
    form.update(overrides)
    return MultiDict(form)


def free_rows():
    return [{"product_id": "", "account_code": "6061", "label": "Abonnement Freebox",
             "untaxed": "33,33", "vat_rate": "20", "vat": "6,66"}]


# ------------------------------------------------------------------ préremplissage

def test_form_from_free_invoice_unknown_supplier(books):
    form = purchase_entry.form_from_extraction(invoice_reader.parse_text(FREE))
    v = form.values
    assert (v["entity_id"], v["new_name"], v["supplier_vat"]) == ("new", "Free", "FR60421938861")
    assert (v["invoice_number"], v["issue_date"], v["due_date"]) == ("1400000013", "2026-09-02", "2026-09-04")
    assert (v["total"], v["untaxed"], v["tax"]) == ("39,99", "33,33", "6,66")
    assert form.checks == set() and form.source == "text"
    # Une ligne au taux lu, avec le produit par défaut (Achats divers, 6068).
    assert [(r["account_code"], r["untaxed"], r["vat_rate"], r["vat"]) for r in form.rows] == [
        ("6068", "33,33", "20", "6,66")]


def test_form_recognises_supplier_by_vat(books):
    free = Entity(name="Free Télécom", vat_number="FR60421938861")
    db.session.add(free)
    db.session.commit()
    form = purchase_entry.form_from_extraction(invoice_reader.parse_text(FREE))
    assert form.values["entity_id"] == str(free.id) and "new_name" not in form.values


def test_form_with_loyalty_discount(books):
    form = purchase_entry.form_from_extraction(invoice_reader.parse_text(TICKET))
    # Total du ticket 171,16, dont 0,76 € de points fidélité (seule remise du ticket de test).
    assert form.values["total"] == "170,40" and form.values["untaxed"] == "141,87"
    assert {"total", "untaxed"} <= form.checks and form.values["entity_id"] == "new"
    assert [(r["account_code"], r["label"], r["untaxed"], r["vat_rate"]) for r in form.rows] == [
        ("6068", "Achats divers", "142,63", "20"), ("609", "Remise fidélité", "-0,76", "0")]
    assert any("Remise" in w for w in form.warnings)


def test_own_iban_ignored(books):
    db.session.add(BankAccount(label="Banque", iban="FR76 3000 6000 0112 3456 7890 189",
                               account_id=Account.query.filter_by(code="401").one().id))
    db.session.commit()
    assert purchase_entry.own_ibans() == {"FR7630006000011234567890189"}


def test_read_staged_uses_supplier_memory_and_own_identity(books, tmp_path):
    clean, _ = purchase_entry.validate_header(header())
    purchase_entry.create(clean, free_rows())
    org = organization.get()
    org.name, org.siren = "SCI des Chênes Verts", "123456782"
    db.session.commit()
    assert purchase_entry.supplier_hints(Purchase.query.one().entity) == invoice_reader.SupplierHints(
        rates=frozenset({2000}), tax_free=False, number_shapes=frozenset({"9999999999"}))
    # Facture suivante sans HT ni TVA lisibles : le taux habituel du fournisseur les déduit.
    text = ("SCI DES CHENES VERTS\nSIRET 123 456 782 00028\nFacture Freebox n°1500000046 du 02/10/2026\n"
            "Somme à payer 39,99 EUR\nFree SAS au capital de 3.441.812 EUR - RCS Paris - "
            "No de TVA intracommunautaire : FR 604 219 388 61")
    pdf = _pdf(tmp_path / "next.pdf", text)
    token = attachments.stage(FileStorage(io.BytesIO(pdf.read_bytes()), filename="next.pdf"))
    ext = purchase_entry.read_staged(token)
    assert (ext.value("total"), ext.value("untaxed"), ext.value("tax")) == (3999, 3333, 666)
    assert ext.fields["untaxed"].check and ext.value("siret") is None
    assert ext.value("invoice_number") == "1500000046"


def test_default_product_saved_for_proposed_line(books):
    form = purchase_entry.form_from_extraction(invoice_reader.parse_text(FREE))
    product = Product.query.filter_by(name="Achats divers").one()  # enregistré, plus seulement en session
    assert form.rows[0]["product_id"] == str(product.id)
    assert catalog.ensure_default_purchase_product() == product and Product.query.count() == 1


def test_chosen_product_becomes_supplier_default(books):
    account = Account.query.filter_by(code="6061").one()
    power = Product(name="Electricité", kind="purchase", purchase_account_id=account.id, vat_rate_bp=2000)
    db.session.add(power)
    db.session.commit()
    generic = catalog.ensure_default_purchase_product()
    # « Achats divers » ne devient pas le produit du fournisseur ; le premier produit précis, si.
    rows = [dict(free_rows()[0], product_id=str(generic.id)), dict(free_rows()[0], product_id=str(power.id))]
    clean, _ = purchase_entry.validate_header(header(new_name="EDF", supplier_name="EDF"))
    p, _ = purchase_entry.create(clean, rows[:1])
    assert p.entity.default_product_id is None
    if p.journal_entry_id:
        purchase_posting.unpost(p)
    purchase_posting.save_lines(p, rows)
    assert p.entity.default_product_id == power.id
    # Déjà renseigné : inchangé par une autre facture.
    other = Product(name="Gaz", kind="purchase", purchase_account_id=account.id)
    db.session.add(other)
    db.session.commit()
    catalog.remember_supplier_product(p.entity, [type("L", (), {"product_id": other.id})()])
    assert p.entity.default_product_id == power.id
    assert catalog.product_for(p.entity) == power


# ------------------------------------------------------------------ validation, doublons

def test_validate_header(books):
    clean, errors = purchase_entry.validate_header(header())
    assert errors == []
    assert (clean["total_cents"], clean["untaxed_cents"], clean["tax_cents"]) == (3999, 3333, 666)
    assert clean["issue_date"] == date(2026, 9, 2) and clean["new_name"] == "Free"

    _, errors = purchase_entry.validate_header(header(
        total="", issue_date="02/09/2026", supplier_siret="123", entity_id="new", new_name=""))
    assert errors == ["Date de facture invalide.", "Le SIRET doit comporter 14 chiffres.",
                      "Le montant TTC est obligatoire.", "Indiquez le nom du fournisseur à créer."]
    _, errors = purchase_entry.validate_header(header(total="-5", entity_id="999"))
    assert errors == ["Le TTC doit être positif (cochez « Avoir » pour un avoir).",
                      "Fournisseur introuvable."]


def test_duplicates(books):
    clean, _ = purchase_entry.validate_header(header())
    p, _ = purchase_entry.create(clean, free_rows())
    find = purchase_entry.duplicates
    assert find(p.entity_id, " 1400000013 ", None, None) == [p]
    assert find(p.entity_id, "1500000046", date(2026, 9, 2), 3999) == []
    assert find(p.entity_id, None, date(2026, 9, 2), 3999) == [p]
    assert find(p.entity_id, "1400000013", None, None, exclude_id=p.id) == []
    assert find(None, "X", None, None) == []


# ------------------------------------------------------------------ création, modification

def test_create_posts_and_stores_attachment(books):
    token = attachments.stage(FileStorage(io.BytesIO(b"%PDF-1.4 x"), filename="free.pdf"))
    clean, _ = purchase_entry.validate_header(header(supplier_siret="451 647 903 01031"))
    p, outcome = purchase_entry.create(clean, free_rows(), token)
    assert outcome["posted"] == 1 and p.journal_entry is not None
    assert (p.source, p.lines_edited, p.qonto_id) == ("manual", True, None)
    assert len(p.idempotency_key) == 36 and p.supplier_name == "Free"
    assert p.entity.name == "Free" and p.entity.siret == "45164790301031"
    assert p.entity.vat_number == "FR60421938861" and p.entity.entity_type == "FOURNISSEUR"
    assert p.attachment_path == f"achats/2026/09/{p.id}-free.pdf"
    assert attachments.path_of(p).read_bytes() == b"%PDF-1.4 x"
    codes = sorted((l.account.code, l.debit_cents, l.credit_cents) for l in p.journal_entry.lines)
    assert codes == [("401001", 0, 3999), ("44566", 666, 0), ("6061", 3333, 0)]


def test_create_without_lines_uses_default_and_existing_homonym(books):
    free = Entity(name="FREE")
    db.session.add(free)
    db.session.commit()
    clean, _ = purchase_entry.validate_header(header())
    p, _ = purchase_entry.create(clean, [])
    assert p.entity == free and free.vat_number == "FR60421938861"
    assert [(l.account.code, l.untaxed_cents, l.vat_cents) for l in p.lines] == [("6068", 3333, 666)]


def test_create_with_bad_line_raises(books):
    clean, _ = purchase_entry.validate_header(header())
    rows = [dict(free_rows()[0], account_code="999")]
    with pytest.raises(LedgerError):
        purchase_entry.create(clean, rows)


def test_update_header_until_posted(books):
    clean, _ = purchase_entry.validate_header(header(entity_id=""))
    p, outcome = purchase_entry.create(clean, free_rows())
    assert outcome["posted"] == 0 and p.entity is None  # fournisseur à rattacher

    clean, _ = purchase_entry.validate_header(header(invoice_number="1400000013-B"))
    outcome = purchase_entry.update(p, clean)
    assert p.invoice_number == "1400000013-B" and outcome["posted"] == 1
    assert purchase_entry.header_values(p)["total"] == "39,99"
    with pytest.raises(LedgerError, match="comptabilisée"):
        purchase_entry.update(p, clean)


def test_update_refuses_qonto_invoice(books):
    p = Purchase(qonto_id="si-1", total_cents=100)
    db.session.add(p)
    db.session.commit()
    clean, _ = purchase_entry.validate_header(header())
    with pytest.raises(LedgerError, match="saisie"):
        purchase_entry.update(p, clean)


# ------------------------------------------------------------------ envoi à Qonto

class FakeQonto:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def create_supplier_invoice(self, content, filename, mime, key):
        self.calls.append((content, filename, mime, key))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _entered(books, token=True):
    t = attachments.stage(FileStorage(io.BytesIO(b"%PDF-1.4 x"), filename="free.pdf")) if token else None
    clean, _ = purchase_entry.validate_header(header())
    p, _ = purchase_entry.create(clean, free_rows(), t)
    return p


def test_send_to_qonto_then_resend_is_noop(books):
    p = _entered(books)
    client = FakeQonto({"id": "si-77", "status": "to_review"})
    assert purchase_entry.send_to_qonto(p, client) is True
    assert (p.qonto_id, p.qonto_status, p.qonto_upload_status, p.qonto_upload_error) == (
        "si-77", "to_review", "sent", None)
    assert client.calls == [(b"%PDF-1.4 x", "free.pdf", "application/pdf", p.idempotency_key)]
    assert not purchase_entry.can_send_to_qonto(p)
    assert purchase_entry.send_to_qonto(p, client) is True and len(client.calls) == 1


def test_failed_upload_kept_and_resent_with_same_key(books):
    from app.services.qonto_client import QontoError
    p = _entered(books)
    client = FakeQonto(QontoError("Qonto a refusé la facture : wrong content type"), {"id": "si-78"})
    assert purchase_entry.send_to_qonto(p, client) is False
    assert p.qonto_upload_status == "failed" and "wrong content type" in p.qonto_upload_error
    assert p.qonto_id is None and p.journal_entry is not None  # la facture reste enregistrée
    assert purchase_entry.send_to_qonto(p, client) is True
    assert client.calls[0][3] == client.calls[1][3] == p.idempotency_key


def test_network_error_does_not_raise(books):
    import requests
    p = _entered(books)
    assert purchase_entry.send_to_qonto(p, FakeQonto(requests.ConnectionError("boom"))) is False
    assert "boom" in p.qonto_upload_error


def test_cannot_send_without_attachment(books):
    p = _entered(books, token=False)
    client = FakeQonto()
    assert not purchase_entry.can_send_to_qonto(p)
    assert purchase_entry.send_to_qonto(p, client) is False and client.calls == []


def test_unpost_keeps_entered_invoice(books):
    from app.services import purchase_posting
    p = _entered(books)
    p.raw_payload = '{"id": "si-77", "total_amount": {"value": "1.00", "currency": "EUR"}}'
    db.session.commit()
    purchase_posting.unpost(p)
    assert p.total_cents == 3999 and p.invoice_number == "1400000013" and len(p.lines) == 1


def test_send_without_file_on_disk_or_key(books):
    p = _entered(books)
    attachments.path_of(p).unlink()
    assert purchase_entry.send_to_qonto(p, FakeQonto()) is False
    assert "Pièce introuvable" in p.qonto_upload_error

    q = _entered(books)
    q.idempotency_key = None
    db.session.commit()
    client = FakeQonto({"id": "si-80"})
    assert purchase_entry.send_to_qonto(q, client) is True
    assert q.idempotency_key and client.calls[0][3] == q.idempotency_key


def test_unexpected_error_does_not_raise(books):
    p = _entered(books)
    assert purchase_entry.send_to_qonto(p, FakeQonto(KeyError("id"))) is False
    assert p.qonto_upload_error.startswith("Envoi impossible")


def test_update_refuses_replacing_sent_attachment(books):
    p = _entered(books)
    p.journal_entry_id = None
    p.qonto_upload_status = "sent"
    db.session.commit()
    token = attachments.stage(FileStorage(io.BytesIO(b"%PDF-1.4 y"), filename="b.pdf"))
    clean, _ = purchase_entry.validate_header(header())
    with pytest.raises(LedgerError, match="ne peut plus être remplacée"):
        purchase_entry.update(p, clean, token)
