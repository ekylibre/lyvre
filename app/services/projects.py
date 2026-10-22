"""Projets / activités (lot C.1, axe analytique unique OA11).

Un projet se porte sur une ligne d'écriture (`journal_lines.project_id`), une ligne de facture
d'achat (reprise sur la ligne de charge à la comptabilisation) ou une règle de catégorisation
(reprise sur la ligne de charge / produit de l'écriture générée). La **ventilation** d'une ligne
sur plusieurs projets la découpe en lignes de même compte et même sens : l'écriture reste
équilibrée, la balance et le FEC (mêmes comptes, mêmes totaux) inchangés.
"""
from datetime import date

from sqlalchemy import case, func

from app.extensions import db
from app.models import Account, BankTransaction, BudgetLine, FiscalYear, JournalEntry, JournalLine, Project, PurchaseLine, Rule
from app.models.journal_entry import MANAGED_SOURCES


class ProjectError(Exception):
    def __init__(self, message, status=422, field=None):
        super().__init__(message)
        self.message, self.status, self.field = message, status, field


def resolve(value):
    """`project_id` saisi → Project (None si vide) ; ValueError si inconnu."""
    if value in (None, "", 0, "0"):
        return None
    try:
        project = db.session.get(Project, int(value))
    except (TypeError, ValueError):
        project = None
    if project is None:
        raise ValueError("Projet inconnu.")
    return project


def totals(fiscal_year_id=None) -> dict[int, dict]:
    """Charges (6), produits (7) et résultat par projet, tous exercices ou un seul."""
    expense = func.sum(case((Account.code.like("6%"), JournalLine.debit_cents - JournalLine.credit_cents), else_=0))
    income = func.sum(case((Account.code.like("7%"), JournalLine.credit_cents - JournalLine.debit_cents), else_=0))
    query = (db.session.query(JournalLine.project_id, expense, income, func.count(JournalLine.id))
             .join(Account, Account.id == JournalLine.account_id)
             .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
             .filter(JournalLine.project_id.isnot(None)))
    if fiscal_year_id:
        query = query.filter(JournalEntry.fiscal_year_id == fiscal_year_id)
    out = {}
    for project_id, exp, inc, count in query.group_by(JournalLine.project_id):
        exp, inc = int(exp or 0), int(inc or 0)
        out[project_id] = {"expense_cents": exp, "income_cents": inc, "result_cents": inc - exp, "lines": count}
    return out


def payload(project: Project, figures: dict | None = None) -> dict:
    figures = figures or {"expense_cents": 0, "income_cents": 0, "result_cents": 0, "lines": 0}
    return {"id": project.id, "name": project.name, "description": project.description or "",
            "start_date": project.start_date.isoformat() if project.start_date else None,
            "end_date": project.end_date.isoformat() if project.end_date else None,
            "manager": project.manager or "", "archived": project.archived, **figures}


def options(include_archived_ids=()) -> list[dict]:
    """Choix d'un projet : projets actifs, plus les archivés déjà utilisés par la saisie."""
    rows = Project.query.filter(db.or_(Project.archived.is_(False), Project.id.in_(list(include_archived_ids) or [0])))
    return [{"value": str(p.id), "label": p.name} for p in rows.order_by(Project.name)]


def _date(value, label, field):
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise ProjectError(f"{label} : date invalide.", field=field) from None


def save(project: Project | None, data: dict) -> Project:
    name = (data.get("name") or "").strip()[:120]
    if not name:
        raise ProjectError("Nom du projet obligatoire.", field="name")
    clash = Project.query.filter(func.lower(Project.name) == name.lower())
    if project is not None:
        clash = clash.filter(Project.id != project.id)
    if clash.first():
        raise ProjectError(f"Le projet « {name} » existe déjà.", field="name")
    start = _date(data.get("start_date"), "Début", "start_date")
    end = _date(data.get("end_date"), "Fin", "end_date")
    if start and end and end < start:
        raise ProjectError("La fin doit suivre le début.", field="end_date")
    if project is None:
        project = Project()
        db.session.add(project)
    project.name, project.start_date, project.end_date = name, start, end
    project.description = (data.get("description") or "").strip() or None
    project.manager = (data.get("manager") or "").strip()[:120] or None
    project.archived = bool(data.get("archived"))
    db.session.commit()
    return project


def delete(project: Project):
    used = (JournalLine.query.filter_by(project_id=project.id).count()
            + PurchaseLine.query.filter_by(project_id=project.id).count()
            + Rule.query.filter_by(project_id=project.id).count()
            + BudgetLine.query.filter_by(project_id=project.id).count())
    if used:
        raise ProjectError(f"Projet utilisé ({used} ligne(s), règle(s) ou montant(s) de budget) : archivez-le plutôt.",
                           status=409)
    db.session.delete(project)
    db.session.commit()


