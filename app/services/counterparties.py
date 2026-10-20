"""Contreparties bancaires → tiers.

- `link_existing` : rattache les transactions sans tiers à l'entité de même nom
  (débits et crédits), sans jamais en créer.
- `proposals` : contreparties de débits encore sans tiers, groupées par nom, à
  valider (créer le fournisseur, rattacher à une entité existante, ignorer).
  Les opérations sans fournisseur réel (frais Qonto, rémunération, rejets…) sont exclues.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from app.extensions import db
from app.models import BankTransaction, Entity, IgnoredCounterparty

# Types d'opération Qonto sans fournisseur réel derrière la contrepartie.
NO_SUPPLIER_TYPES = {
    "qonto_fee", "account_remuneration", "recall", "direct_debit_hold", "card_acquirer_payout",
    "income", "swift_income", "direct_debit_collection", "financing_installment", "pay_later",
    "investment",
}
SUGGESTIONS = 3


def name_key(name) -> str:
    """Nom normalisé : casse et espaces ignorés, accents conservés."""
    text = unicodedata.normalize("NFKC", name or "")
    return re.sub(r"\s+", " ", text).strip().casefold()[:200]


@dataclass
class Proposal:
    key: str
    label: str
    count: int = 0
    total_cents: int = 0
    first_date: date | None = None
    last_date: date | None = None
    suggestions: list[Entity] = field(default_factory=list)


def _entities_by_key() -> dict[str, Entity]:
    entities = {}
    for entity in Entity.query.order_by(Entity.id).all():
        entities.setdefault(name_key(entity.name), entity)
    return entities


def link_existing(transactions) -> int:
    """Rattache les transactions sans tiers à l'entité de même nom. Retourne le nombre lié."""
    candidates = [t for t in transactions if t.entity_id is None and t.counterparty]
    if not candidates:
        return 0
    entities = _entities_by_key()
    linked = 0
    for txn in candidates:
        entity = entities.get(name_key(txn.counterparty))
        if entity is not None:
            txn.entity_id = entity.id
            linked += 1
    db.session.commit()
    return linked


def _proposal_query(bank_account_id=None):
    query = BankTransaction.query.filter(
        BankTransaction.entity_id.is_(None),
        BankTransaction.counterparty.isnot(None),
        BankTransaction.amount_cents < 0,
        BankTransaction.is_reversed.is_(False),
        db.or_(BankTransaction.raw_type.is_(None),
               BankTransaction.raw_type.notin_(NO_SUPPLIER_TYPES)),
    )
    if bank_account_id is not None:
        query = query.filter(BankTransaction.bank_account_id == bank_account_id)
    return query


def proposals(bank_account_id=None) -> list[Proposal]:
    """Contreparties de débits à valider, les plus fréquentes d'abord."""
    ignored = {row.name_key for row in IgnoredCounterparty.query.all()}
    groups: dict[str, Proposal] = {}
    labels: dict[str, Counter] = {}
    for txn in _proposal_query(bank_account_id).all():
        key = name_key(txn.counterparty)
        if not key or key in ignored:
            continue
        group = groups.setdefault(key, Proposal(key=key, label=txn.counterparty))
        labels.setdefault(key, Counter())[txn.counterparty] += 1
        group.count += 1
        group.total_cents += txn.amount_cents
        group.first_date = min(filter(None, (group.first_date, txn.transaction_date)))
        group.last_date = max(filter(None, (group.last_date, txn.transaction_date)))

    entities = Entity.query.order_by(Entity.name).all() if groups else []
    for key, group in groups.items():
        group.label = labels[key].most_common(1)[0][0]
        first_word = key.split(" ")[0]
        if len(first_word) >= 3:
            group.suggestions = [e for e in entities
                                 if name_key(e.name).startswith(first_word)][:SUGGESTIONS]
    return sorted(groups.values(), key=lambda g: (-g.count, g.label.casefold()))


def count_proposals(bank_account_id=None) -> int:
    return len(proposals(bank_account_id))


def _matching_transactions(key):
    return [t for t in _proposal_query().all() if name_key(t.counterparty) == key]


def accept(key, *, entity_id=None, create_name=None) -> tuple[Entity, int]:
    """Rattache les transactions de la contrepartie à une entité existante ou à un
    nouveau fournisseur. Retourne (entité, nombre de transactions rattachées)."""
    if entity_id:
        entity = db.session.get(Entity, entity_id)
        if entity is None:
            raise ValueError("Tiers introuvable.")
    else:
        name = (create_name or "").strip()
        if not name:
            raise ValueError("Indiquez le nom du fournisseur.")
        entity = Entity.query.filter_by(name=name).first()
        if entity is None:
            entity = Entity(name=name, entity_type="FOURNISSEUR")
            db.session.add(entity)
            db.session.flush()
    transactions = _matching_transactions(key)
    for txn in transactions:
        txn.entity_id = entity.id
    db.session.commit()
    return entity, len(transactions)


def ignore(key, label) -> None:
    """Ne plus proposer cette contrepartie (toutes les transactions, présentes et futures)."""
    if not IgnoredCounterparty.query.filter_by(name_key=key).first():
        db.session.add(IgnoredCounterparty(name_key=key, label=(label or key)[:200]))
        db.session.commit()
