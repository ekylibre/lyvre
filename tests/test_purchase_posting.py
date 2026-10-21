"""Comptabilisation des factures d'achat en engagement (journal AC)."""
from datetime import date

import pytest

from app.extensions import db
from app.models import (
    Account, Entity, FiscalYear, Journal, JournalEntry, Product, Purchase, PurchaseLine,
)
from app.services import purchase_posting
from app.services.ledger import LedgerError


@pytest.fixture()
def books(app):
    accounts = {code: Account(code=code, label=f"Compte {code}", account_type="EXPENSE")
                for code in ("401", "44566", "6061", "6068", "60")}
    accounts["60"].is_header = True
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    db.session.add_all([*accounts.values(), fy, Journal(code="AC", label="Achats")])
    db.session.commit()
    return {"fy": fy, **accounts}


_DEFAULT = object()


def _purchase(books, entity=_DEFAULT, lines=None, total=12000, **kwargs):
    """Facture prête ; un fournisseur distinct est créé sauf si `entity` est donné (None : aucun)."""
    if entity is _DEFAULT:
        count = Entity.query.filter(Entity.name.like("EDF%")).count()
        entity = Entity(name="EDF" if count == 0 else f"EDF {count + 1}", entity_type="FOURNISSEUR")
    fields = {"qonto_id": f"si-{Purchase.query.count() + 1}", "invoice_number": "F-42",
              "issue_date": date(2026, 7, 25), "total_cents": total, "entity": entity}
    fields.update(kwargs)
    purchase = Purchase(**fields)
    purchase.lines = lines if lines is not None else [
        PurchaseLine(position=0, account=books["6061"], label="Électricité",
                     untaxed_cents=10000, vat_rate_bp=2000, vat_cents=2000, total_cents=12000)]
    db.session.add(purchase)
    db.session.commit()
    return purchase


def _entry_lines(purchase):
    return sorted((l.account.code, l.debit_cents, l.credit_cents) for l in purchase.journal_entry.lines)


# ------------------------------------------------------------------ état

def test_ready_and_reasons(books):
    p = _purchase(books)
    assert purchase_posting.purchase_state(p).code == "ready"

    p.entity = None
    p.lines[0].account = None
    p.lines[0].total_cents = 11000
    p.issue_date = date(2027, 2, 1)
    p.currency = "USD"
    state = purchase_posting.purchase_state(p)
    assert state.code == "to_complete" and state.label == "À compléter"
    text = " ".join(state.reasons)
    for expected in ("Devise USD", "Fournisseur à rattacher", "Aucun exercice", "sans compte",
                     "Total des lignes (110,00 €) ≠ TTC (120,00 €)"):
        assert expected in text


def test_hidden_and_posted_states(books):
    p = _purchase(books, is_hidden=True)
    assert purchase_posting.purchase_state(p).code == "hidden"
    p.is_hidden = False
    purchase_posting.post(p)
    assert purchase_posting.purchase_state(p).code == "posted"


def test_vat_rate_to_confirm_only_when_vat_liable(books):
    line = PurchaseLine(position=0, account=books["6061"], untaxed_cents=12000, vat_rate_bp=None,
                        vat_cents=0, total_cents=12000)
    p = _purchase(books, lines=[line])
    assert purchase_posting.purchase_state(p).code == "ready"
    books["fy"].vat_liable = True
    assert purchase_posting.purchase_state(p).reasons == ["Taux de TVA à confirmer."]


def test_closed_year_and_bad_supplier_account(books):
    books["fy"].closed = True
    client = Entity(name="Free", entity_type="CLIENT", account_code="411001")
    reasons = purchase_posting.purchase_state(_purchase(books, entity=client)).reasons
    assert any("clôturé" in r for r in reasons)
    assert any("411001" in r and "fournisseur" in r for r in reasons)


# ------------------------------------------------------------------ écriture

def test_post_not_vat_liable_charges_ttc(books):
    p = _purchase(books)
    purchase_posting.post(p)
    db.session.commit()
    entry = p.journal_entry
    assert entry.journal.code == "AC" and entry.entry_date == date(2026, 7, 25)
    assert entry.source == "PURCHASE" and entry.source_ref == f"PURCHASE:{p.id}"
    assert entry.reference.startswith("AC-2026-")
    assert _entry_lines(p) == [("401001", 0, 12000), ("6061", 12000, 0)]


def test_post_vat_liable_splits_vat(books):
    books["fy"].vat_liable = True
    lines = [
        PurchaseLine(position=0, account=books["6061"], untaxed_cents=10000, vat_rate_bp=2000,
                     vat_cents=2000, total_cents=12000),
        PurchaseLine(position=1, account=books["6068"], untaxed_cents=1000, vat_rate_bp=550,
                     vat_cents=55, total_cents=1055),
    ]
    p = _purchase(books, lines=lines, total=13055)
    purchase_posting.post(p)
    assert _entry_lines(p) == [("401001", 0, 13055), ("44566", 2055, 0),
                               ("6061", 10000, 0), ("6068", 1000, 0)]


