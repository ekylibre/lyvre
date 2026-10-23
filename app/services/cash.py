"""Caisse (lot D.1, D22) : compte de trésorerie en espèces (53x), dans les deux modes de tenue.

- Un mouvement de caisse saisi crée une écriture au journal « CA » : 53x contre le compte choisi
  (recette ou dépense en espèces).
- **Dépôt en banque** : virement interne par le compte **581** (règle du PCG), en deux écritures —
  caisse → 581 le jour du dépôt (journal CA), 581 → banque (journal BQ) — sans effet sur les
  recettes ni les dépenses. La ligne 512 de la seconde écriture se rapproche ensuite du relevé
  bancaire ; le contrôle de clôture signale un 58x non soldé.
- Solde : cumulé depuis l'origine, hors à-nouveaux (qui ne font que reprendre les soldes).
"""
from datetime import date

from sqlalchemy import func

from app.extensions import db
from app.models import Account, BankAccount, FiscalYear, Journal, JournalEntry, JournalLine
from app.models.journal_entry import SOURCE_OPENING
from app.services import projects
from app.services.ledger import post_entry

CASH_JOURNAL = ("CA", "Caisse")
BANK_JOURNAL = ("BQ", "Banque")
TRANSFER_PREFIX = "581"
SOURCE_CASH = "CASH"


class CashError(Exception):
    def __init__(self, message, field=None, status=422):
        super().__init__(message)
        self.message, self.field, self.status = message, field, status


def ledger_balance(account_id: int, until: date | None = None) -> int:
    """Solde (débit − crédit) cumulé d'un compte, hors à-nouveaux, jusqu'à `until` inclus."""
    query = (db.session.query(func.sum(JournalLine.debit_cents - JournalLine.credit_cents))
             .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
             .filter(JournalLine.account_id == account_id, JournalEntry.source != SOURCE_OPENING))
    if until is not None:
        query = query.filter(JournalEntry.entry_date <= until)
    return int(query.scalar() or 0)


def _journal(spec):
    code, label = spec
    journal = Journal.query.filter_by(code=code).first()
    if journal is None:
        journal = Journal(code=code, label=label)
        db.session.add(journal)
        db.session.flush()
    return journal


def _fiscal_year(when: date) -> FiscalYear:
    fy = FiscalYear.query.filter(FiscalYear.start_date <= when, FiscalYear.end_date >= when).first()
    if fy is None:
        raise CashError(f"Aucun exercice ne couvre le {when:%d/%m/%Y}.", "date")
    if fy.closed:
        raise CashError(f"L'exercice {fy.label} est clôturé.", "date", 409)
    return fy


def _date(value) -> date:
    try:
        return date.fromisoformat(str(value or ""))
    except ValueError:
        raise CashError("Date invalide.", "date") from None


def _amount(value) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise CashError("Montant positif attendu.", "amount_cents")
    return value


def cash_account(ba_id: int) -> BankAccount:
    ba = db.session.get(BankAccount, ba_id)
    if ba is None or ba.kind != "cash":
        raise CashError("Caisse introuvable.", status=404)
    return ba


def movements(ba: BankAccount, start: date | None = None, end: date | None = None) -> dict:
    """Lignes du compte de caisse (période facultative), avec solde courant."""
    query = (JournalLine.query.join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
             .filter(JournalLine.account_id == ba.account_id, JournalEntry.source != SOURCE_OPENING))
    opening = 0
    if start is not None:
        opening = ledger_balance(ba.account_id, date.fromordinal(start.toordinal() - 1))
        query = query.filter(JournalEntry.entry_date >= start)
    if end is not None:
        query = query.filter(JournalEntry.entry_date <= end)
    rows, running = [], opening
    for line in query.order_by(JournalEntry.entry_date, JournalEntry.id, JournalLine.id):
        amount = line.debit_cents - line.credit_cents
        running += amount
        others = [o.account.code for o in line.entry.lines if o.id != line.id]
        rows.append({"line_id": line.id, "entry_id": line.entry_id, "date": line.entry.entry_date.isoformat(),
                     "reference": line.entry.reference, "label": line.label or line.entry.description or "",
                     "counterpart": ", ".join(others), "amount_cents": amount, "balance_cents": running,
                     "deposit": any(c.startswith(TRANSFER_PREFIX) for c in others)})
    return {"opening_cents": opening, "closing_cents": running, "rows": rows}


