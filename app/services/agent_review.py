"""Vérification humaine des objets créés par une clé d'API (lot AK3, claudedocs/design_api_mcp_aiffel.md § 9.2).

- Facture d'achat : « Marquer vérifiée » lève le motif « à vérifier » (`purchase_posting.purchase_state`), puis la
  facture est comptabilisée si elle est prête, comme toute facture saisie.
- Tiers : « Marquer vérifié ».
- Écriture : vérifiée par sa validation (numéro), comme une saisie manuelle.
"""
from __future__ import annotations

from datetime import datetime

from app.extensions import db


def origin_payload(obj) -> dict | None:
    """Badge d'origine d'un objet (achat, tiers, écriture), ou None s'il a été saisi dans Lyvre."""
    if getattr(obj, "origin_key_id", None) is None:
        return None
    checked = getattr(obj, "checked_at", None)
    if hasattr(obj, "validation_number"):
        pending = obj.validation_number is None
    else:
        pending = checked is None
    return {"label": obj.origin_label, "external_ref": obj.external_ref, "pending": pending,
            "checked_at": checked.isoformat() if checked else None}


def check_purchase(p, user) -> dict:
    """Marque vérifiée (commit) et comptabilise si elle est prête. Renvoie le résultat de `post_ready`."""
    from app.services import purchase_posting
    if p.origin_key_id is None:
        raise ValueError("Cette facture n'a pas été saisie par une clé d'API.")
    if p.checked_at is None:
        p.checked_at, p.checked_by_id = datetime.utcnow(), user.id
        db.session.commit()
    return purchase_posting.post_ready([p])


def check_entity(entity, user) -> None:
    if entity.origin_key_id is None:
        raise ValueError("Ce tiers n'a pas été créé par une clé d'API.")
    if entity.checked_at is None:
        entity.checked_at, entity.checked_by_id = datetime.utcnow(), user.id
        db.session.commit()


def counts() -> dict:
    """Saisies par clé à vérifier : achats et tiers non vérifiés, écritures non validées."""
    from app.models import Entity, JournalEntry, Purchase
    purchases = Purchase.query.filter(Purchase.origin_key_id.isnot(None), Purchase.checked_at.is_(None),
                                      Purchase.is_hidden.is_(False), Purchase.journal_entry_id.is_(None)).count()
    entities = Entity.query.filter(Entity.origin_key_id.isnot(None), Entity.checked_at.is_(None)).count()
    entries = JournalEntry.query.filter(JournalEntry.origin_key_id.isnot(None),
                                        JournalEntry.validation_number.is_(None)).count()
    return {"purchases": purchases, "entities": entities, "entries": entries,
            "total": purchases + entities + entries}
