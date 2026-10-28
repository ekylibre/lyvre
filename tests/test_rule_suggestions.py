"""Règles de catégorisation proposées depuis un mois : transactions réglées par une facture ou rapprochées
d'une écriture saisie, regroupées par motif de libellé ; création, recréation, ambiguïtés."""
from datetime import date

from app.extensions import db
from app.models import Account, Entity, Rule
from app.services import purchase_settlement as ps
from app.services import rule_suggestions as rs
from app.services.ledger import post_entry
from app.services.reconciler import reconcile
from test_purchase_settlement_ofx import books, invoice, txn as _txn  # noqa: F401  (fixture)

SEPTEMBER = (date(2026, 9, 1), date(2026, 9, 30))


def txn(books, day, label, amount=-3999):  # noqa: F811
    t = _txn(books, day, amount=amount)
    t.label = label
    db.session.commit()
    return t


def _by_pattern():
    return {s.pattern: s for s in rs.suggest(*SEPTEMBER)}


def test_label_pattern():
    assert rs.label_pattern("PRLV SEPA FREE PRO 1234567 ECHEANCE 09/2026") == "FREE PRO"
    assert rs.label_pattern("Qonto — solo_smart_2024 7") == "QONTO SOLO SMART"
    assert rs.label_pattern("123 456") is None


def test_create_then_identical_then_recreate(books):  # noqa: F811
    invoice(books)  # Free, 39,99 € sur 6061, payée par le débit unique ci-dessous
    txn(books, date(2026, 9, 4), "PRLV FREE PRO 1234567")
    assert ps.auto_match()["matched"] == 1
    s = _by_pattern()["FREE PRO"]
    assert (s.status, s.entity.name, s.account_code, dict(s.sources)) == ("new", "Free", "6061", {"purchase": 1})

    assert rs.apply(*SEPTEMBER, ["FREE PRO"]) == {"created": 1, "updated": 0}
    rule = Rule.query.one()
    assert (rule.label_contains, rule.account_code, rule.entity_name, rule.is_active) == ("FREE PRO", "6061", "Free", True)
    assert rule.name == "Free — relevé 09/2026"
    assert _by_pattern()["FREE PRO"].status == "identical"

    rule.account_code = "6068"  # la règle a changé depuis : à recréer
    db.session.commit()
    assert _by_pattern()["FREE PRO"].status == "update"
    assert rs.apply(*SEPTEMBER, ["FREE PRO"]) == {"created": 0, "updated": 1}
    assert Rule.query.one().account_code == "6061"


def test_ambiguous_and_short_patterns(books):  # noqa: F811
    invoice(books, number="F-1", supplier="Free")
    invoice(books, number="O-1", supplier="Orange", total=2000)
    txn(books, date(2026, 9, 3), "PRLV TELECOM SERVICES 1")
    txn(books, date(2026, 9, 4), "PRLV TELECOM SERVICES 2", amount=-2000)
    invoice(books, number="A-1", supplier="Avia", total=625)
    txn(books, date(2026, 9, 5), "AVIA", amount=-625)
    ps.auto_match()
    found = _by_pattern()
    assert found["TELECOM SERVICES"].status == "conflict" and not found["TELECOM SERVICES"].creatable
    assert found["AVIA"].status == "too_short"
    assert rs.apply(*SEPTEMBER, ["TELECOM SERVICES", "AVIA"]) == {"created": 0, "updated": 0}


def test_manual_entry_on_a_statement(books):  # noqa: F811
    travel = Account(code="6251", label="Voyages et déplacements", account_type="EXPENSE")
    db.session.add(travel)
    db.session.commit()
    t = txn(books, date(2026, 9, 10), "AUTOROUTES DU SUD 4521", amount=-920)
    t.entity = Entity(name="VINCI Autoroutes")
    entry = post_entry(books["fy"].id, 2, date(2026, 9, 10), "Péage", [
        {"account_id": travel.id, "label": "Péage", "debit_cents": 920, "credit_cents": 0},
        {"account_id": books["512"].id, "label": "Péage", "debit_cents": 0, "credit_cents": 920}])
    reconcile(t.id, next(l.id for l in entry.lines if l.account_id == books["512"].id))
    s = _by_pattern()["AUTOROUTES SUD"]
    assert (s.status, s.account_code, s.entity.name, dict(s.sources)) == ("new", "6251", "VINCI Autoroutes", {"entry": 1})


def test_shadowed_by_an_earlier_rule(books):  # noqa: F811
    db.session.add(Rule(position=1, name="Tout Free", label_contains="FREE", account_code="6068", is_active=True))
    db.session.commit()
    invoice(books)
    txn(books, date(2026, 9, 4), "PRLV FREE PRO 1234567")
    ps.auto_match()
    s = _by_pattern()["FREE PRO"]
    assert s.status == "new" and s.shadowed_by.name == "Tout Free"


def test_api(books, login_as):  # noqa: F811
    client = login_as()
    invoice(books)
    txn(books, date(2026, 9, 4), "PRLV FREE PRO 1234567")
    ps.auto_match()
    items = client.get("/api/v1/rules/suggestions?period=2026-09").get_json()["items"]
    assert items[0]["pattern"] == "FREE PRO" and items[0]["sources"] == {"facture d'achat": 1}
    assert client.get("/api/v1/rules/suggestions?period=sept").status_code == 422
    assert client.post("/api/v1/rules/suggestions", json={"period": "2026-09", "patterns": []}).status_code == 422
    resp = client.post("/api/v1/rules/suggestions", json={"period": "2026-09", "patterns": ["FREE PRO"]})
    assert resp.status_code == 200 and resp.get_json()["result"] == {"created": 1, "updated": 0}
