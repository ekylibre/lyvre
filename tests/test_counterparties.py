"""Contreparties bancaires → tiers : rattachement automatique et propositions de fournisseurs."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, BankAccount, BankTransaction, Entity, IgnoredCounterparty
from app.services import counterparties


@pytest.fixture()
def ba(app):
    gl = Account(code="512", label="Banques")
    db.session.add(gl)
    db.session.commit()
    account = BankAccount(label="Qonto", account_id=gl.id, qonto_account_id="acc-1")
    db.session.add(account)
    db.session.commit()
    return account


def _txn(ba, fitid, amount, counterparty, raw_type="transfer", day=1, **extra):
    txn = BankTransaction(bank_account_id=ba.id, fitid=fitid, source="qonto", amount_cents=amount,
                          counterparty=counterparty, raw_type=raw_type,
                          transaction_date=date(2026, 9, day), **extra)
    db.session.add(txn)
    db.session.commit()
    return txn


def test_name_key():
    assert counterparties.name_key("  SARL   Papin ") == "sarl papin"
    assert counterparties.name_key("Énergie") == "énergie"  # accents conservés
    assert counterparties.name_key(None) == ""


def test_link_existing_matches_name_for_debits_and_credits(ba):
    edf = Entity(name="EDF")
    db.session.add(edf)
    db.session.commit()
    debit = _txn(ba, "t1", -1000, "edf ")
    credit = _txn(ba, "t2", 5000, "EDF")
    other = _txn(ba, "t3", -500, "Inconnu")
    assert counterparties.link_existing([debit, credit, other]) == 2
    assert (debit.entity_id, credit.entity_id, other.entity_id) == (edf.id, edf.id, None)
    assert Entity.query.count() == 1  # aucune création


def test_link_existing_keeps_existing_entity(ba):
    a, b = Entity(name="EDF"), Entity(name="Autre")
    db.session.add_all([a, b])
    db.session.commit()
    txn = _txn(ba, "t1", -1000, "EDF", entity_id=b.id)
    assert counterparties.link_existing([txn]) == 0
    assert txn.entity_id == b.id


def test_proposals_group_and_exclude(ba):
    _txn(ba, "t1", -1000, "SARL Papin", day=2)
    _txn(ba, "t2", -2500, "sarl  papin", day=9)
    _txn(ba, "t3", -300, "DUPRE MAINTENANCE")
    _txn(ba, "fee", -122, "Qonto", raw_type="qonto_fee")           # frais : exclu
    _txn(ba, "in", 4837, "Groupe Roy")                               # crédit : exclu
    _txn(ba, "rev", -999, "Annulé SA", is_reversed=True)             # annulée : exclue
    _txn(ba, "ent", -50, "Déjà classé", entity_id=_entity("Déjà classé").id)
    result = counterparties.proposals(ba.id)
    assert [(p.label, p.count, p.total_cents) for p in result] == [
        ("SARL Papin", 2, -3500), ("DUPRE MAINTENANCE", 1, -300),
    ]
    papin = result[0]
    assert (papin.first_date, papin.last_date) == (date(2026, 9, 2), date(2026, 9, 9))


def _entity(name):
    entity = Entity(name=name)
    db.session.add(entity)
    db.session.commit()
    return entity


def test_proposals_suggest_similar_entities(ba):
    _entity("Papin Frères")
    _entity("SARL Papin (ancien)")
    _txn(ba, "t1", -1000, "SARL Papin")
    [proposal] = counterparties.proposals(ba.id)
    assert [e.name for e in proposal.suggestions] == ["SARL Papin (ancien)"]


def test_accept_creates_supplier_and_links_all(ba):
    _txn(ba, "t1", -1000, "SARL Papin")
    _txn(ba, "t2", -2000, "SARL  PAPIN")
    entity, n = counterparties.accept("sarl papin", create_name="SARL Papin")
    assert (n, entity.entity_type) == (2, "FOURNISSEUR")
    assert BankTransaction.query.filter_by(entity_id=entity.id).count() == 2
    assert counterparties.proposals(ba.id) == []


def test_accept_reuses_entity_with_same_name(ba):
    existing = _entity("SARL Papin")
    _txn(ba, "t1", -1000, "Papin")
    entity, _ = counterparties.accept("papin", create_name="SARL Papin")
    assert entity.id == existing.id and Entity.query.count() == 1


def test_accept_links_to_existing_entity(ba):
    target = _entity("Papin & Fils")
    _txn(ba, "t1", -1000, "SARL Papin")
    entity, n = counterparties.accept("sarl papin", entity_id=target.id)
    assert (entity.id, n) == (target.id, 1)


def test_accept_errors(ba):
    with pytest.raises(ValueError, match="nom du fournisseur"):
        counterparties.accept("x", create_name="  ")
    with pytest.raises(ValueError, match="introuvable"):
        counterparties.accept("x", entity_id=999)


def test_ignore_is_remembered(ba):
    _txn(ba, "t1", -1000, "Boulangerie")
    counterparties.ignore("boulangerie", "Boulangerie")
    counterparties.ignore("boulangerie", "Boulangerie")
    assert IgnoredCounterparty.query.count() == 1
    _txn(ba, "t2", -800, "BOULANGERIE")  # nouvelle transaction : toujours ignorée
    assert counterparties.proposals(ba.id) == []


# ------------------------------------------------------------------- écrans

def test_counterparties_screen_and_actions(login_as, ba):
    _txn(ba, "t1", -1000, "SARL Papin")
    _txn(ba, "t2", -300, "DUPRE MAINTENANCE")
    _txn(ba, "t3", -50, "Boulangerie")
    client = login_as(is_admin=False)
    page = client.get(f"/bank-accounts/{ba.id}/transactions").get_data(as_text=True)
    assert "3 contrepartie(s) de débits sans tiers" in page

    html = client.get(f"/bank-accounts/{ba.id}/counterparties").get_data(as_text=True)
    assert "SARL Papin" in html and "DUPRE MAINTENANCE" in html

    resp = client.post(f"/bank-accounts/{ba.id}/counterparties", follow_redirects=True, data={
        "action": "create", "name_key": "sarl papin", "label": "SARL Papin", "name": "SARL Papin"})
    assert "Fournisseur « SARL Papin » : 1 transaction(s) rattachée(s)." in resp.get_data(as_text=True)

    target = _entity("Dupré Maintenance Énergies")
    client.post(f"/bank-accounts/{ba.id}/counterparties", data={
        "action": "link", "name_key": "dupre maintenance", "label": "DUPRE", "entity_id": target.id})
    client.post(f"/bank-accounts/{ba.id}/counterparties", data={
        "action": "ignore", "name_key": "boulangerie", "label": "Boulangerie"})
    html = client.get(f"/bank-accounts/{ba.id}/counterparties").get_data(as_text=True)
    assert "Aucune contrepartie à valider" in html
    page = client.get(f"/bank-accounts/{ba.id}/transactions").get_data(as_text=True)
    assert "contrepartie(s) de débits sans tiers" not in page


def test_counterparties_screen_error_message(login_as, ba):
    client = login_as(is_admin=False)
    resp = client.post(f"/bank-accounts/{ba.id}/counterparties", follow_redirects=True,
                       data={"action": "create", "name_key": "x", "label": "X", "name": ""})
    assert "Indiquez le nom du fournisseur." in resp.get_data(as_text=True)
