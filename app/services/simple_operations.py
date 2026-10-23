"""Recettes et dépenses de la comptabilité simplifiée (lot D.3, D20).

Une opération saisie (date, libellé, montant, catégorie, compte bancaire ou caisse, tiers, projet)
**génère une écriture en partie double** de deux lignes, `source='SIMPLE'` : compte de trésorerie
(512x ou 53x) contre le compte de la catégorie. Aucune donnée propre au mode simple : le passage en
partie double (D.5) ne demande aucune reprise.

Une transaction bancaire importée se **catégorise** : l'opération est créée à sa date et à son
montant, et sa ligne de trésorerie rapprochée de la transaction dans la même transaction.
La liste des opérations reprend toute ligne de classe 6 ou 7 d'une écriture qui touche la
trésorerie (opérations saisies, catégorisées, mouvements de caisse, écritures de règle).
"""
from datetime import date

from app.extensions import db
from app.models import (
    Account, BankAccount, BankTransaction, Entity, FiscalYear, Journal, JournalEntry, JournalLine, SimpleCategory,
)
from app.services import projects, simple_categories
from app.services.ledger import delete_entries, entry_is_reconciled, post_entry

SOURCE_SIMPLE = "SIMPLE"
JOURNALS = {"bank": ("BQ", "Banque"), "cash": ("CA", "Caisse")}


class OperationError(Exception):
    def __init__(self, message, field=None, status=422):
        super().__init__(message)
        self.message, self.field, self.status = message, field, status


def _journal(kind):
    code, label = JOURNALS[kind]
    journal = Journal.query.filter_by(code=code).first()
    if journal is None:
        journal = Journal(code=code, label=label)
        db.session.add(journal)
        db.session.flush()
    return journal


def _fiscal_year(when: date) -> FiscalYear:
    fy = FiscalYear.query.filter(FiscalYear.start_date <= when, FiscalYear.end_date >= when).first()
    if fy is None:
        raise OperationError(f"Aucun exercice ne couvre le {when:%d/%m/%Y} : créez-le dans Compta › Exercices.", "date")
    if fy.closed:
        raise OperationError(f"L'exercice {fy.label} est verrouillé.", "date", 409)
    return fy


def _clean(data: dict, *, need_treasury=True):
    try:
        when = date.fromisoformat(str(data.get("date") or ""))
    except ValueError:
        raise OperationError("Date invalide.", "date") from None
    label = (data.get("label") or "").strip()[:300]
    if not label:
        raise OperationError("Libellé obligatoire.", "label")
    amount = data.get("amount_cents")
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
        raise OperationError("Montant positif attendu.", "amount_cents")
    category = db.session.get(SimpleCategory, data.get("category_id")) if isinstance(data.get("category_id"), int) else None
    if category is None:
        raise OperationError("Catégorie obligatoire.", "category_id")
    treasury = None
    if need_treasury:
        treasury = db.session.get(BankAccount, data.get("bank_account_id")) if isinstance(data.get("bank_account_id"), int) else None
        if treasury is None:
            raise OperationError("Compte bancaire ou caisse obligatoire.", "bank_account_id")
    entity = None
    if data.get("entity_id") not in (None, ""):
        entity = db.session.get(Entity, data.get("entity_id")) if isinstance(data.get("entity_id"), int) else None
        if entity is None:
            raise OperationError("Tiers inconnu.", "entity_id")
    try:
        project = projects.resolve(data.get("project_id"))
    except ValueError as exc:
        raise OperationError(str(exc), "project_id") from None
    return when, label, amount, category, treasury, entity, project


def _lines(category, treasury_account_id, amount, label, entity, project):
    income = category.kind == "income"
    return [
        {"account_id": treasury_account_id, "label": label,
         "debit_cents": amount if income else 0, "credit_cents": 0 if income else amount},
        {"account_id": category.account_id, "label": label, "debit_cents": 0 if income else amount,
         "credit_cents": amount if income else 0, "project_id": project.id if project else None},
    ], entity


