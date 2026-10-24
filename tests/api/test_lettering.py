"""Lot F3 : lettrage des comptes de tiers (manuel, partiel, écart, par document, à-nouveaux détaillés,
FEC, contrepassation, propositions, comptes par défaut)."""
from datetime import date

import pytest

from app.extensions import db
from app.models import (
    Account, Entity, FiscalYear, Journal, JournalEntry, JournalLine, Lettering, Sale,
)
from app.services import closing, fec, lettering, organization, validation
from app.services.ledger import post_entry, reverse
from app.services.lettering import LetteringError, code_for, index_of

from test_sale_payments import API, TODAY, _invoice, _txn, admin  # noqa: F401  (fixture des ventes)


def _error(resp, status):
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()["error"]


@pytest.fixture()
def books(app, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "instance_path", str(tmp_path))
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    accounts = [Account(code=c, label=f"Compte {c}", account_type="OTHER")
                for c in ("411001", "401001", "512100", "706", "6061", "6588", "758", "120", "129", "445660")]
    db.session.add_all([fy, Journal(code="BQ", label="Banque"), Journal(code="VE", label="Ventes"), *accounts,
                        Entity(name="Client SARL", entity_type="CLIENT", customer_account_code="411001")])
    db.session.commit()
    return fy


def _acc(code):
    return Account.query.filter_by(code=code).one()


def _post(fy, journal, day, tiers_cents, desc, tiers="411001", other="706"):
    """Écriture d'un montant signé sur le compte de tiers (positif : débit)."""
    j = Journal.query.filter_by(code=journal).one()
    a, b = _acc(tiers), _acc(other)
    amount = abs(tiers_cents)
    entry = post_entry(fy.id, j.id, day, desc, [
        {"account_id": a.id, "debit_cents": amount if tiers_cents > 0 else 0, "credit_cents": 0 if tiers_cents > 0 else amount},
        {"account_id": b.id, "debit_cents": 0 if tiers_cents > 0 else amount, "credit_cents": amount if tiers_cents > 0 else 0}])
    return next(l for l in entry.lines if l.account_id == a.id)


def test_codes_and_lettrable_default(books):
    assert [code_for(i) for i in (1, 26, 27, 52, 703)] == ["A", "Z", "AA", "AZ", "AAA"]
    assert index_of("AA") == 27 and index_of("ab") == 28
    assert _acc("411001").lettrable and _acc("401001").lettrable and not _acc("445660").lettrable
    assert not _acc("706").lettrable


def test_manual_complete_partial_and_unletter(books, login_as):
    invoice = _post(books, "VE", date(2026, 3, 1), 12000, "Facture F-1")
    first = _post(books, "BQ", date(2026, 3, 10), -5000, "Acompte", other="512100")
    rest = _post(books, "BQ", date(2026, 3, 20), -7000, "Solde", other="512100")
    client = login_as()
    resp = client.post("/api/v1/lettering", json={"line_ids": [invoice.id, first.id]})
    assert resp.status_code == 201 and resp.get_json()["item"] == {"id": resp.get_json()["item"]["id"], "code": "a", "partial": True}
    # Ajouter la dernière ligne au lettrage partiel : complet, nouveau code.
    resp = client.post("/api/v1/lettering", json={"line_ids": [rest.id, first.id]})
    assert resp.get_json()["item"]["code"] == "A" and not resp.get_json()["item"]["partial"]  # code du partiel repris
    assert Lettering.query.count() == 1
    lines = client.get(f"/api/v1/lettering/accounts/{_acc('411001').id}/lines?state=open").get_json()
    assert lines["items"] == [] and lines["open_balance_cents"] == 0
    listed = client.get("/api/v1/lettering/accounts").get_json()["items"]
    assert [(i["code"], i["open_lines"], i["open_balance_cents"]) for i in listed] == [("411001", 0, 0)]
    lettering_id = Lettering.query.one().id
    assert client.delete(f"/api/v1/lettering/{lettering_id}").status_code == 200
    assert JournalLine.query.filter(JournalLine.lettering_id.isnot(None)).count() == 0
    # Comptes différents, compte non lettrable : refusés.
    other = _post(books, "BQ", date(2026, 3, 21), -1000, "Fournisseur", tiers="401001", other="512100")
    assert "même compte" in _error(client.post("/api/v1/lettering", json={"line_ids": [invoice.id, other.id]}), 409)["message"]
    sale_line = next(l for l in invoice.entry.lines if l.account.code == "706")
    assert _error(client.post("/api/v1/lettering", json={"line_ids": [sale_line.id, sale_line.id]}), 409)


