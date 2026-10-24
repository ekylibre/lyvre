"""Lettrage des comptes de tiers (lot F3).

- **Lettrer** des lignes d'un même compte lettrable : solde nul → lettrage complet (code en
  majuscules : A, B… Z, AA…) ; sinon **partiel** (minuscules). Écart ≤ seuil de la structure
  (`organization.lettering_gap_cents`, 1 € par défaut) : écriture d'écart OD (comptes par rôle,
  `account_roles`) incluse dans le lettrage, qui devient complet.
- **Délettrer** : les lignes redeviennent ouvertes ; l'écriture d'écart est supprimée (contrepassée
  si validée).
- **Par document** (`sync_sales`, `sync_purchases`) : la ligne de tiers de la facture, celles de
  ses encaissements / règlements et de ses avoirs sont relettrées ensemble (idempotent), après
  chaque encaissement ou règlement ; un lettrage posé à la main sur ces lignes est respecté.
- **Inter-exercices** : une ligne non lettrée à la clôture est reprise une par une dans les
  à-nouveaux (`journal_lines.carried_from_line_id`) ; le lettrage par document suit cette chaîne.
- **Propositions** sur un compte : paires de montants opposés (même tiers, dates proches), puis
  combinaisons de 2 ou 3 lignes (bornées).
"""
import time
from datetime import date
from itertools import combinations

from sqlalchemy import func, or_

from app.extensions import db
from app.models import (
    Account, Journal, JournalEntry, JournalLine, Lettering, Organization, Purchase, PurchasePayment, Sale, SalePayment,
)
from app.models.journal_entry import SOURCE_LETTERING
from app.services import account_roles
from app.services.ledger_errors import LedgerError

DEFAULT_GAP_CENTS = 100
PROPOSAL_LINES = 200
PROPOSAL_SECONDS = 2.0


class LetteringError(LedgerError):
    pass


# ------------------------------------------------------------------ codes


def code_for(index: int) -> str:
    """1 → A, 26 → Z, 27 → AA (numérotation bijective en base 26)."""
    letters = ""
    while index > 0:
        index, rest = divmod(index - 1, 26)
        letters = chr(65 + rest) + letters
    return letters


def index_of(code: str) -> int:
    index = 0
    for char in code.upper():
        index = index * 26 + (ord(char) - 64)
    return index


def next_code(account_id: int) -> str:
    codes = [c for (c,) in db.session.query(Lettering.code).filter(Lettering.account_id == account_id)]
    return code_for(max((index_of(c) for c in codes), default=0) + 1)


# ------------------------------------------------------------------ lettrer / délettrer


def signed(line: JournalLine) -> int:
    return line.debit_cents - line.credit_cents


def gap_threshold() -> int:
    org = Organization.query.first()
    return org.lettering_gap_cents if org is not None else DEFAULT_GAP_CENTS


def _journal_od() -> Journal:
    journal = Journal.query.filter_by(code="OD").first()
    if journal is None:
        journal = Journal(code="OD", label="Opérations diverses")
        db.session.add(journal)
        db.session.flush()
    return journal


def _post_gap(account: Account, balance: int, on_date: date) -> JournalLine:
    """Écriture d'écart : solde le reste du lettrage en charge (reste débiteur) ou produit (créditeur)."""
    from app.services.ledger import open_fiscal_year_for, post_entry
    fy = open_fiscal_year_for(on_date) or open_fiscal_year_for(date.today())
    if fy is None:
        raise LetteringError("Aucun exercice ouvert pour l'écriture d'écart.")
    on_date = min(max(on_date, fy.start_date), fy.end_date)
    try:
        other = account_roles.account_for("lettering_gap_expense" if balance > 0 else "lettering_gap_income")
    except account_roles.RoleError as exc:
        raise LetteringError(str(exc)) from None
    amount = abs(balance)
    label = f"Écart de lettrage {account.code}"
    rows = [{"account_id": account.id, "label": label, "debit_cents": 0 if balance > 0 else amount,
             "credit_cents": amount if balance > 0 else 0},
            {"account_id": other.id, "label": label, "debit_cents": amount if balance > 0 else 0,
             "credit_cents": 0 if balance > 0 else amount}]
    entry = post_entry(fy.id, _journal_od().id, on_date, label, rows, source=SOURCE_LETTERING, commit=False,
                       auto_date=True)
    return next(line for line in entry.lines if line.account_id == account.id)