def create(data: dict) -> JournalEntry:
    when, label, amount, category, treasury, entity, project = _clean(data)
    fy = _fiscal_year(when)
    lines, entity = _lines(category, treasury.account_id, amount, label, entity, project)
    entry = post_entry(fy.id, _journal(treasury.kind).id, when, label, lines, source=SOURCE_SIMPLE, commit=False)
    _set_entity(entry, category, entity)
    db.session.commit()
    return entry


def _set_entity(entry, category, entity):
    for line in entry.lines:
        if line.account_id == category.account_id:
            line.entity_id = entity.id if entity else None


def categorize(transaction_id: int, data: dict) -> JournalEntry:
    """Transaction bancaire importée → opération de sa catégorie, rapprochée aussitôt."""
    bt = db.session.get(BankTransaction, transaction_id)
    if bt is None:
        raise OperationError("Transaction introuvable.", status=404)
    if bt.reconciled or bt.journal_line_id is not None:
        raise OperationError("Transaction déjà rapprochée.", status=409)
    if bt.is_reversed:
        raise OperationError("Transaction annulée par la banque.", status=409)
    payload = {"date": bt.transaction_date.isoformat(), "label": data.get("label") or bt.label or "Opération",
               "amount_cents": abs(bt.amount_cents), "category_id": data.get("category_id"),
               "entity_id": data.get("entity_id", bt.entity_id), "project_id": data.get("project_id")}
    when, label, amount, category, _treasury, entity, project = _clean(payload, need_treasury=False)
    if (bt.amount_cents > 0) != (category.kind == "income"):
        raise OperationError("Un encaissement va dans une catégorie de recette, un débit dans une dépense.", "category_id")
    fy = _fiscal_year(when)
    lines, entity = _lines(category, bt.bank_account.account_id, amount, label, entity, project)
    entry = post_entry(fy.id, _journal("bank").id, when, label, lines, source=SOURCE_SIMPLE, commit=False)
    _set_entity(entry, category, entity)
    treasury_line = next(l for l in entry.lines if l.account_id == bt.bank_account.account_id)
    bt.journal_line_id, bt.reconciled = treasury_line.id, True
    if entity is not None and bt.entity_id is None:
        bt.entity_id = entity.id
    db.session.commit()
    return entry


def update(entry_id: int, data: dict) -> JournalEntry:
    """Modification d'une opération saisie ; rapprochée : seuls libellé, catégorie (même sens),
    tiers et projet changent (date, montant et compte suivent le relevé)."""
    entry = db.session.get(JournalEntry, entry_id)
    if entry is None or entry.source != SOURCE_SIMPLE:
        raise OperationError("Opération introuvable.", status=404)
    if entry.fiscal_year.closed:
        raise OperationError("Exercice verrouillé.", status=409)
    treasury_line, category_line = _split(entry)
    reconciled = entry_is_reconciled(entry)
    current = {"date": entry.entry_date.isoformat(), "amount_cents": category_line.debit_cents or category_line.credit_cents,
               "bank_account_id": _treasury_of(treasury_line).id if _treasury_of(treasury_line) else None}
    merged = {**current, **data} if not reconciled else {**data, **current}
    when, label, amount, category, treasury, entity, project = _clean(merged)
    old_income = category_line.credit_cents > 0
    if reconciled and (category.kind == "income") != old_income:
        raise OperationError("Opération rapprochée : la catégorie garde le même sens (recette ou dépense).", "category_id")
    fy = _fiscal_year(when)
    income = category.kind == "income"
    entry.entry_date, entry.description, entry.fiscal_year_id = when, label, fy.id
    treasury_line.account_id = treasury.account_id
    treasury_line.debit_cents, treasury_line.credit_cents = (amount, 0) if income else (0, amount)
    category_line.account_id = category.account_id
    category_line.debit_cents, category_line.credit_cents = (0, amount) if income else (amount, 0)
    category_line.project_id = project.id if project else None
    category_line.entity_id = entity.id if entity else None
    for line in (treasury_line, category_line):
        line.label = label
    db.session.commit()
    return entry


