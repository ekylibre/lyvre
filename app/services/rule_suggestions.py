"""Règles de catégorisation proposées à partir d'un mois (relevés et factures réglées).

Sources, pour les transactions bancaires du mois :

- **facture d'achat** réglée par la transaction (`purchase_payments`, facture lettrée avec son
  règlement) : fournisseur et compte de charge principal de la facture (6…) ;
- **facture de vente** encaissée par la transaction (`sale_payments`) : client et compte de produit
  principal (7…) ;
- **écriture** rapprochée de la transaction, saisie ou corrigée à la main (ni règle, ni facture) : son
  unique compte de charge ou de produit, et le tiers de la transaction.

Les transactions sont regroupées par **motif de libellé** (`label_pattern`) ; un motif donne une règle
(« le libellé contient … ») s'il désigne un seul tiers et un seul compte. Statut d'une proposition :
`new` (à créer), `update` (une règle de même motif existe avec un autre tiers ou compte : la
recréer), `identical` (déjà en place), `conflict` (plusieurs tiers ou comptes), `too_short` (motif
trop court pour être sûr). Rien n'est appliqué aux transactions : « Appliquer les règles » le fait.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date

from app.extensions import db
from app.models import BankTransaction, Entity, JournalEntry, PurchasePayment, Rule, SalePayment

STOPWORDS = {"PRELEVEMENT", "PRLV", "VIREMENT", "VIR", "EMIS", "INST", "VERS", "WEB", "SEPA", "CB", "CARTE", "FACTURE",
             "FACT", "DE", "DU", "DES", "LA", "LE", "LES", "EN", "VOTRE", "FAVEUR", "REF", "ECHEANCE", "PAIEMENT", "PAR",
             "ET", "A", "AU", "AUX", "POUR", "NO", "N", "SAS", "SARL", "SA", "EURL", "FR"}
MIN_PATTERN = 5  # caractères : un motif plus court attraperait d'autres libellés
SOURCE_LABELS = {"purchase": "facture d'achat", "sale": "facture de vente", "entry": "écriture"}


def label_pattern(label: str) -> str | None:
    """Partie stable d'un libellé bancaire : majuscules sans accents, sans mots génériques, chiffres,
    dates ni références ; trois premiers mots significatifs."""
    plain = unicodedata.normalize("NFKD", label or "").encode("ascii", "ignore").decode().upper()
    words = [w for w in re.split(r"[^A-Z0-9]+", plain) if w and not any(c.isdigit() for c in w)
             and w not in STOPWORDS and len(w) > 1]
    return " ".join(words[:3]) or None


@dataclass
class Suggestion:
    pattern: str
    status: str = "new"
    entity: Entity | None = None
    account_code: str | None = None
    rule: Rule | None = None             # règle existante de même motif
    shadowed_by: Rule | None = None      # règle antérieure qui attraperait déjà ces libellés
    reason: str = ""
    transactions: list[BankTransaction] = field(default_factory=list)
    sources: Counter = field(default_factory=Counter)
    entities: set = field(default_factory=set)
    accounts: set = field(default_factory=set)

    @property
    def creatable(self) -> bool:
        return self.status in ("new", "update")


def _main_account(lines, prefix: str) -> str | None:
    """Compte (préfixe 6 ou 7) qui porte la plus grande part des montants des lignes."""
    totals: Counter = Counter()
    for line in lines:
        code = line.account.code if line.account is not None else ""
        if code.startswith(prefix):
            totals[code] += abs(line.untaxed_cents)
    return totals.most_common(1)[0][0] if totals else None


def _from_entry(txn: BankTransaction) -> tuple[Entity | None, str | None]:
    """Écriture rapprochée saisie à la main : son unique compte 6 / 7 (hors écriture de règle)."""
    from app.services import rule_entries

    line = txn.journal_line
    if line is None:
        return None, None
    entry: JournalEntry = line.entry
    if entry.source == "RULE" or rule_entries.document_of(txn) is not None:  # posée par une règle
        return None, None
    accounts = {l.account.code for l in entry.lines if l.id != line.id and (l.account.code or "")[:1] in ("6", "7")}
    if len(accounts) != 1:
        return None, None
    return txn.entity, accounts.pop()


def _observations(start: date, end: date, bank_account_id: int | None):
    """(transaction, tiers, compte, source) des transactions du mois dont on sait la catégorie."""
    query = BankTransaction.query.filter(BankTransaction.transaction_date.between(start, end),
                                         BankTransaction.is_reversed.is_(False))
    if bank_account_id:
        query = query.filter(BankTransaction.bank_account_id == bank_account_id)
    for txn in query.order_by(BankTransaction.transaction_date, BankTransaction.id):
        payment = PurchasePayment.query.filter_by(bank_transaction_id=txn.id).first()
        if payment is not None:
            purchase = payment.purchase
            if purchase.journal_entry_id is not None and purchase.entity is not None:
                yield txn, purchase.entity, _main_account(purchase.lines, "6"), "purchase"
            continue
        sale_payment = SalePayment.query.filter_by(bank_transaction_id=txn.id).first()
        if sale_payment is not None:
            sale = sale_payment.sale
            yield txn, sale.entity, _main_account(sale.lines, "7"), "sale"
            continue
        if txn.reconciled:
            entity, account = _from_entry(txn)
            if account:
                yield txn, entity, account, "entry"


def _first_matching(rules, label: str) -> Rule | None:
    from app.services.rules_engine import _match_rule

    probe = BankTransaction(label=label, amount_cents=0)
    return next((rule for rule in rules if _match_rule(rule, probe)), None)


def suggest(start: date, end: date, bank_account_id: int | None = None) -> list[Suggestion]:
    groups: dict[str, Suggestion] = {}
    for txn, entity, account, source in _observations(start, end, bank_account_id):
        pattern = label_pattern(txn.label)
        if not pattern or not account:
            continue
        s = groups.setdefault(pattern, Suggestion(pattern=pattern))
        s.transactions.append(txn)
        s.sources[source] += 1
        s.entities.add(entity.id if entity is not None else None)
        s.accounts.add(account)
        if entity is not None:
            s.entity = entity
    existing = {(r.label_contains or "").upper(): r for r in Rule.query.filter(Rule.label_contains.isnot(None))
                if not r.label_regex and r.amount_min_cents is None and r.amount_max_cents is None and not r.raw_type}
    active = Rule.query.filter(Rule.is_active.is_(True)).order_by(Rule.position).all()
    for s in groups.values():
        s.account_code = next(iter(s.accounts)) if len(s.accounts) == 1 else None
        s.rule = existing.get(s.pattern)
        if len(s.entities) > 1 or len(s.accounts) > 1:
            s.status = "conflict"
            s.reason = (f"{len(s.accounts)} comptes" if len(s.accounts) > 1 else f"{len(s.entities)} tiers") \
                + " pour ce libellé : règle à écrire à la main."
            continue
        if len(s.pattern) < MIN_PATTERN:
            s.status = "too_short"
            s.reason = "Motif trop court : il attraperait d'autres libellés."
            continue
        if s.rule is not None:
            same_entity = (s.rule.entity_name or None) == (s.entity.name if s.entity else None)
            s.status = "identical" if s.rule.account_code == s.account_code and same_entity else "update"
        first = _first_matching(active, s.transactions[0].label)
        if first is not None and first is not s.rule:
            s.shadowed_by = first
    order = {"update": 0, "new": 1, "conflict": 2, "too_short": 3, "identical": 4}
    return sorted(groups.values(), key=lambda s: (order[s.status], s.pattern))


def apply(start: date, end: date, patterns, bank_account_id: int | None = None) -> dict:
    """Crée ou recrée (met à jour) les règles des motifs choisis ; sans application aux transactions."""
    wanted = set(patterns or [])
    created = updated = 0
    position = (db.session.query(db.func.max(Rule.position)).scalar() or 0) + 1
    for s in suggest(start, end, bank_account_id):
        if s.pattern not in wanted or not s.creatable:
            continue
        name = f"{s.entity.name if s.entity else s.pattern} — relevé {start:%m/%Y}"[:200]
        fields = {"account_code": s.account_code, "entity_name": s.entity.name if s.entity else None,
                  "entity_type": s.entity.entity_type if s.entity else None}
        if s.rule is not None:
            for key, value in fields.items():
                setattr(s.rule, key, value)
            s.rule.name = name
            s.rule.is_active = True
            updated += 1
        else:
            db.session.add(Rule(position=position, name=name, label_contains=s.pattern, is_active=True, **fields))
            position += 1
            created += 1
    db.session.commit()
    return {"created": created, "updated": updated}
