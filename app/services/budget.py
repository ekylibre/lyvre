"""Budget (lot C.2, D13) : montants prévus par compte de charge ou de produit, sur un exercice,
global ou par projet.

- Une **ligne de grille** = un compte (classe 6 ou 7, regroupement admis : 60, 64…) saisi soit en
  **annuel** (une ligne `month` NULL, répartie par douzièmes à l'affichage), soit **par mois**
  (une ligne par rang de mois dans l'exercice, 1 = premier mois).
- La grille d'un périmètre (exercice, projet ou « sans projet ») s'enregistre d'un bloc
  (`save` remplace le périmètre). Deux comptes dont l'un est préfixe de l'autre ne peuvent pas
  coexister dans un périmètre (le réalisé serait compté deux fois).
- `copy_rows` prépare une grille à partir de l'exercice précédent : son budget, ou son réalisé
  (regroupé au compte à 3 chiffres quand il existe), sans rien enregistrer.
"""
from datetime import date

from sqlalchemy import func

from app.extensions import db
from app.models import Account, BudgetLine, FiscalYear, JournalEntry, JournalLine, Project

CLASSES = ("6", "7")
SHORT_MONTHS = ("janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc.")
ACTUAL_LEVEL = 3


class BudgetError(Exception):
    def __init__(self, message, field=None):
        super().__init__(message)
        self.message, self.field = message, field


def month_starts(fy) -> list[date]:
    out, cur = [], date(fy.start_date.year, fy.start_date.month, 1)
    while cur <= fy.end_date:
        out.append(cur)
        cur = date(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)
    return out


def months(fy) -> list[dict]:
    return [{"index": i + 1, "label": f"{SHORT_MONTHS[d.month - 1]} {d:%y}", "start": d.isoformat()}
            for i, d in enumerate(month_starts(fy))]


def spread(annual: int, count: int) -> list[int]:
    """Douzièmes (ou n-ièmes) entiers dont la somme vaut le montant annuel."""
    base, rest = divmod(annual, count)
    return [base + (1 if i < rest else 0) for i in range(count)]


def kind(code: str) -> str:
    return "expense" if code.startswith("6") else "income"


def previous_fiscal_year(fy):
    return FiscalYear.query.filter(FiscalYear.end_date < fy.start_date).order_by(FiscalYear.end_date.desc()).first()


def _scope(fy, project):
    query = BudgetLine.query.filter_by(fiscal_year_id=fy.id)
    return query.filter(BudgetLine.project_id == project.id) if project else query.filter(BudgetLine.project_id.is_(None))


def _row(account, count, annual=None, monthly=None) -> dict:
    values = spread(annual, count) if annual is not None else monthly
    return {"account_id": account.id, "code": account.code, "label": account.label, "kind": kind(account.code),
            "mode": "annual" if annual is not None else "monthly", "annual_cents": annual,
            "months": values, "total_cents": sum(values)}


def grid(fy, project=None) -> list[dict]:
    count = len(month_starts(fy))
    by_account: dict[int, dict] = {}
    for line in _scope(fy, project).all():
        entry = by_account.setdefault(line.account_id, {"account": line.account, "annual": None, "months": [0] * count})
        if line.month is None:
            entry["annual"] = line.amount_cents
        elif 1 <= line.month <= count:
            entry["months"][line.month - 1] = line.amount_cents
    rows = [_row(e["account"], count, annual=e["annual"]) if e["annual"] is not None
            else _row(e["account"], count, monthly=e["months"]) for e in by_account.values()]
    return sorted(rows, key=lambda r: (r["kind"] != "expense", r["code"]))


def totals(rows) -> dict:
    expense = sum(r["total_cents"] for r in rows if r["kind"] == "expense")
    income = sum(r["total_cents"] for r in rows if r["kind"] == "income")
    return {"expense_cents": expense, "income_cents": income, "result_cents": income - expense}


def _amount(value, field):
    if value is None:
        return 0
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise BudgetError("Montant positif ou nul attendu (en centimes).", field)
    return value