def record(ba: BankAccount, data: dict):
    """Mouvement de caisse : `{date, label, direction (in|out), amount_cents, account_id, project_id?}`."""
    when = _date(data.get("date"))
    amount = _amount(data.get("amount_cents"))
    direction = data.get("direction")
    if direction not in ("in", "out"):
        raise CashError("Entrée ou sortie ?", "direction")
    label = (data.get("label") or "").strip()[:300]
    if not label:
        raise CashError("Libellé obligatoire.", "label")
    counterpart = db.session.get(Account, data.get("account_id")) if isinstance(data.get("account_id"), int) else None
    if counterpart is None or counterpart.is_header:
        raise CashError("Compte de contrepartie obligatoire (compte utilisable).", "account_id")
    if counterpart.id == ba.account_id or counterpart.code.startswith("5"):
        raise CashError("Pour un mouvement entre caisse et banque, utilisez « Dépôt en banque ».", "account_id")
    try:
        project = projects.resolve(data.get("project_id"))
    except ValueError as exc:
        raise CashError(str(exc), "project_id") from None
    fy = _fiscal_year(when)
    cash_line = {"account_id": ba.account_id, "label": label, "debit_cents": amount if direction == "in" else 0,
                 "credit_cents": amount if direction == "out" else 0}
    other = {"account_id": counterpart.id, "label": label, "debit_cents": cash_line["credit_cents"],
             "credit_cents": cash_line["debit_cents"], "project_id": project.id if project else None}
    if direction == "out" and ledger_balance(ba.account_id, when) - amount < 0:
        raise CashError("La caisse ne peut pas devenir négative à cette date.", "amount_cents", 409)
    return post_entry(fy.id, _journal(CASH_JOURNAL).id, when, label, [cash_line, other], source=SOURCE_CASH)


def transfer_account() -> Account:
    account = (Account.query.filter(Account.is_header.is_(False), Account.code == TRANSFER_PREFIX).first()
               or Account.query.filter(Account.is_header.is_(False), Account.code.like(f"{TRANSFER_PREFIX}%"))
               .order_by(Account.code).first())
    if account is None:
        raise CashError("Compte 581 (virements internes) absent du plan comptable.", status=409)
    return account


def deposit(ba: BankAccount, data: dict) -> tuple[JournalEntry, JournalEntry]:
    """Dépôt d'espèces en banque : `{date, amount_cents, bank_account_id, label?}` (deux écritures par 581)."""
    when = _date(data.get("date"))
    amount = _amount(data.get("amount_cents"))
    bank = db.session.get(BankAccount, data.get("bank_account_id")) if isinstance(data.get("bank_account_id"), int) else None
    if bank is None or bank.kind != "bank":
        raise CashError("Compte bancaire de destination obligatoire.", "bank_account_id")
    if ledger_balance(ba.account_id, when) - amount < 0:
        raise CashError("Montant supérieur au solde de la caisse à cette date.", "amount_cents", 409)
    fy = _fiscal_year(when)
    label = (data.get("label") or "").strip()[:300] or f"Dépôt d'espèces — {bank.label}"
    via = transfer_account()
    out = post_entry(fy.id, _journal(CASH_JOURNAL).id, when, label, [
        {"account_id": via.id, "label": label, "debit_cents": amount},
        {"account_id": ba.account_id, "label": label, "credit_cents": amount}], source=SOURCE_CASH, commit=False)
    into = post_entry(fy.id, _journal(BANK_JOURNAL).id, when, label, [
        {"account_id": bank.account_id, "label": label, "debit_cents": amount},
        {"account_id": via.id, "label": label, "credit_cents": amount}], source=SOURCE_CASH, commit=False)
    db.session.commit()
    return out, into