def test_gap_entry_within_threshold(books, login_as):
    invoice = _post(books, "VE", date(2026, 3, 1), 12000, "Facture F-2")
    paid = _post(books, "BQ", date(2026, 3, 10), -11960, "Virement", other="512100")
    client = login_as()
    resp = client.post("/api/v1/lettering", json={"line_ids": [invoice.id, paid.id], "gap": True})
    assert resp.status_code == 201, resp.get_json()
    item = Lettering.query.one()
    assert not item.partial and item.gap_entry_id
    gap = db.session.get(JournalEntry, item.gap_entry_id)
    assert sorted((l.account.code, l.debit_cents, l.credit_cents) for l in gap.lines) == [("411001", 0, 40), ("6588", 40, 0)]
    client.delete(f"/api/v1/lettering/{item.id}")
    assert db.session.get(JournalEntry, gap.id) is None
    # Au-delà du seuil (1 €) : refusé.
    late = _post(books, "BQ", date(2026, 3, 11), -10000, "Virement partiel", other="512100")
    assert "seuil" in _error(client.post("/api/v1/lettering", json={"line_ids": [invoice.id, late.id], "gap": True}), 409)["message"]


def test_bank_payment_letters_invoice(admin):
    inv = _invoice(admin)
    txn = _txn(120000)
    admin.post(f"{API}/match", json={"bank_transaction_id": txn.id, "allocations": [{"sale_id": inv["id"], "amount_cents": 120000}]})
    item = Lettering.query.one()
    assert item.origin == "document" and not item.partial and len(item.lines) == 2
    assert {l.account.code for l in item.lines} == {"411001"}
    # Encaissement défait : lettrage retiré.
    payment_id = admin.get(f"{API}/{inv['id']}").get_json()["item"]["payments"][0]["id"]
    assert admin.delete(f"/api/v1/sale-payments/{payment_id}").status_code == 200
    assert Lettering.query.count() == 0


def test_partial_payment_and_credit_note(admin):
    inv = _invoice(admin, amount="1000")
    entity = Entity.query.filter_by(name="Client SARL").one()
    sale = db.session.get(Sale, inv["id"])
    bank = next(a for a in admin.get(f"{API}/{inv['id']}/payment-options").get_json()["accounts"])
    resp = admin.post(f"{API}/{inv['id']}/payments", json={"amount": "200", "paid_on": TODAY.isoformat(),
                                                        "bank_account_id": bank["value"], "method": "check"})
    assert resp.status_code in (200, 201), resp.get_json()
    item = Lettering.query.one()
    assert item.partial and item.balance_cents == 100000 and item.code == "a"
    assert sale.entity_id == entity.id