def test_vat_account_falls_back_to_4456(books):
    books["fy"].vat_liable = True
    db.session.delete(books["44566"])
    db.session.add(Account(code="4456", label="TVA déductible", account_type="TIERS"))
    db.session.commit()
    p = _purchase(books)
    purchase_posting.post(p)
    assert ("4456", 2000, 0) in _entry_lines(p)


def test_credit_note_reversed(books):
    p = _purchase(books, is_credit_note=True)
    purchase_posting.post(p)
    assert _entry_lines(p) == [("401001", 12000, 0), ("6061", 0, 12000)]
    assert p.journal_entry.description.startswith("Avoir F-42")


def test_supplier_account_from_entity_code_or_next_free(books):
    maif = Entity(name="MAIF", entity_type="FOURNISSEUR", account_code="401007")
    other = Entity(name="ECOLOGIC", entity_type="CLIENT", account_code="401020")
    db.session.add_all([maif, other])
    db.session.commit()
    p1 = _purchase(books, entity=maif)
    purchase_posting.post(p1)
    account = Account.query.filter_by(code="401007").one()
    assert account.label == "MAIF" and account.account_type == "TIERS"
    assert account.parent.code == "401"

    p2 = _purchase(books)  # EDF sans code : suivant libre après 401020
    purchase_posting.post(p2)
    assert p2.entity.account_code == "401021"
    assert Account.query.filter_by(code="401021").count() == 1


def test_post_refuses_incomplete(books):
    p = _purchase(books, entity=None)
    with pytest.raises(LedgerError, match="Fournisseur à rattacher"):
        purchase_posting.post(p)


def test_post_ready_isolates_failures(books, monkeypatch):
    ok = _purchase(books)
    incomplete = _purchase(books, entity=None)
    failing = _purchase(books)
    real_post = purchase_posting.post

    def post(p):
        if p is failing:
            raise LedgerError("boom")
        return real_post(p)

    monkeypatch.setattr(purchase_posting, "post", post)
    result = purchase_posting.post_ready([ok, incomplete, failing])
    assert result["posted"] == 1 and result["errors"] == ["Facture F-42 : boom"]
    assert ok.journal_entry_id and not incomplete.journal_entry_id and not failing.journal_entry_id


def test_unpost_reapplies_qonto_payload(books):
    import json
    p = _purchase(books, raw_payload=json.dumps({
        "id": "si-1", "status": "paid", "invoice_number": "F-42", "supplier_name": "EDF",
        "issue_date": "2026-07-25", "total_amount": {"value": "130.00", "currency": "EUR"},
        "total_amount_excluding_taxes": {"value": "108.33"}, "total_tax_amount": {"value": "21.67"},
        "taxes": [{"tax_rate": "20", "tax_amount": {"value": "21.67"}}],
        "updated_at": "2026-10-21T08:00:00Z"}))
    purchase_posting.post(p)
    p.review_reason = "Modifiée dans Qonto après comptabilisation : montant TTC."
    db.session.commit()
    entry_id = p.journal_entry_id

    purchase_posting.unpost(p)
    assert db.session.get(JournalEntry, entry_id) is None
    assert p.journal_entry_id is None and p.review_reason is None
    assert p.total_cents == 13000 and sum(l.total_cents for l in p.lines) == 13000


def test_unpost_requires_posted(books):
    with pytest.raises(LedgerError):
        purchase_posting.unpost(_purchase(books))


# ------------------------------------------------------------------ lignes saisies

def test_save_lines_computes_vat_and_posts(books):
    product = Product(name="Électricité", kind="purchase", purchase_account=books["6061"],
                      vat_rate_bp=2000)
    db.session.add(product)
    p = _purchase(books, lines=[], total=12500)
    result = purchase_posting.save_lines(p, [
        {"product_id": str(product.id), "account_code": "", "label": "", "untaxed": "100",
         "vat_rate": "20", "vat": ""},
        {"product_id": "", "account_code": "6068", "label": "Frais de port", "untaxed": "5,00",
         "vat_rate": "0", "vat": ""},
        {"product_id": "", "account_code": "", "label": "", "untaxed": "", "vat_rate": "", "vat": ""},
    ])
    assert p.lines_edited and result["posted"] == 1
    assert [(l.account.code, l.label, l.untaxed_cents, l.vat_cents, l.total_cents) for l in p.lines] == \
        [("6061", "Électricité", 10000, 2000, 12000), ("6068", "Frais de port", 500, 0, 500)]


@pytest.mark.parametrize("row, message", [
    ({"untaxed": "abc"}, "Montant invalide"),
    ({"untaxed": "10", "vat_rate": "x"}, "invalide"),
    ({"untaxed": "10", "account_code": "999"}, "introuvable"),
    ({"untaxed": "10", "account_code": "60"}, "compte de charge"),
    ({"label": "Sans montant"}, "montant HT"),
])
def test_save_lines_validation(books, row, message):
    p = _purchase(books)
    with pytest.raises(LedgerError, match=message):
        purchase_posting.save_lines(p, [row])


def test_save_lines_refused_when_posted(books):
    p = _purchase(books)
    purchase_posting.post(p)
    with pytest.raises(LedgerError, match="annulez"):
        purchase_posting.save_lines(p, [{"untaxed": "1"}])
