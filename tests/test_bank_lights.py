"""Lot TX1 : feu des transactions (règle, motifs, légende et filtre de la liste), catégorie affichée
(Lyvre d'abord, puis Qonto), catégories Qonto lues à la synchronisation et relecture complète unique."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, BankAccount, BankTransaction
from app.services import bank_lights
from test_qonto_sync import SYNC_FROM, FakeClient, ba, tx  # noqa: F401  (fixture ba)


def _bt(**kw):
    values = {"is_reversed": False, "reconciled": False, "attachment_count": 0, "attachment_required": True,
              "attachment_lost": False, "category": None, "qonto_category": None,
              "qonto_cashflow_category": None, "qonto_cashflow_subcategory": None}
    return BankTransaction(**{**values, **kw})


@pytest.mark.parametrize("kw, default_tiers, expected", [
    ({"reconciled": True, "attachment_count": 1}, False, ("green", ["Rapprochée"])),
    ({"reconciled": True, "attachment_count": None, "attachment_required": None}, False, ("green", ["Rapprochée"])),  # OFX
    ({"is_reversed": True}, False, ("green", ["Annulée par la banque"])),
    ({}, False, ("orange", ["À rapprocher", "Justificatif manquant"])),
    ({"reconciled": True}, False, ("orange", ["Justificatif manquant"])),
    ({"reconciled": True, "attachment_count": 1}, True, ("orange", ["Tiers par défaut"])),
    ({"reconciled": True, "attachment_lost": True}, False, ("red", ["Justificatif perdu"])),
    ({"is_reversed": True, "reconciled": True, "attachment_count": 1}, False,
     ("red", ["Annulée par la banque mais encore rapprochée"])),
    ({"attachment_lost": True}, False, ("red", ["Justificatif perdu", "À rapprocher"])),
])
def test_light_rules(kw, default_tiers, expected):
    assert bank_lights.light(_bt(**kw), rule_default_tiers=default_tiers) == expected


@pytest.mark.parametrize("kw, expected", [
    # Facture liée et écriture passée : à jour, même sans justificatif Qonto ni rapprochement.
    ({"journal_line_id": 7, "reconciled": True}, ("green", ["Facture liée et écriture passée"])),
    ({"journal_line_id": 7, "attachment_lost": True}, ("green", ["Facture liée et écriture passée"])),
    ({}, ("orange", ["À rapprocher", "Justificatif manquant"])),  # facture liée mais pas d'écriture
    ({"journal_line_id": 7, "reconciled": True, "is_reversed": True}, ("red", ["Annulée par la banque mais encore rapprochée"])),
])
def test_linked_invoice_and_entry_are_up_to_date(kw, expected):
    assert bank_lights.light(_bt(**kw), has_invoice=True) == expected


def test_category_display_order():
    assert bank_lights.category_display(_bt(category="Énergie", qonto_cashflow_subcategory="Électricité")) == \
        {"label": "Énergie", "source": "lyvre"}
    assert bank_lights.category_display(_bt(qonto_cashflow_category="Technologies",
                                            qonto_cashflow_subcategory="Licences logicielles"))["label"] == \
        "Licences logicielles"
    assert bank_lights.category_display(_bt(qonto_category="online_service", qonto_cashflow_category="")) == \
        {"label": "Services en ligne", "source": "qonto"}
    assert bank_lights.category_display(_bt(qonto_category="space_travel"))["label"] == "Space travel"
    assert bank_lights.category_display(_bt(qonto_category="")) is None


def test_list_returns_lights_counts_and_filters(app, login_as):
    client = login_as()
    gl = Account(code="512", label="Banque")
    db.session.add(gl)
    db.session.flush()
    account = BankAccount(label="Compte", account_id=gl.id)
    db.session.add(account)
    db.session.flush()
    rows = [("a", {"reconciled": True, "attachment_count": 1}), ("b", {}), ("c", {}),
            ("d", {"reconciled": True, "attachment_lost": True})]
    for fitid, kw in rows:
        db.session.add(_bt(bank_account_id=account.id, fitid=fitid, transaction_date=date(2026, 7, 2),
                           amount_cents=-1000, label=fitid, qonto_category="online_service", **kw))
    db.session.commit()
    url = f"/api/v1/bank-accounts/{account.id}/transactions?status=all"
    body = client.get(url).get_json()
    assert body["lights"] == {"green": 1, "orange": 2, "red": 1}
    first = next(t for t in body["transactions"] if t["label"] == "b")
    assert first["light"] == "orange" and first["light_reasons"] == ["À rapprocher", "Justificatif manquant"]
    assert first["category_display"] == {"label": "Services en ligne", "source": "qonto"}
    filtered = client.get(url + "&light=orange").get_json()
    assert sorted(t["label"] for t in filtered["transactions"]) == ["b", "c"]
    assert filtered["lights"] == body["lights"]  # comptes de la légende avant le filtre
    assert len(client.get(url + "&light=bleu").get_json()["transactions"]) == 4  # couleur inconnue : ignorée


def test_sync_reads_qonto_categories(ba):  # noqa: F811
    from app.services import qonto_sync
    fake = FakeClient([
        tx("t1", 1000, category="online_service", cashflow_category={"id": "c1", "name": "Technologies"},
           cashflow_subcategory={"id": "s1", "name": "Licences logicielles"}),
        tx("t2", 2000, category=None, cashflow_category=None, cashflow_subcategory=None),
    ])
    qonto_sync.sync_bank_account(ba.id, client=fake)
    t1, t2 = (BankTransaction.query.filter_by(fitid=f).one() for f in ("t1", "t2"))
    assert (t1.qonto_category, t1.qonto_cashflow_category, t1.qonto_cashflow_subcategory) == \
        ("online_service", "Technologies", "Licences logicielles")
    assert (t2.qonto_category, t2.qonto_cashflow_category, t2.qonto_cashflow_subcategory) == ("", "", "")


def test_unread_categories_trigger_one_full_reread(ba):  # noqa: F811
    from app.services import qonto_sync
    fake = FakeClient([tx("t1", 1000, category="online_service")])
    qonto_sync.sync_bank_account(ba.id, client=fake)
    BankTransaction.query.filter_by(fitid="t1").one().qonto_category = None  # importée avant le lot TX1
    db.session.commit()
    fake.calls.clear()
    qonto_sync.sync_bank_account(ba.id, client=fake)
    assert fake.calls and all("settled_from" in c for c in fake.calls)  # relecture par mois, depuis SYNC_FROM
    assert BankTransaction.query.filter_by(fitid="t1").one().qonto_category == "online_service"
    fake.calls.clear()
    qonto_sync.sync_bank_account(ba.id, client=fake)
    assert fake.calls and all("updated_from" in c for c in fake.calls)  # ensuite : incrémentale
