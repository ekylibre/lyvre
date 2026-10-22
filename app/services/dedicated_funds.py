"""Fonds dédiés (phase A.6, minimal) : étape 3 de l'assistant de clôture.

Une ressource affectée (subvention, contribution d'un autre organisme, don ou legs) reçue en N et
non utilisée à la clôture est **dotée** en fonds dédiés : débit 689x, crédit 19x. Les exercices
suivants, la part utilisée est **reprise** : débit 19x, crédit 789x. Les écritures sont passées en
journal OD au dernier jour de l'exercice (`source='DEDICATED_FUND'`, gérées par l'assistant).

- Dotations cumulées ≤ montant de la ressource ; utilisation ≤ solde au début de l'exercice.
- Mouvements possibles seulement sur un exercice ouvert ; supprimer un mouvement supprime son
  écriture.
- Lot C.5 : un fonds peut financer un **projet**. L'assistant propose alors le mouvement d'après le
  réalisé du projet (charges de classe 6 de l'exercice, hors dotations aux fonds dédiés) : l'année
  de la ressource, dotation du reste non utilisé (ressource − charges du projet) ; les années
  suivantes, utilisation à hauteur des charges du projet, dans la limite du solde du fonds.
"""
from app.extensions import db
from sqlalchemy import func

from app.models import Account, DedicatedFund, DedicatedFundMovement, Entity, FiscalYear, JournalEntry, JournalLine
from app.models.dedicated_fund import FUND_KINDS, MOVEMENT_KINDS
from app.models.fiscal_year import FY_OPEN
from app.models.journal_entry import SOURCE_DEDICATED_FUND
from app.services import projects as project_service
from app.services.closing import ClosingError, _journal, log
from app.services.ledger import delete_entries, post_entry
from app.utils.money import euros

MOVEMENT_LABELS = {"allocation": "Dotation", "use": "Utilisation"}


def _account(code):
    """Compte du plan : le code exact, sinon son premier sous-compte (6894 → 68940…)."""
    usable = Account.query.filter(Account.is_header.is_(False))
    account = (usable.filter(Account.code == code).first()
               or usable.filter(Account.code.like(f"{code}%")).order_by(Account.code).first())
    if account is None:
        raise ClosingError(f"Compte {code} absent du plan comptable (fonds dédiés).", 422)
    return account


def _open(fy):
    if fy.status != FY_OPEN:
        raise ClosingError("Exercice clôturé : rouvrez-le pour modifier les fonds dédiés.")


def balance_before(fund, fy) -> int:
    """Solde du fonds (19x) au début de l'exercice : dotations − utilisations antérieures."""
    total = 0
    for m in fund.movements:
        if m.fiscal_year.end_date < fy.start_date:
            total += m.amount_cents if m.kind == "allocation" else -m.amount_cents
    return total


def funds_for(fy):
    """Fonds concernés par l'exercice : créés jusqu'à lui et non soldés, ou mouvementés en N."""
    out = []
    for fund in DedicatedFund.query.join(FiscalYear, FiscalYear.id == DedicatedFund.origin_fiscal_year_id) \
            .filter(FiscalYear.start_date <= fy.start_date).order_by(DedicatedFund.id):
        current = [m for m in fund.movements if m.fiscal_year_id == fy.id]
        if fund.origin_fiscal_year_id == fy.id or current or balance_before(fund, fy) > 0:
            out.append(fund)
    return out


def project_spending(project, fy) -> int:
    """Charges du projet sur l'exercice (classe 6, hors écritures de fonds dédiés)."""
    value = (db.session.query(func.sum(JournalLine.debit_cents - JournalLine.credit_cents))
             .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
             .join(Account, Account.id == JournalLine.account_id)
             .filter(JournalLine.project_id == project.id, JournalEntry.fiscal_year_id == fy.id,
                     Account.code.like("6%"), JournalEntry.source != SOURCE_DEDICATED_FUND).scalar())
    return int(value or 0)