def save(fy, project, rows) -> list[dict]:
    """Remplace le budget du périmètre (exercice, projet) par `rows` :
    `[{account_id, annual_cents}]` ou `[{account_id, months: [n montants]}]`."""
    if not isinstance(rows, list):
        raise BudgetError("Lignes de budget invalides.")
    count = len(month_starts(fy))
    cleaned, seen = [], {}
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise BudgetError("Ligne de budget invalide.", f"rows[{i}]")
        account = db.session.get(Account, row.get("account_id")) if isinstance(row.get("account_id"), int) else None
        if account is None:
            raise BudgetError("Compte obligatoire.", f"rows[{i}].account_id")
        if not account.code.startswith(CLASSES):
            raise BudgetError(f"Compte {account.code} : compte de charge (6) ou de produit (7) attendu.",
                              f"rows[{i}].account_id")
        for code, j in seen.items():
            if code == account.code:
                raise BudgetError(f"Compte {code} présent deux fois.", f"rows[{i}].account_id")
            if account.code.startswith(code) or code.startswith(account.code):
                raise BudgetError(f"Comptes {code} et {account.code} : l'un regroupe l'autre, le réalisé serait "
                                  "compté deux fois.", f"rows[{i}].account_id")
        seen[account.code] = i
        if row.get("months") is not None:
            values = row["months"]
            if not isinstance(values, list) or len(values) != count:
                raise BudgetError(f"{count} montants mensuels attendus.", f"rows[{i}].months")
            values = [_amount(v, f"rows[{i}].months") for v in values]
            if any(values):
                cleaned.append((account, None, values))
        else:
            annual = _amount(row.get("annual_cents"), f"rows[{i}].annual_cents")
            if annual:
                cleaned.append((account, annual, None))
    _scope(fy, project).delete(synchronize_session=False)
    for account, annual, values in cleaned:
        base = {"fiscal_year_id": fy.id, "account_id": account.id, "project_id": project.id if project else None}
        if annual is not None:
            db.session.add(BudgetLine(**base, month=None, amount_cents=annual))
        else:
            db.session.add_all(BudgetLine(**base, month=m + 1, amount_cents=v) for m, v in enumerate(values) if v)
    db.session.commit()
    return grid(fy, project)


def _actual_account(code, cache):
    """Compte de regroupement à 3 chiffres s'il existe dans le plan, sinon le compte lui-même."""
    prefix = code[:ACTUAL_LEVEL]
    if prefix not in cache:
        cache[prefix] = Account.query.filter_by(code=prefix).first()
    return cache[prefix] or Account.query.filter_by(code=code).first()


def copy_rows(fy, project, source) -> list[dict]:
    """Grille proposée d'après l'exercice précédent (`source` : `budget` ou `actual`), non enregistrée."""
    previous = previous_fiscal_year(fy)
    if previous is None:
        raise BudgetError("Aucun exercice précédent.")
    count, prev_count = len(month_starts(fy)), len(month_starts(previous))
    if source == "budget":
        rows = []
        for row in grid(previous, project):
            account = db.session.get(Account, row["account_id"])
            if row["mode"] == "monthly" and prev_count == count:
                rows.append(_row(account, count, monthly=row["months"]))
            else:
                rows.append(_row(account, count, annual=row["total_cents"]))
        return rows
    if source != "actual":
        raise BudgetError("Source inconnue (budget ou réalisé).")
    starts = month_starts(previous)
    query = (db.session.query(Account.code, JournalEntry.entry_date,
                              func.sum(JournalLine.debit_cents - JournalLine.credit_cents))
             .join(JournalLine, JournalLine.account_id == Account.id)
             .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
             .filter(JournalEntry.fiscal_year_id == previous.id,
                     db.or_(*[Account.code.like(f"{c}%") for c in CLASSES])))
    if project is not None:
        query = query.filter(JournalLine.project_id == project.id)
    cache, amounts = {}, {}
    for code, entry_date, balance in query.group_by(Account.code, JournalEntry.entry_date):
        account = _actual_account(code, cache)
        index = max(i for i, s in enumerate(starts) if s <= entry_date)
        value = int(balance or 0) if code.startswith("6") else -int(balance or 0)
        amounts.setdefault(account, [0] * prev_count)[index] += value
    rows = []
    for account, values in amounts.items():
        values = [max(v, 0) for v in values]
        if not any(values):
            continue
        rows.append(_row(account, count, monthly=values) if prev_count == count
                    else _row(account, count, annual=sum(values)))
    return sorted(rows, key=lambda r: (r["kind"] != "expense", r["code"]))


def account_options():
    """Comptes 6 et 7 proposés à la saisie du budget (regroupements compris)."""
    accounts = (Account.query.filter(db.or_(*[Account.code.like(f"{c}%") for c in CLASSES]))
                .order_by(Account.code).all())
    return [{"value": str(a.id), "label": f"{a.code} — {a.label}", "code": a.code} for a in accounts]


def project_or_error(value):
    if value in (None, "", "none"):
        return None
    try:
        project = db.session.get(Project, int(value))
    except (TypeError, ValueError):
        project = None
    if project is None:
        raise BudgetError("Projet inconnu.", "project_id")
    return project