def letter(lines, origin="manual", gap=False, document=None, user_id=None) -> Lettering:
    """Lettre les lignes (sans commit). Une ligne d'un lettrage partiel l'y entraîne tout entier."""
    lines = list({line.id: line for line in lines}.values())
    if len(lines) < 2:
        raise LetteringError("Sélectionnez au moins deux lignes.")
    if len({line.account_id for line in lines}) != 1:
        raise LetteringError("Les lignes d'un lettrage sont sur le même compte.")
    account = lines[0].account
    if not account.lettrable:
        raise LetteringError(f"Le compte {account.code} n'est pas lettrable.")
    for existing in {line.lettering for line in lines if line.lettering is not None}:
        if not existing.partial:
            raise LetteringError(f"Ligne déjà lettrée ({existing.code}) : délettrez-la d'abord.")
        lines += [line for line in existing.lines if line not in lines]
        _drop(existing)
    balance = sum(signed(line) for line in lines)
    gap_line = None
    if balance and gap:
        if abs(balance) > gap_threshold():
            raise LetteringError(f"Écart de {abs(balance) / 100:.2f} € supérieur au seuil de "
                                 f"{gap_threshold() / 100:.2f} €.".replace(".", ","))
        gap_line = _post_gap(account, balance, max(line.entry.entry_date for line in lines))
        lines.append(gap_line)
        balance = 0
    code = next_code(account.id)
    lettering = Lettering(
        account_id=account.id, code=code if balance == 0 else code.lower(), partial=balance != 0,
        balance_cents=balance, lettered_on=max(line.entry.entry_date for line in lines), origin=origin,
        document_type=document[0] if document else None, document_id=document[1] if document else None,
        gap_entry_id=gap_line.entry_id if gap_line else None, user_id=user_id)
    db.session.add(lettering)
    db.session.flush()
    for line in lines:
        line.lettering_id = lettering.id
    db.session.flush()
    return lettering


def _drop(lettering: Lettering) -> None:
    for line in JournalLine.query.filter_by(lettering_id=lettering.id):
        line.lettering_id = None
    db.session.flush()
    db.session.delete(lettering)
    db.session.flush()


def unletter(lettering: Lettering) -> None:
    """Délettre (sans commit) ; l'écriture d'écart est retirée (contrepassée si validée)."""
    gap = db.session.get(JournalEntry, lettering.gap_entry_id) if lettering.gap_entry_id else None
    _drop(lettering)
    if gap is not None:
        from app.services.ledger import remove_entry
        remove_entry(gap)
        db.session.flush()


def release(line_ids) -> None:
    """Lignes qui disparaissent (écriture supprimée ou contrepassée) : leurs lettrages sont défaits."""
    if not line_ids:
        return
    ids = {i for (i,) in db.session.query(JournalLine.lettering_id).filter(
        JournalLine.id.in_(line_ids), JournalLine.lettering_id.isnot(None))}
    for lettering in Lettering.query.filter(Lettering.id.in_(ids)) if ids else []:
        _drop(lettering)


# ------------------------------------------------------------------ lettrage par document


def final_line(line: JournalLine) -> JournalLine:
    """Ligne reprise en à-nouveau : sa dernière reprise (lettrage dans l'exercice où elle est ouverte)."""
    seen = set()
    while line.id not in seen:
        seen.add(line.id)
        following = JournalLine.query.filter_by(carried_from_line_id=line.id).first()
        if following is None:
            return line
        line = following
    return line


