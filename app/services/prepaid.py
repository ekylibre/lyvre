"""Charges et produits constatés d'avance proposés à la clôture (lot F4).

Sources, pour les écritures de l'exercice dont la période de service dépasse sa fin :
- factures d'achat comptabilisées (`purchases.service_start` / `service_end`, sinon la période de
  l'échéance d'abonnement rattachée : échéance → échéance suivante − 1 jour) : charges (classe 6) ;
- factures de vente émises (`sales.service_start` / `service_end`) : produits (classe 7) ;
- lignes d'écriture de classe 6 ou 7 portant une période (`journal_lines.service_*`).

Montant = arrondi(montant de la charge ou du produit × jours de la période après la clôture / jours
de la période), par compte. Les propositions retenues passent par `closing.add_inventory` (écriture OD
au dernier jour, extournée à l'ouverture de N+1), avec `source_ref` = clé de la proposition : une
proposition déjà passée est signalée, pas reproposée.
"""
from dataclasses import asdict, dataclass
from datetime import date, timedelta

from app.extensions import db
from app.models import JournalEntry, JournalLine, Purchase, Sale, Subscription, SubscriptionPeriod
from app.models.journal_entry import SOURCE_INVENTORY, SOURCE_SALE


@dataclass
class Proposal:
    key: str
    kind: str                 # prepaid_expense (486) ou deferred_income (487)
    source: str               # purchase, sale, line
    source_id: int
    url: str
    label: str
    account_code: str
    period_start: str
    period_end: str
    base_cents: int
    days_after: int
    days_total: int
    amount_cents: int
    posted: bool


def share(base_cents: int, start: date, end: date, closing: date) -> tuple[int, int, int]:
    """(montant après la clôture, jours après, jours de la période)."""
    total = (end - start).days + 1
    after = (end - max(start, closing + timedelta(days=1))).days + 1 if end > closing else 0
    return round(base_cents * max(after, 0) / total), max(after, 0), total


def subscription_period(purchase: Purchase) -> tuple[date, date] | None:
    from app.services.recurrence import add_months
    from app.services.subscriptions import FREQUENCIES
    period = SubscriptionPeriod.query.filter_by(purchase_id=purchase.id).first()
    if period is None:
        return None
    sub = db.session.get(Subscription, period.subscription_id)
    following = add_months(period.due_date, FREQUENCIES[sub.frequency], sub.due_day)
    return period.due_date, following - timedelta(days=1)


def _amounts(entry: JournalEntry, prefix: str) -> dict[str, int]:
    """Montant de la charge (6, débit) ou du produit (7, crédit) par compte, dans l'écriture."""
    sums = {}
    for line in entry.lines:
        code = line.account.code
        if code.startswith(prefix):
            value = line.debit_cents - line.credit_cents if prefix == "6" else line.credit_cents - line.debit_cents
            sums[code] = sums.get(code, 0) + value
    return {code: v for code, v in sums.items() if v > 0}


def proposals(fy) -> list[dict]:
    posted = {ref for (ref,) in db.session.query(JournalEntry.source_ref).filter(
        JournalEntry.fiscal_year_id == fy.id, JournalEntry.source == SOURCE_INVENTORY, JournalEntry.source_ref.isnot(None))}
    found: list[Proposal] = []

    def add(kind, source, source_id, url, label, entry, prefix, start, end):
        if start is None or end is None or end <= fy.end_date or entry is None or entry.fiscal_year_id != fy.id:
            return
        for code, base in sorted(_amounts(entry, prefix).items()):
            amount, after, total = share(base, start, end, fy.end_date)
            if amount <= 0:
                continue
            key = f"{kind}:{source}:{source_id}:{code}"
            found.append(Proposal(key, kind, source, source_id, url, label, code, start.isoformat(), end.isoformat(),
                                  base, after, total, amount, key in posted))

    for p in Purchase.query.filter(Purchase.journal_entry_id.isnot(None), Purchase.is_credit_note.is_(False)):
        start, end = p.service_start, p.service_end
        if start is None:
            start, end = subscription_period(p) or (None, None)
        name = f"{p.supplier_name or (p.entity.name if p.entity else '')} {p.invoice_number or ''}".strip()
        add("prepaid_expense", "purchase", p.id, f"/purchases/{p.id}", name, p.journal_entry, "6", start, end)
    for s in Sale.query.filter(Sale.kind == "invoice", Sale.journal_entry_id.isnot(None)):
        add("deferred_income", "sale", s.id, f"/sales/{s.id}", f"{s.number} {s.entity.name if s.entity else ''}".strip(),
            db.session.get(JournalEntry, s.journal_entry_id), "7", s.service_start, s.service_end)
    lines = (JournalLine.query.join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
             .filter(JournalEntry.fiscal_year_id == fy.id, JournalLine.service_end > fy.end_date,
                     JournalLine.service_start.isnot(None), JournalEntry.source.notin_(("PURCHASE", SOURCE_SALE, SOURCE_INVENTORY))))
    for line in lines:
        code = line.account.code
        if not code.startswith(("6", "7")):
            continue
        kind = "prepaid_expense" if code.startswith("6") else "deferred_income"
        base = line.debit_cents - line.credit_cents if code.startswith("6") else line.credit_cents - line.debit_cents
        if base <= 0:
            continue
        amount, after, total = share(base, line.service_start, line.service_end, fy.end_date)
        key = f"{kind}:line:{line.id}:{code}"
        found.append(Proposal(key, kind, "line", line.id, f"/entries/{line.entry_id}",
                              f"{line.entry.reference or ''} {line.label or line.entry.description or ''}".strip(),
                              code, line.service_start.isoformat(), line.service_end.isoformat(), base, after, total,
                              amount, key in posted))
    return [asdict(p) for p in sorted(found, key=lambda p: (p.kind, p.period_start, p.key))]


def post(fy, selection, user_id=None) -> list[JournalEntry]:
    """Passe les propositions choisies (`[{key, amount_cents}]`, montant modifiable) en écritures
    d'inventaire ; une proposition déjà passée est ignorée."""
    from app.services import closing
    by_key = {p["key"]: p for p in proposals(fy)}
    entries = []
    for item in selection:
        proposal = by_key.get(item.get("key")) if isinstance(item, dict) else None
        if proposal is None:
            raise closing.ClosingError("Proposition introuvable (déjà passée ou modifiée) : rechargez la page.", 409)
        if proposal["posted"]:
            continue
        amount = item.get("amount_cents", proposal["amount_cents"])
        start, end = date.fromisoformat(proposal["period_start"]), date.fromisoformat(proposal["period_end"])
        label = f"{proposal['label']} — {start:%d/%m/%Y} au {end:%d/%m/%Y}"
        entries.append(closing.add_inventory(fy, proposal["kind"], proposal["account_code"], amount, label,
                                             user_id=user_id, source_ref=proposal["key"]))
    return entries