def suggestion(fund, fy) -> dict | None:
    """Mouvement proposé d'après le réalisé du projet (None sans projet ou si rien à proposer)."""
    if fund.project is None:
        return None
    spent = project_spending(fund.project, fy)
    current = [m for m in fund.movements if m.fiscal_year_id == fy.id]
    if fund.origin_fiscal_year_id == fy.id:
        allocated_total = sum(m.amount_cents for m in fund.movements if m.kind == "allocation")
        done = sum(m.amount_cents for m in current if m.kind == "allocation")
        target = max(fund.amount_cents - spent, 0)
        amount = min(target - done, fund.amount_cents - allocated_total)
        why = (f"Ressource {euros(fund.amount_cents)} − charges du projet {euros(spent)} "
               f"= {euros(target)} non utilisés")
        kind = "allocation"
    else:
        done = sum(m.amount_cents for m in current if m.kind == "use")
        target = min(balance_before(fund, fy), spent)
        amount = target - done
        why = f"Charges du projet {euros(spent)}, dans la limite du solde du fonds"
        kind = "use"
    if amount <= 0:
        return None
    return {"kind": kind, "amount_cents": amount, "spent_cents": spent, "explanation": why}


def payload(fund, fy) -> dict:
    current = [m for m in fund.movements if m.fiscal_year_id == fy.id]
    allocated = sum(m.amount_cents for m in fund.movements if m.kind == "allocation")
    start = balance_before(fund, fy)
    end = start + sum(m.amount_cents if m.kind == "allocation" else -m.amount_cents for m in current)
    return {
        "id": fund.id, "label": fund.label, "kind": fund.kind, "kind_label": FUND_KINDS[fund.kind]["label"],
        "origin": fund.origin_fiscal_year.label, "amount_cents": fund.amount_cents,
        "resource_account": fund.resource_account.code if fund.resource_account else None,
        "funder": db.session.get(Entity, fund.entity_id).name if fund.entity_id else None,
        "project_id": fund.project_id, "project": fund.project.name if fund.project else None,
        "suggestion": suggestion(fund, fy),
        "balance_start_cents": start, "balance_end_cents": end,
        "allocatable_cents": max(fund.amount_cents - allocated, 0),
        "movements": [{"id": m.id, "kind": m.kind, "kind_label": MOVEMENT_LABELS[m.kind], "amount_cents": m.amount_cents,
                       "entry": {"id": m.entry.id, "reference": m.entry.reference, "url": f"/entries/{m.entry.id}"}
                       if m.entry else None} for m in current],
    }


def options():
    return [{"value": k, "label": v["label"], "accounts": list(v["accounts"])} for k, v in FUND_KINDS.items()]


def _project(project_id):
    try:
        return project_service.resolve(project_id)
    except ValueError as exc:
        raise ClosingError(str(exc), 422) from None


def set_project(fy, fund_id, project_id, user_id=None):
    _open(fy)
    fund = db.session.get(DedicatedFund, fund_id)
    if fund is None or fund.origin_fiscal_year.start_date > fy.start_date:
        raise ClosingError("Fonds dédié introuvable pour cet exercice.", 404)
    project = _project(project_id)
    fund.project_id = project.id if project else None
    log(fy, "dedicated_funds", "fund_project", user_id, fund=fund.label, project=project.name if project else None)
    db.session.commit()
    return fund


def create_fund(fy, label, kind, amount_cents, resource_account_code=None, user_id=None, project_id=None):
    _open(fy)
    label = (label or "").strip()[:200]
    if not label:
        raise ClosingError("Libellé du fonds obligatoire.", 422)
    if kind not in FUND_KINDS:
        raise ClosingError("Nature de ressource inconnue.", 422)
    if not isinstance(amount_cents, int) or amount_cents <= 0:
        raise ClosingError("Montant de la ressource positif attendu.", 422)
    resource = None
    if resource_account_code:
        resource = Account.query.filter_by(code=str(resource_account_code).strip(), is_header=False).first()
        if resource is None or not resource.code.startswith("7"):
            raise ClosingError("Compte de la ressource : compte de produit (classe 7) attendu.", 422)
    project = _project(project_id)
    fund = DedicatedFund(label=label, kind=kind, amount_cents=amount_cents, origin_fiscal_year_id=fy.id,
                         resource_account_id=resource.id if resource else None,
                         project_id=project.id if project else None)
    db.session.add(fund)
    db.session.flush()
    log(fy, "dedicated_funds", "fund_add", user_id, fund=label, amount_cents=amount_cents)
    db.session.commit()
    return fund


