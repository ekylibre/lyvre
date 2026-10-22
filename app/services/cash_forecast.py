"""Prévisionnel de trésorerie (lot C.4, D14) : 12 mois glissants à partir du mois en cours,
calculé à la demande (rien n'est stocké hors saisies manuelles).

- **Solde de départ** : par compte bancaire, solde comptable du compte (toutes écritures datées
  jusqu'à aujourd'hui, hors à-nouveaux qui ne font que reprendre les soldes antérieurs) plus les
  transactions bancaires encore non comptabilisées ; comptes de caisse (53) : solde comptable.
- **Mouvements attendus par mois** :
  - factures d'achat non réglées (montant à payer, à l'échéance ; un avoir est un encaissement) ;
  - factures clients non réglées (reste dû, à l'échéance) ;
  - budget général restant : montants prévus du mois (charges et produits, hors dotations et
    reprises 68 / 78 sans effet sur la trésorerie) ; pour le mois en cours, prévu moins réalisé ;
  - saisies manuelles (`cash_forecast_items`), répétées chaque mois jusqu'à une date.
  Une échéance dépassée est rattachée au mois en cours.
- **Alerte** : premier mois dont le solde de fin est négatif.
"""
from datetime import date

from sqlalchemy import func

from app.extensions import db
from app.models import (
    Account, BankAccount, BankTransaction, CashForecastItem, CustomerInvoice, FiscalYear, JournalEntry, JournalLine,
    Purchase,
)
from app.models.journal_entry import SOURCE_OPENING
from app.services import budget

MONTHS = 12
CASH_PREFIXES = ("53",)
NON_CASH_PREFIXES = ("68", "78")
CLOSED_PURCHASE_STATUSES = ("paid", "archived", "rejected", "discarded")
CATEGORIES = {
    "customers": "Factures clients", "purchases": "Factures d'achat", "budget": "Budget restant", "manual": "Saisies manuelles",
}


class ForecastError(Exception):
    def __init__(self, message, field=None):
        super().__init__(message)
        self.message, self.field = message, field


def _month(d: date) -> date:
    return date(d.year, d.month, 1)