def delete(entry_id: int) -> str:
    entry = db.session.get(JournalEntry, entry_id)
    if entry is None or entry.source != SOURCE_SIMPLE:
        raise OperationError("Opération introuvable.", status=404)
    (outcome,) = delete_entries([entry_id])
    if outcome["status"] != "ok":
        raise OperationError(outcome.get("message") or "Suppression impossible.", status=409)
    return outcome["reference"]


def _split(entry):
    treasury = [l for l in entry.lines if l.account.code.startswith(("51", "53"))]
    other = [l for l in entry.lines if not l.account.code.startswith(("51", "53"))]
    if len(treasury) != 1 or len(other) != 1:
        raise OperationError("Écriture non modifiable ici (plus de deux lignes).", status=409)
    return treasury[0], other[0]


def _treasury_of(line):
    return BankAccount.query.filter_by(account_id=line.account_id).first()


# ------------------------------------------------------------------ liste


def operations(start: date, end: date, *, category_id=None, kind=None, bank_account_id=None, project_id=None) -> dict:
    """Recettes et dépenses de la période : lignes 6 / 7 des écritures qui touchent la trésorerie."""
    categories = {c.account_id: c for c in simple_categories.listing()}
    treasury_accounts = {b.account_id: b for b in BankAccount.query}
    query = (JournalLine.query.join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
             .join(Account, Account.id == JournalLine.account_id)
             .filter(JournalEntry.entry_date.between(start, end),
                     db.or_(Account.code.like("6%"), Account.code.like("7%"))))
    if project_id:
        query = query.filter(JournalLine.project_id == project_id)
    rows, income, expense = [], 0, 0
    for line in query.order_by(JournalEntry.entry_date.desc(), JournalEntry.id.desc()):
        treasury = next((treasury_accounts[o.account_id] for o in line.entry.lines if o.account_id in treasury_accounts), None)
        if treasury is None:
            continue  # écriture sans trésorerie (inventaire, dotation…) : hors recettes / dépenses
        category = categories.get(line.account_id)
        amount = line.credit_cents - line.debit_cents
        row_kind = "income" if line.account.code.startswith("7") else "expense"
        if category_id and (category is None or category.id != category_id):
            continue
        if kind and row_kind != kind:
            continue
        if bank_account_id and treasury.id != bank_account_id:
            continue
        signed = amount if row_kind == "income" else -(line.debit_cents - line.credit_cents)
        if row_kind == "income":
            income += amount
        else:
            expense += line.debit_cents - line.credit_cents
        entity = db.session.get(Entity, line.entity_id) if line.entity_id else None
        rows.append({
            "entry_id": line.entry_id, "line_id": line.id, "date": line.entry.entry_date.isoformat(),
            "label": line.label or line.entry.description or "", "kind": row_kind, "amount_cents": signed,
            "category_id": category.id if category else None,
            "category": category.label if category else f"{line.account.code} {line.account.label}",
            "bank_account_id": treasury.id, "bank_account": treasury.label, "treasury_kind": treasury.kind,
            "entity_id": entity.id if entity else None, "entity": entity.name if entity else None,
            "project_id": line.project_id, "project": line.project.name if line.project else None,
            "reconciled": entry_is_reconciled(line.entry),
            "editable": line.entry.source == SOURCE_SIMPLE and not line.entry.fiscal_year.closed,
        })
    return {"rows": rows, "income_cents": income, "expense_cents": expense, "balance_cents": income - expense}


def to_categorize(limit=200) -> list[dict]:
    """Transactions bancaires importées, ni rapprochées ni annulées : à catégoriser."""
    rows = (BankTransaction.query.filter(BankTransaction.reconciled.is_(False), BankTransaction.journal_line_id.is_(None),
                                         BankTransaction.is_reversed.is_(False))
            .order_by(BankTransaction.transaction_date.desc()).limit(limit).all())
    return [{"id": t.id, "date": t.transaction_date.isoformat(), "label": t.label or "", "amount_cents": t.amount_cents,
             "bank_account": t.bank_account.label, "entity_id": t.entity_id,
             "entity": t.entity.name if t.entity else None} for t in rows]