def delete_fund(fy, fund_id, user_id=None):
    _open(fy)
    fund = db.session.get(DedicatedFund, fund_id)
    if fund is None or fund.origin_fiscal_year_id != fy.id:
        raise ClosingError("Fonds dédié introuvable dans cet exercice.", 404)
    if fund.movements:
        raise ClosingError("Supprimez d'abord les dotations et utilisations du fonds.")
    log(fy, "dedicated_funds", "fund_delete", user_id, fund=fund.label)
    db.session.delete(fund)
    db.session.commit()


def add_movement(fy, fund_id, kind, amount_cents, user_id=None):
    _open(fy)
    fund = db.session.get(DedicatedFund, fund_id)
    if fund is None or fund.origin_fiscal_year.start_date > fy.start_date:
        raise ClosingError("Fonds dédié introuvable pour cet exercice.", 404)
    if kind not in MOVEMENT_KINDS:
        raise ClosingError("Mouvement inconnu (dotation ou utilisation).", 422)
    if not isinstance(amount_cents, int) or amount_cents <= 0:
        raise ClosingError("Montant positif attendu.", 422)
    if kind == "allocation":
        allocated = sum(m.amount_cents for m in fund.movements if m.kind == "allocation")
        if allocated + amount_cents > fund.amount_cents:
            raise ClosingError(f"Dotation limitée au montant non encore doté ({euros(fund.amount_cents - allocated)}).",
                               422)
    else:
        start = balance_before(fund, fy)
        used = sum(m.amount_cents for m in fund.movements if m.fiscal_year_id == fy.id and m.kind == "use")
        if used + amount_cents > start:
            raise ClosingError(f"Utilisation limitée au solde du fonds au début de l'exercice "
                               f"({euros(start - used)}).", 422)
    expense, reserve, income = (_account(code) for code in FUND_KINDS[fund.kind]["accounts"])
    debit, credit = (expense, reserve) if kind == "allocation" else (reserve, income)
    text = f"{MOVEMENT_LABELS[kind]} fonds dédié — {fund.label}"
    entry = post_entry(fy.id, _journal().id, fy.end_date, text, [
        {"account_id": debit.id, "label": text, "debit_cents": amount_cents, "credit_cents": 0},
        {"account_id": credit.id, "label": text, "debit_cents": 0, "credit_cents": amount_cents}],
        source=SOURCE_DEDICATED_FUND, commit=False)
    movement = DedicatedFundMovement(fund_id=fund.id, fiscal_year_id=fy.id, kind=kind, amount_cents=amount_cents,
                                     entry_id=entry.id)
    db.session.add(movement)
    log(fy, "dedicated_funds", kind, user_id, fund=fund.label, entry=entry.reference, amount_cents=amount_cents)
    db.session.commit()
    return movement


def delete_movement(fy, movement_id, user_id=None):
    _open(fy)
    movement = db.session.get(DedicatedFundMovement, movement_id)
    if movement is None or movement.fiscal_year_id != fy.id:
        raise ClosingError("Mouvement introuvable dans cet exercice.", 404)
    reference = movement.entry.reference if movement.entry else None
    if movement.kind == "allocation":
        fund = movement.fund
        later = [m for m in fund.movements if m.kind == "use" and m.fiscal_year.start_date > fy.start_date]
        if later:
            raise ClosingError("Ce fonds a déjà été utilisé dans un exercice suivant.")
    entry_id = movement.entry_id
    db.session.delete(movement)
    db.session.flush()
    if entry_id:
        (outcome,) = delete_entries([entry_id], allow_managed=True)
        if outcome["status"] != "ok":
            raise ClosingError(outcome.get("message") or "Suppression impossible.")
    log(fy, "dedicated_funds", "delete", user_id, entry=reference)
    db.session.commit()
