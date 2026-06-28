"""Tests du module de mise à jour de la fiche tiers Odoo (Notes interne)."""
from datetime import date, datetime

import pytest

from app.extensions import db
from app.models import Entity, Order
from app.services import odoo_partner_update as opu


# --- bloc de note --------------------------------------------------------


def test_build_note_block_green():
    block = opu.build_note_block(
        date(2026, 12, 31), {"color": "green"}, today=date(2026, 6, 28)
    )
    assert opu.NOTE_MARKER_START in block
    assert opu.NOTE_MARKER_END in block
    assert "31/12/2026" in block
    assert "Adhésion à jour" in block
    assert "Mise à jour : 28/06/2026" in block


def test_build_note_block_status_labels():
    for color, label in opu.STATUS_LABELS.items():
        block = opu.build_note_block(date(2026, 1, 1), {"color": color})
        assert label in block


# --- merge idempotent ----------------------------------------------------


def test_merge_into_empty_comment():
    block = opu.build_note_block(date(2026, 1, 1), {"color": "red"})
    assert opu.merge_into_comment("", block) == block
    # Odoo renvoie False pour un champ vide.
    assert opu.merge_into_comment(False, block) == block


def test_merge_preserves_free_text():
    block = opu.build_note_block(date(2026, 1, 1), {"color": "red"})
    merged = opu.merge_into_comment("Note manuelle importante.", block)
    assert merged.startswith("Note manuelle importante.")
    assert merged.endswith(block)


def test_merge_replaces_previous_block():
    old = opu.build_note_block(date(2025, 1, 1), {"color": "green"})
    existing = f"Texte libre.\n\n{old}"
    new = opu.build_note_block(date(2026, 1, 1), {"color": "red"})
    merged = opu.merge_into_comment(existing, new)
    # Un seul bloc géré, c'est le nouveau.
    assert merged.count(opu.NOTE_MARKER_START) == 1
    assert "01/01/2026" in merged
    assert "01/01/2025" not in merged
    assert "Texte libre." in merged


# --- résolution du partner Odoo ------------------------------------------


class FakeClient:
    """Client Odoo factice : enregistre les écritures, sert les recherches."""

    def __init__(self, partners_by_email=None, comments=None):
        self.partners_by_email = partners_by_email or {}
        self.comments = comments or {}
        self.writes = []

    def search_read(self, model, domain=None, fields=None, limit=None, **kw):
        if model != "res.partner":
            return []
        # Recherche par email : domain = [["email", "in", [...]]]
        if domain and domain[0][0] == "email":
            wanted = {e.lower() for e in domain[0][2]}
            return [
                {"id": pid, "email": email}
                for email, pid in self.partners_by_email.items()
                if email.lower() in wanted
            ]
        # Recherche par id pour relire le comment.
        if domain and domain[0][0] == "id":
            pid = domain[0][2]
            return [{"id": pid, "comment": self.comments.get(pid, "")}]
        return []

    def write(self, model, ids, values):
        if isinstance(ids, int):
            ids = [ids]
        for pid in ids:
            self.writes.append((pid, values))
            if "comment" in values:
                self.comments[pid] = values["comment"]
        return True


def test_resolve_prefers_order_partner_id(session):
    ent = Entity(name="Alice", entity_type="ADHERENT", email="alice@example.org")
    db.session.add(ent)
    db.session.commit()
    db.session.add(Order(odoo_id=1, partner_id=42, entity_id=ent.id,
                         date_order=datetime(2026, 1, 1)))
    db.session.commit()

    client = FakeClient(partners_by_email={"alice@example.org": 99})
    resolved = opu.resolve_partner_ids(client, [ent])
    # La commande POS (42) prime sur la recherche email (99).
    assert resolved == {ent.id: 42}


def test_resolve_falls_back_to_email(session):
    ent = Entity(name="Bob", entity_type="ADHERENT", email="bob@example.org")
    db.session.add(ent)
    db.session.commit()

    client = FakeClient(partners_by_email={"bob@example.org": 7})
    resolved = opu.resolve_partner_ids(client, [ent])
    assert resolved == {ent.id: 7}


def test_resolve_unmatched_entity_absent(session):
    ent = Entity(name="Carol", entity_type="ADHERENT", email="carol@example.org")
    db.session.add(ent)
    db.session.commit()

    client = FakeClient(partners_by_email={})  # pas de fiche Odoo
    resolved = opu.resolve_partner_ids(client, [ent])
    assert resolved == {}


# --- mise à jour de bout en bout (client factice) ------------------------


def test_update_member_notes_writes_comment(session):
    ent = Entity(name="Dora", entity_type="ADHERENT", email="dora@example.org")
    db.session.add(ent)
    db.session.commit()

    client = FakeClient(partners_by_email={"dora@example.org": 5})
    rows = [{"entity": ent, "birthday": date(2026, 12, 1), "color": "green"}]
    result = opu.update_member_notes(rows, today=date(2026, 6, 28), client=client)

    assert result["updated"] == 1
    assert result["skipped"] == 0
    assert result["errors"] == 0
    assert client.writes[0][0] == 5
    written = client.writes[0][1]["comment"]
    assert "01/12/2026" in written
    assert "Adhésion à jour" in written


def test_update_member_notes_idempotent(session):
    ent = Entity(name="Eve", entity_type="ADHERENT", email="eve@example.org")
    db.session.add(ent)
    db.session.commit()

    client = FakeClient(partners_by_email={"eve@example.org": 3})
    rows = [{"entity": ent, "birthday": date(2026, 12, 1), "color": "orange"}]
    opu.update_member_notes(rows, today=date(2026, 6, 28), client=client)
    opu.update_member_notes(rows, today=date(2026, 6, 28), client=client)

    # Deux passages : un seul bloc géré dans le comment final.
    final = client.comments[3]
    assert final.count(opu.NOTE_MARKER_START) == 1


def test_update_member_notes_skips_unresolved(session):
    ent = Entity(name="Frank", entity_type="ADHERENT", email="frank@example.org")
    db.session.add(ent)
    db.session.commit()

    client = FakeClient(partners_by_email={})  # introuvable
    rows = [{"entity": ent, "birthday": date(2026, 12, 1), "color": "red"}]
    result = opu.update_member_notes(rows, today=date(2026, 6, 28), client=client)

    assert result["updated"] == 0
    assert result["skipped"] == 1
    assert client.writes == []
