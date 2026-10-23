"""États de la comptabilité simplifiée (lot D.4) et verrouillage d'exercice.

- **Compte de résultat simplifié** : recettes et dépenses par catégorie, exercice N et N-1 (les
  comptes 6 / 7 sans catégorie apparaissent sous leur numéro).
- **Situation de trésorerie** : solde de chaque compte bancaire et caisse au début et à la fin de
  l'exercice, **cumulé depuis l'origine** (hors à-nouveaux : il n'y en a pas en mode simple).
- **Verrouillage** : en mode simple, un exercice se verrouille sans assistant ni FEC (`status`
  `closed`) et se déverrouille par l'administrateur tant que l'instance reste en mode simple.
"""
from datetime import datetime, timedelta

from sqlalchemy import func

from app.extensions import db
from app.models import Account, BankAccount, FiscalYear, JournalEntry, JournalLine
from app.models.fiscal_year import FY_CLOSED, FY_OPEN
from app.services import simple_categories
from app.services.cash import ledger_balance


class SimpleReportError(Exception):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.message, self.status = message, status


def previous_year(fy):
    return FiscalYear.query.filter(FiscalYear.end_date < fy.start_date).order_by(FiscalYear.end_date.desc()).first()


def _amounts(fy) -> dict[int, int]:
    """Montant par compte (sens naturel : produits au crédit, charges au débit), comptes 6 et 7."""
    if fy is None:
        return {}
    rows = (db.session.query(JournalLine.account_id, Account.code,
                             func.sum(JournalLine.credit_cents - JournalLine.debit_cents))
            .join(Account, Account.id == JournalLine.account_id)
            .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
            .filter(JournalEntry.fiscal_year_id == fy.id, db.or_(Account.code.like("6%"), Account.code.like("7%")))
            .group_by(JournalLine.account_id, Account.code))
    return {account_id: (int(total or 0) if code.startswith("7") else -int(total or 0)) for account_id, code, total in rows}


def income_statement(fy) -> dict:
    prev = previous_year(fy)
    current, before = _amounts(fy), _amounts(prev)
    categories = simple_categories.listing()
    by_account = {c.account_id: c for c in categories}
    rows = {}
    for account_id in set(current) | set(before):
        category = by_account.get(account_id)
        account = db.session.get(Account, account_id)
        key = f"c{category.id}" if category else f"a{account_id}"
        row = rows.setdefault(key, {
            "label": category.label if category else f"{account.code} {account.label}",
            "kind": category.kind if category else ("income" if account.code.startswith("7") else "expense"),
            "position": category.position if category else 10_000 + int(account.code.ljust(8, "0")[:8]),
            "amount_cents": 0, "previous_cents": 0})
        row["amount_cents"] += current.get(account_id, 0)
        row["previous_cents"] += before.get(account_id, 0)
    ordered = sorted(rows.values(), key=lambda r: (r["kind"] != "income", r["position"]))
    totals = {}
    for kind in ("income", "expense"):
        totals[kind] = {key: sum(r[key] for r in ordered if r["kind"] == kind) for key in ("amount_cents", "previous_cents")}
    result = {key: totals["income"][key] - totals["expense"][key] for key in ("amount_cents", "previous_cents")}
    return {"fiscal_year": fy.label, "previous_year": prev.label if prev else None,
            "rows": [{k: v for k, v in r.items() if k != "position"} for r in ordered], "totals": totals, "result": result}


def treasury_situation(fy) -> dict:
    day_before = fy.start_date - timedelta(days=1)
    rows = []
    for ba in BankAccount.query.order_by(BankAccount.kind, BankAccount.label):
        start, end = ledger_balance(ba.account_id, day_before), ledger_balance(ba.account_id, fy.end_date)
        rows.append({"label": ba.label, "kind": ba.kind, "account": ba.account.code, "start_cents": start,
                     "end_cents": end, "change_cents": end - start})
    total = {key: sum(r[key] for r in rows) for key in ("start_cents", "end_cents", "change_cents")}
    return {"fiscal_year": fy.label, "start_date": fy.start_date.isoformat(), "end_date": fy.end_date.isoformat(),
            "rows": rows, "total": total, "result_cents": income_statement(fy)["result"]["amount_cents"]}


def lock(fy, locked: bool, user_id=None):
    """Verrouille (ou déverrouille) un exercice en mode simple."""
    if locked:
        if fy.status != FY_OPEN:
            raise SimpleReportError("Exercice déjà verrouillé.")
        fy.status, fy.closed_at, fy.closed_by_user_id = FY_CLOSED, datetime.utcnow(), user_id
    else:
        if fy.status == FY_OPEN:
            raise SimpleReportError("Exercice déjà ouvert.")
        if fy.fec_sha256:
            raise SimpleReportError("Exercice clôturé définitivement en partie double (FEC figé) : irréversible.")
        fy.status, fy.closed_at, fy.closed_by_user_id = FY_OPEN, None, None
    db.session.commit()
    return fy