def test_opening_carries_open_lines_and_next_year_payment(books):
    org = organization.get()
    org.siren = "732829320"
    db.session.commit()
    invoice = _post(books, "VE", date(2026, 12, 15), 30000, "Facture F-9 décembre")
    paid = _post(books, "VE", date(2026, 6, 1), 5000, "Facture F-3")
    paid_back = _post(books, "BQ", date(2026, 6, 5), -5000, "Règlement F-3", other="512100")
    lettering.letter([paid, paid_back])
    for step in closing.DECIDED_BEFORE_CLOSE:
        closing.set_step(books, step, "skipped", note="test du lettrage")
    closing.close_provisional(books)
    following, opening, _ = closing.generate_opening(books, create_next=True)
    carried = [l for l in opening.lines if l.account.code == "411001"]
    assert len(carried) == 1 and carried[0].carried_from_line_id == invoice.id and carried[0].debit_cents == 30000
    assert "F-9" in carried[0].label
    # FEC de 2026 : lettrage de la facture de juin, facture de décembre non lettrée.
    rows = [r.split("\t") for r in fec.build(books).content.decode("iso-8859-15").split("\r\n")[1:] if r]
    letters = {(r[4], r[11], r[12]): (r[13], r[14]) for r in rows}
    assert letters[("411001", "50,00", "0,00")] == ("A", "20260605")
    assert letters[("411001", "300,00", "0,00")] == ("", "")
    # Encaissement en janvier : lettré avec la ligne d'à-nouveau.
    january = _post(following, "BQ", date(2027, 1, 10), -30000, "Règlement F-9", other="512100")
    item = lettering.letter([carried[0], january])
    assert not item.partial and lettering.final_line(invoice).id == carried[0].id


def test_reversal_letters_original_with_inverse(books):
    line = _post(books, "VE", date(2026, 3, 1), 12000, "Facture erronée")
    validation.validate(books, [line.entry], "manual")
    db.session.commit()
    reversal = reverse(line.entry, date(2026, 3, 5), "erreur")
    tiers = next(l for l in reversal.lines if l.account.code == "411001")
    db.session.refresh(line)
    assert line.lettering_id == tiers.lettering_id and line.lettering.origin == "reversal" and not line.lettering.partial


def test_proposals_pairs_and_combinations(books, login_as):
    invoice = _post(books, "VE", date(2026, 3, 1), 12000, "Facture F-1")
    paid = _post(books, "BQ", date(2026, 3, 10), -12000, "Règlement F-1", other="512100")
    big = _post(books, "VE", date(2026, 4, 1), 10000, "Facture F-2")
    part1 = _post(books, "BQ", date(2026, 4, 10), -3000, "Acompte", other="512100")
    part2 = _post(books, "BQ", date(2026, 4, 20), -7000, "Solde", other="512100")
    items = login_as().get(f"/api/v1/lettering/accounts/{_acc('411001').id}/proposals").get_json()["items"]
    assert {"kind": "pair", "line_ids": [invoice.id, paid.id], "amount_cents": 12000} in items
    combo = next(i for i in items if i["kind"] == "combination")
    assert set(combo["line_ids"]) == {big.id, part1.id, part2.id}


def test_tiers_open_balance_and_account_roles(books, login_as):
    _post(books, "VE", date(2026, 3, 1), 12000, "Facture F-1")
    client = login_as(is_admin=True)
    entity = Entity.query.one()
    detail = client.get(f"/api/v1/tiers/{entity.id}").get_json()
    assert detail["lettering"] == [{"kind": "customer", "account_id": _acc("411001").id, "account_code": "411001",
                                    "open_balance_cents": 12000}]
    roles = {r["role"]: r for r in client.get("/api/v1/account-roles").get_json()["items"]}
    assert roles["lettering_gap_expense"]["account"]["code"] == "6588" and not roles["lettering_gap_expense"]["custom"]
    resp = client.put("/api/v1/account-roles", json={"roles": {"lettering_gap_expense": _acc("6061").id},
                                                     "lettering_gap_cents": 250})
    assert resp.status_code == 200, resp.get_json()
    roles = {r["role"]: r for r in resp.get_json()["items"]}
    assert roles["lettering_gap_expense"]["account"]["code"] == "6061" and resp.get_json()["lettering_gap_cents"] == 250


def test_reprise_letters_paid_documents(admin):
    inv = _invoice(admin)
    txn = _txn(120000)
    admin.post(f"{API}/match", json={"bank_transaction_id": txn.id, "allocations": [{"sale_id": inv["id"], "amount_cents": 120000}]})
    db.session.query(JournalLine).update({"lettering_id": None})
    Lettering.query.delete()
    db.session.commit()
    resp = admin.post("/api/v1/lettering/reprise")
    assert resp.get_json()["letterings"] == 1