def _sync(document_type: str, document_id: int, account: Account | None, entry_ids) -> Lettering | None:
    if account is None or not account.lettrable:
        return None
    entry_ids = {i for i in entry_ids if i}
    if not entry_ids:
        return None
    lines = JournalLine.query.filter(JournalLine.entry_id.in_(entry_ids), JournalLine.account_id == account.id).all()
    lines = list({line.id: line for line in (final_line(line) for line in lines)}.values())
    current = {line.lettering for line in lines if line.lettering is not None}
    if any(lettering.origin != "document" for lettering in current):
        return None  # lettrage posé à la main : respecté
    for lettering in current:
        _drop(lettering)
    if len(lines) < 2:
        return None
    return letter(lines, origin="document", document=(document_type, document_id))


def _components(start, neighbours):
    seen, groups = set(), []
    for item in start:
        if item is None or item.id in seen:
            continue
        group, todo = [], [item]
        while todo:
            current = todo.pop()
            if current.id in seen:
                continue
            seen.add(current.id)
            group.append(current)
            todo.extend(n for n in neighbours(current) if n is not None and n.id not in seen)
        groups.append(group)
    return groups


def _account_by_code(code) -> Account | None:
    return Account.query.filter_by(code=code).first() if code else None


def sync_sales(sales) -> None:
    """Relettre factures, avoirs et encaissements des ventes (et de celles encaissées avec elles)."""
    def invoice_of(sale):
        return sale.invoice if sale.kind == "credit_note" and sale.invoice is not None else sale

    def neighbours(sale):
        related = []
        for payment in SalePayment.query.filter_by(sale_id=sale.id):
            if payment.journal_entry_id:
                related += [p.sale for p in SalePayment.query.filter_by(journal_entry_id=payment.journal_entry_id)]
        return [invoice_of(s) for s in related]

    invoices = [invoice_of(s) for s in sales if s is not None and s.kind in ("invoice", "credit_note")]
    for group in _components(invoices, neighbours):
        entry_ids = set()
        for sale in group:
            notes = Sale.query.filter(Sale.invoice_id == sale.id, Sale.kind == "credit_note", Sale.status != "draft").all()
            entry_ids |= {s.journal_entry_id for s in [sale, *notes]}
            entry_ids |= {p.journal_entry_id for p in SalePayment.query.filter(SalePayment.sale_id.in_([sale.id, *[n.id for n in notes]]))}
        first = group[0]
        _sync("sale", first.id, _account_by_code(first.entity.customer_account_code if first.entity else None), entry_ids)


def sync_purchases(purchases) -> None:
    """Relettre factures d'achat et règlements (et les factures réglées avec elles)."""
    def neighbours(purchase):
        related = []
        for payment in PurchasePayment.query.filter_by(purchase_id=purchase.id):
            if payment.journal_entry_id:
                related += [p.purchase for p in PurchasePayment.query.filter_by(journal_entry_id=payment.journal_entry_id)]
        return related

    for group in _components([p for p in purchases if p is not None], neighbours):
        entry_ids = {p.journal_entry_id for p in group}
        entry_ids |= {pay.journal_entry_id for pay in PurchasePayment.query.filter(
            PurchasePayment.purchase_id.in_([p.id for p in group]))}
        first = group[0]
        if first.entity is None:
            continue
        _sync("purchase", first.id, _account_by_code(first.entity.account_code), entry_ids)


def reprise() -> dict:
    """Lettrage initial des pièces de Lyvre (factures de vente émises, factures d'achat comptabilisées)."""
    sales = Sale.query.filter(Sale.kind == "invoice", Sale.journal_entry_id.isnot(None)).all()
    purchases = Purchase.query.filter(Purchase.journal_entry_id.isnot(None)).all()
    before = Lettering.query.count()
    sync_sales(sales)
    sync_purchases(purchases)
    db.session.flush()
    return {"sales": len(sales), "purchases": len(purchases), "letterings": Lettering.query.count() - before}


# ------------------------------------------------------------------ lecture


def _open():
    return or_(JournalLine.lettering_id.is_(None), Lettering.partial.is_(True))