def _add_months(d: date, n: int) -> date:
    index = d.year * 12 + d.month - 1 + n
    return date(index // 12, index % 12 + 1, 1)


def _gl_balance(account_id, today) -> int:
    value = (db.session.query(func.sum(JournalLine.debit_cents - JournalLine.credit_cents))
             .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
             .filter(JournalLine.account_id == account_id, JournalEntry.entry_date <= today,
                     JournalEntry.source != SOURCE_OPENING).scalar())
    return int(value or 0)


def balances(today: date) -> list[dict]:
    out = []
    bank_gl = set()
    for ba in BankAccount.query.order_by(BankAccount.label):
        bank_gl.add(ba.account_id)
        unbooked = (db.session.query(func.sum(BankTransaction.amount_cents))
                    .filter(BankTransaction.bank_account_id == ba.id, BankTransaction.journal_line_id.is_(None),
                            BankTransaction.reconciled.is_(False), BankTransaction.is_reversed.is_(False),
                            BankTransaction.transaction_date <= today).scalar())
        gl = _gl_balance(ba.account_id, today)
        out.append({"label": ba.label, "account": ba.account.code, "ledger_cents": gl, "unbooked_cents": int(unbooked or 0),
                    "balance_cents": gl + int(unbooked or 0)})
    for account in Account.query.filter(db.or_(*[Account.code.like(f"{p}%") for p in CASH_PREFIXES]),
                                        Account.is_header.is_(False)).order_by(Account.code):
        if account.id in bank_gl:
            continue
        gl = _gl_balance(account.id, today)
        if gl:
            out.append({"label": account.label, "account": account.code, "ledger_cents": gl, "unbooked_cents": 0,
                        "balance_cents": gl})
    return out


def _bucket(when: date | None, first: date, last: date) -> date | None:
    """Mois de rattachement (échéance dépassée : mois en cours ; au-delà de l'horizon : ignorée)."""
    month = max(_month(when), first) if when else first
    return month if month <= last else None


def _purchases(first, last):
    rows = (Purchase.query.filter(Purchase.is_hidden.is_(False), Purchase.payment_date.is_(None),
                                  db.or_(Purchase.qonto_status.is_(None), Purchase.qonto_status.notin_(CLOSED_PURCHASE_STATUSES)))
            .all())
    for p in rows:
        if any(pay.journal_entry_id for pay in p.payments):
            continue
        month = _bucket(p.due_date or p.issue_date, first, last)
        amount = p.payable_cents if p.payable_cents is not None else p.total_cents
        if month and amount:
            name = p.entity.name if p.entity else (p.supplier_name or "Fournisseur")
            yield month, (amount if p.is_credit_note else -amount), f"{name} — {p.invoice_number or 'sans numéro'}", \
                f"/purchases/{p.id}"


def _customers(first, last):
    for inv in CustomerInvoice.query.filter(CustomerInvoice.state == "posted", CustomerInvoice.amount_residual_cents > 0):
        month = _bucket(inv.invoice_date_due or inv.invoice_date, first, last)
        if month:
            yield month, inv.amount_residual_cents, f"{inv.partner_name or 'Client'} — {inv.name}", "/customer-invoices/"


def _manual(first, last):
    for item in CashForecastItem.query.order_by(CashForecastItem.date):
        month = _month(item.date)
        until = _month(item.repeat_monthly_until) if item.repeat_monthly_until else month
        while month <= min(until, last):
            if month >= first:
                yield month, item.amount_cents, item.label, None
            month = _add_months(month, 1)


def _budget(first, last, today):
    """Prévu du budget général par mois (sens trésorerie), hors 68 / 78 ; mois en cours : reste à réaliser."""
    grids = {}
    month = first
    while month <= last:
        fy = FiscalYear.query.filter(FiscalYear.start_date <= month, FiscalYear.end_date >= month).first()
        if fy is not None:
            if fy.id not in grids:
                grids[fy.id] = (budget.month_starts(fy), budget.grid(fy, None))
            starts, rows = grids[fy.id]
            index = next((i for i, s in enumerate(starts) if s == month), None)
            if index is not None:
                for kind_, sign in (("expense", -1), ("income", 1)):
                    planned = {r["code"]: r["months"][index] for r in rows
                               if r["kind"] == kind_ and not r["code"].startswith(NON_CASH_PREFIXES)}
                    total = sum(planned.values())
                    if month == first and total:
                        done = budget.actuals(fy, None, month, today)
                        realised = sum(v for code, v in done.items()
                                       if any(code.startswith(c) for c in planned))
                        total = max(total - realised, 0)
                    if total:
                        label = "Charges prévues au budget" if kind_ == "expense" else "Produits prévus au budget"
                        yield month, sign * total, label, f"/budget/tracking?fiscal_year_id={fy.id}"
        month = _add_months(month, 1)


def forecast(today: date | None = None) -> dict:
    today = today or date.today()
    first = _month(today)
    last = _add_months(first, MONTHS - 1)
    accounts = balances(today)
    opening = sum(a["balance_cents"] for a in accounts)
    months = {(_add_months(first, i)): {"in": {k: 0 for k in CATEGORIES}, "out": {k: 0 for k in CATEGORIES}, "details": []}
              for i in range(MONTHS)}
    sources = (("purchases", _purchases(first, last)), ("customers", _customers(first, last)),
               ("budget", _budget(first, last, today)), ("manual", _manual(first, last)))
    for category, rows in sources:
        for month, amount, label, url in rows:
            slot = months[month]
            slot["in" if amount > 0 else "out"][category] += abs(amount)
            slot["details"].append({"category": category, "label": label, "amount_cents": amount, "url": url})
    out, running, first_negative = [], opening, None
    for month, slot in months.items():
        inflow, outflow = sum(slot["in"].values()), sum(slot["out"].values())
        start = running
        running += inflow - outflow
        if running < 0 and first_negative is None:
            first_negative = {"month": month.isoformat(), "closing_cents": running}
        out.append({"month": month.isoformat(), "label": f"{budget.SHORT_MONTHS[month.month - 1]} {month:%y}",
                    "opening_cents": start, "inflows": slot["in"], "outflows": slot["out"], "inflow_cents": inflow,
                    "outflow_cents": outflow, "closing_cents": running,
                    "details": sorted(slot["details"], key=lambda d: (d["category"], -abs(d["amount_cents"])))})
    return {"today": today.isoformat(), "accounts": accounts, "opening_cents": opening, "months": out,
            "categories": CATEGORIES, "first_negative": first_negative}


# ------------------------------------------------------------------ saisies manuelles


def _date(value, field, label):
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise ForecastError(f"{label} : date invalide.", field) from None


def save_item(item: CashForecastItem | None, data: dict) -> CashForecastItem:
    label = (data.get("label") or "").strip()[:200]
    if not label:
        raise ForecastError("Libellé obligatoire.", "label")
    when = _date(data.get("date"), "date", "Date")
    if when is None:
        raise ForecastError("Date obligatoire.", "date")
    amount = data.get("amount_cents")
    if not isinstance(amount, int) or isinstance(amount, bool) or amount == 0:
        raise ForecastError("Montant non nul attendu (positif : encaissement, négatif : décaissement).", "amount_cents")
    until = _date(data.get("repeat_monthly_until"), "repeat_monthly_until", "Répéter jusqu'au")
    if until and until < when:
        raise ForecastError("La fin de répétition doit suivre la date.", "repeat_monthly_until")
    bank = data.get("bank_account_id")
    if bank not in (None, "") and db.session.get(BankAccount, int(bank)) is None:
        raise ForecastError("Compte bancaire inconnu.", "bank_account_id")
    if item is None:
        item = CashForecastItem()
        db.session.add(item)
    item.label, item.date, item.amount_cents, item.repeat_monthly_until = label, when, amount, until
    item.bank_account_id = int(bank) if bank not in (None, "") else None
    db.session.commit()
    return item


def item_payload(item: CashForecastItem) -> dict:
    return {"id": item.id, "date": item.date.isoformat(), "label": item.label, "amount_cents": item.amount_cents,
            "bank_account_id": item.bank_account_id, "bank_account": item.bank_account.label if item.bank_account else None,
            "repeat_monthly_until": item.repeat_monthly_until.isoformat() if item.repeat_monthly_until else None}