def split_line(line: JournalLine, parts) -> list[JournalLine]:
    """Ventile une ligne : `parts` = [{project_id, amount_cents}], total = montant de la ligne.
    La ligne d'origine prend la première part ; les suivantes sont de nouvelles lignes."""
    entry = line.entry
    if entry.fiscal_year.closed:
        raise ProjectError("Exercice clôturé : ventilation impossible.", status=409)
    if entry.source in MANAGED_SOURCES:
        raise ProjectError("Écriture gérée par l'assistant de clôture.", status=409)
    if BankTransaction.query.filter_by(journal_line_id=line.id).first() is not None:
        raise ProjectError("Ligne rapprochée d'une transaction bancaire : ventilez la ligne de charge ou "
                           "de produit.", status=409)
    if not isinstance(parts, list) or len(parts) < 2:
        raise ProjectError("Au moins deux parts.")
    amount = line.debit_cents or line.credit_cents
    cleaned = []
    for i, part in enumerate(parts):
        cents = part.get("amount_cents") if isinstance(part, dict) else None
        if not isinstance(cents, int) or isinstance(cents, bool) or cents <= 0:
            raise ProjectError("Montant positif attendu pour chaque part.", field=f"parts[{i}].amount_cents")
        try:
            project = resolve(part.get("project_id"))
        except ValueError as exc:
            raise ProjectError(str(exc), field=f"parts[{i}].project_id") from None
        cleaned.append((project, cents))
    if sum(cents for _p, cents in cleaned) != amount:
        raise ProjectError(f"Les parts doivent totaliser {amount / 100:.2f} € (montant de la ligne).")
    side = "debit_cents" if line.debit_cents else "credit_cents"
    created = []
    (first_project, first_cents), rest = cleaned[0], cleaned[1:]
    line.project_id = first_project.id if first_project else None
    setattr(line, side, first_cents)
    for project, cents in rest:
        new = JournalLine(entry_id=entry.id, account_id=line.account_id, label=line.label,
                          debit_cents=0, credit_cents=0, project_id=project.id if project else None)
        setattr(new, side, cents)
        db.session.add(new)
        created.append(new)
    db.session.commit()
    return [line, *created]


def set_line_project(line: JournalLine, project_id):
    entry = line.entry
    if entry.fiscal_year.closed:
        raise ProjectError("Exercice clôturé : affectation impossible.", status=409)
    if entry.source in MANAGED_SOURCES:
        raise ProjectError("Écriture gérée par l'assistant de clôture.", status=409)
    try:
        project = resolve(project_id)
    except ValueError as exc:
        raise ProjectError(str(exc), field="project_id") from None
    line.project_id = project.id if project else None
    db.session.commit()


def fiscal_year_or_none(value):
    try:
        return db.session.get(FiscalYear, int(value)) if value else None
    except (TypeError, ValueError):
        return None


def statement(project: Project, start: date, end: date) -> dict:
    """Compte de résultat du projet sur [start, end] (pour un financeur) : charges et produits par
    compte, puis le détail des lignes avec leur pièce (facture d'achat jointe quand il y en a)."""
    from app.models import Purchase
    lines = (JournalLine.query.join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
             .join(Account, Account.id == JournalLine.account_id)
             .filter(JournalLine.project_id == project.id, JournalEntry.entry_date.between(start, end),
                     db.or_(Account.code.like("6%"), Account.code.like("7%")))
             .order_by(JournalEntry.entry_date, JournalEntry.id, JournalLine.id).all())
    purchases = {p.journal_entry_id: p for p in Purchase.query.filter(
        Purchase.journal_entry_id.in_({l.entry_id for l in lines} or {0}), Purchase.attachment_path.isnot(None))}
    by_account: dict[str, dict] = {}
    details = []
    for line in lines:
        code = line.account.code
        amount = line.debit_cents - line.credit_cents if code.startswith("6") else line.credit_cents - line.debit_cents
        bucket = by_account.setdefault(code, {"code": code, "label": line.account.label,
                                              "kind": "expense" if code.startswith("6") else "income", "amount_cents": 0})
        bucket["amount_cents"] += amount
        purchase = purchases.get(line.entry_id)
        details.append({"date": line.entry.entry_date.isoformat(), "reference": line.entry.reference,
                        "entry_url": f"/entries/{line.entry_id}", "label": line.label or line.entry.description or "",
                        "account": code, "kind": bucket["kind"], "amount_cents": amount,
                        "document_url": f"/purchases/{purchase.id}/attachment" if purchase else None})
    accounts = sorted(by_account.values(), key=lambda a: (a["kind"] != "expense", a["code"]))
    expense = sum(a["amount_cents"] for a in accounts if a["kind"] == "expense")
    income = sum(a["amount_cents"] for a in accounts if a["kind"] == "income")
    return {"project": payload(project), "start": start.isoformat(), "end": end.isoformat(), "accounts": accounts,
            "lines": details, "totals": {"expense_cents": expense, "income_cents": income, "result_cents": income - expense}}


def default_period(project: Project) -> tuple[date, date]:
    """Dates du projet, sinon l'exercice en cours (ou l'année civile)."""
    today = date.today()
    fy = FiscalYear.query.filter(FiscalYear.start_date <= today, FiscalYear.end_date >= today).first()
    start = project.start_date or (fy.start_date if fy else date(today.year, 1, 1))
    end = project.end_date or (fy.end_date if fy else date(today.year, 12, 31))
    return start, end