def accounts() -> list[dict]:
    """Comptes lettrables mouvementés (même entièrement lettrés) : lignes ouvertes et leur solde."""
    from sqlalchemy import case
    is_open = case((_open(), 1), else_=0)
    rows = (db.session.query(Account, func.coalesce(func.sum(is_open), 0),
                             func.coalesce(func.sum(is_open * (JournalLine.debit_cents - JournalLine.credit_cents)), 0))
            .join(JournalLine, JournalLine.account_id == Account.id)
            .outerjoin(Lettering, Lettering.id == JournalLine.lettering_id)
            .filter(Account.lettrable.is_(True))
            .group_by(Account.id).order_by(Account.code).all())
    return [{"id": a.id, "code": a.code, "label": a.label, "open_lines": n, "open_balance_cents": s} for a, n, s in rows]


def open_balance(account_id: int) -> int:
    return (db.session.query(func.coalesce(func.sum(JournalLine.debit_cents - JournalLine.credit_cents), 0))
            .outerjoin(Lettering, Lettering.id == JournalLine.lettering_id)
            .filter(JournalLine.account_id == account_id, _open()).scalar())


def lines(account_id: int, state: str = "open"):
    query = (JournalLine.query.join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
             .outerjoin(Lettering, Lettering.id == JournalLine.lettering_id)
             .filter(JournalLine.account_id == account_id))
    if state == "open":
        query = query.filter(_open())
    elif state == "lettered":
        query = query.filter(JournalLine.lettering_id.isnot(None))
    return query.order_by(JournalEntry.entry_date, JournalLine.id).all()


def line_payload(line: JournalLine) -> dict:
    entry, lettering = line.entry, line.lettering
    return {"id": line.id, "entry_id": entry.id, "reference": entry.reference, "journal": entry.journal.code,
            "date": entry.entry_date.isoformat(), "label": line.label or entry.description or "",
            "debit_cents": line.debit_cents, "credit_cents": line.credit_cents,
            "lettering": {"id": lettering.id, "code": lettering.code, "partial": lettering.partial,
                          "origin": lettering.origin} if lettering else None,
            "carried": line.carried_from_line_id is not None}


def proposals(account_id: int) -> list[dict]:
    """Paires de montants opposés (même tiers d'abord, dates proches), puis combinaisons de 2 ou 3
    lignes ; chaque ligne dans une seule proposition."""
    candidates = [line for line in lines(account_id, "open") if line.lettering_id is None][-PROPOSAL_LINES:]
    used, found = set(), []
    pairs = []
    for a, b in combinations(candidates, 2):
        if signed(a) and signed(a) == -signed(b):
            same = a.entity_id is not None and a.entity_id == b.entity_id
            reference = bool(a.entry.reference and a.entry.reference in (b.entry.description or "")) or \
                bool(b.entry.reference and b.entry.reference in (a.entry.description or ""))
            gap = abs((a.entry.entry_date - b.entry.entry_date).days)
            pairs.append((-(reference * 2 + same), gap, a, b))
    for _rank, _gap, a, b in sorted(pairs, key=lambda p: (p[0], p[1], p[2].id, p[3].id)):
        if a.id in used or b.id in used:
            continue
        used |= {a.id, b.id}
        found.append({"kind": "pair", "line_ids": [a.id, b.id], "amount_cents": abs(signed(a))})
    deadline = time.monotonic() + PROPOSAL_SECONDS
    rest = [line for line in candidates if line.id not in used]
    for target in rest:
        if target.id in used or time.monotonic() > deadline:
            continue
        opposite = [line for line in rest if line.id not in used and line.id != target.id
                    and signed(line) and (signed(line) > 0) != (signed(target) > 0)]
        for size in (2, 3):
            match = next((combo for combo in combinations(opposite, size)
                          if sum(signed(line) for line in combo) == -signed(target)), None)
            if match:
                used |= {target.id, *(line.id for line in match)}
                found.append({"kind": "combination", "line_ids": [target.id, *(line.id for line in match)],
                              "amount_cents": abs(signed(target))})
                break
            if time.monotonic() > deadline:
                break
    return found
