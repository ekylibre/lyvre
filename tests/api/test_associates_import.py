"""Module « Associés », lot A5 : import CSV (analyse sans écriture, import tout ou rien, soldes
d'ouverture seulement sur un compte courant vierge)."""
import io
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, Associate, Entity, FiscalYear, Instance, JournalEntry
from app.models.associate import ShareMovement
from app.services import associates

EKYLIBRE = """nom;compte;nature;parts;date;nominal;solde;taux
Alain Martin;45510300;usufruit;300;01/01/2026;10,00;86 963,08;
Agnès Martin;45510301;Nu-propriété;150;01/01/2026;10,00;500,00;
Bruno Martin;45510302;NP;150;01/01/2026;10,00;300,00;
Bruno Martin;45510302;PP;700;01/01/2026;10,00;;
"""


@pytest.fixture()
def admin(app, login_as):
    client = login_as(role="admin")
    Instance.query.one().has_associates = True
    db.session.add_all([Account(code="455", label="Associés", account_type="TIERS"),
                        Account(code="471", label="Compte d'attente", account_type="TIERS"),
                        FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))])
    db.session.commit()
    return client


def _send(client, url, text, **form):
    data = {"file": (io.BytesIO(text.encode("utf-8")), "associes.csv"), **form}
    return client.post(url, data=data, content_type="multipart/form-data")


def test_preview_then_import(admin):
    preview = _send(admin, "/api/v1/associates/import/preview", EKYLIBRE)
    body = preview.get_json()
    assert preview.status_code == 200 and body["ok"], body
    assert [(a["name"], a["account_code"], a["action"], a["balance_action"]) for a in body["associates"]] == [
        ("Alain Martin", "45510300", "create", "entry"), ("Agnès Martin", "45510301", "create", "entry"),
        ("Bruno Martin", "45510302", "create", "entry")]
    assert body["associates"][2]["parts"] == {"full": 700, "usufruct": 0, "bare": 150}
    assert body["movements"] == [{"date": "2026-01-01", "nominal_cents": 1000, "parts": 1000}]
    assert body["needs_counterpart"] and any(c["value"] == "471" for c in body["counterparts"])
    assert Associate.query.count() == 0  # rien d'écrit

    refused = _send(admin, "/api/v1/associates/import", EKYLIBRE)
    assert refused.status_code == 422 and "contrepartie" in refused.get_json()["error"]["message"]
    done = _send(admin, "/api/v1/associates/import", EKYLIBRE, counterpart_code="471")
    assert done.status_code == 200, done.get_json()
    assert done.get_json()["result"] == {"created": 3, "reused": 0, "movements": 1, "entries": 3}
    pascal = Associate.query.join(Entity).filter(Entity.name == "Alain Martin").one()
    assert pascal.account.code == "45510300" and associates.balance(pascal.account_id) == 8_696_308
    assert ShareMovement.query.one().kind == "opening"
    entry = JournalEntry.query.filter_by(source_ref=f"OPENING:{pascal.id}").one()
    assert entry.journal.code == "AN" and entry.entry_date == date(2026, 1, 1)

    # Réimporter : associés repris, soldes ignorés (comptes déjà mouvementés).
    again = _send(admin, "/api/v1/associates/import/preview", EKYLIBRE).get_json()
    assert {a["action"] for a in again["associates"]} == {"reuse"}
    assert {a["balance_action"] for a in again["associates"]} == {"ignored"} and not again["needs_counterpart"]


@pytest.mark.parametrize("text, message", [
    ("nom;parts\nA;1\n", "Colonnes manquantes"),
    ("nom;nature;parts;date;nominal\nA;XX;1;01/01/2026;1\n", "nature"),
    ("nom;nature;parts;date;nominal\nA;PP;-3;01/01/2026;1\n", "entier positif"),
    ("nom;nature;parts;date;nominal\nA;PP;3;32/01/2026;1\n", "date invalide"),
    ("nom;nature;parts;date\nA;PP;3;01/01/2026\n", "nominale manquante"),
    ("nom;nature;parts;date;nominal\nA;US;3;01/01/2026;1\n", "Démembrement"),
    ("nom;compte;nature;parts;date;nominal\nA;4551001;PP;3;01/01/2026;1\nA;4551009;PP;1;01/01/2026;1\n", "compte différent"),
    ("nom;compte;nature;parts;date;nominal\nA;401;PP;3;01/01/2026;1\n", "sous-compte 455"),
])
def test_errors_block_the_import(admin, text, message):
    body = _send(admin, "/api/v1/associates/import/preview", text).get_json()
    if "error" in body:
        assert message in body["error"]["message"]
        return
    found = body["errors"] + [e for r in body["rows"] for e in r["errors"]]
    assert not body["ok"] and any(message in e for e in found), found
    assert _send(admin, "/api/v1/associates/import", text, counterpart_code="471").status_code == 422
    assert Associate.query.count() == 0 and Entity.query.count() == 0


def test_existing_associate_and_entity_reused(admin):
    existing = associates.create({"new_name": "Léa Martin"})
    db.session.add(Entity(name="Marie Martin", entity_type="CLIENT"))
    db.session.commit()
    text = ("nom,nature,parts,date,nominal,taux\n"
            "Léa Martin,PP,10,01/01/2026,1,\"1,5\"\n"
            "Marie Martin,PP,5,01/01/2026,1,\n")
    body = _send(admin, "/api/v1/associates/import/preview", text).get_json()
    assert body["ok"], body
    assert [(a["name"], a["action"], a["account_code"]) for a in body["associates"]] == [
        ("Léa Martin", "reuse", existing.account.code), ("Marie Martin", "create", "4551002")]
    done = _send(admin, "/api/v1/associates/import", text).get_json()
    assert done["result"]["created"] == 1 and done["result"]["entries"] == 0
    assert db.session.get(Associate, existing.id).interest_rate_bp == 150
    assert Entity.query.filter_by(name="Marie Martin").one().entity_type == "CLIENT"  # entité reprise


def test_template_and_rights(app, login_as):
    client = login_as(role="treasurer")
    Instance.query.one().has_associates = True
    db.session.commit()
    template = client.get("/api/v1/associates/import/template")
    assert template.status_code == 200 and "nom;compte;nature" in template.get_data(as_text=True)
    assert _send(client, "/api/v1/associates/import/preview", EKYLIBRE).status_code == 403
