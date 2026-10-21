"""Saisie d'une facture d'achat : préremplissage, validation, doublons, création, modification."""
import io
from datetime import date

import pytest
from werkzeug.datastructures import FileStorage, MultiDict

from app.extensions import db
from app.models import Account, BankAccount, Entity, FiscalYear, Journal, Purchase
from app.services import attachments, invoice_reader, purchase_entry
from app.services.ledger import LedgerError
from test_invoice_reader import FREE, TICKET


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
