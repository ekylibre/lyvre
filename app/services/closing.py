"""Assistant de clôture d'un exercice (phase A.4 : étapes 1 à 6).

Étapes : 1 `checks` (contrôles), 2 `inventory` (écritures d'inventaire), 3 `dedicated_funds`
(fonds dédiés, phase A.6), 4 `result`, 5 `fec` (essai à blanc du FEC), 6 `close` (clôture
provisoire puis définitive), 7 `opening` et 8 `allocation` (phase A.5).

- Les contrôles sont **recalculés** à chaque lecture ; seule la décision de l'utilisateur est
  stockée (`closing_steps`) : `done`, ou `skipped` avec un motif obligatoire.
- Clôture provisoire (administrateur ou trésorier) : étapes 1 à 5 décidées, exercice ouvert ;
  écritures verrouillées et numérotées (`fec.validate`). Clôture définitive (administrateur) :
  FEC figé (`fec.freeze`), irréversible. Réouverture d'une clôture provisoire (administrateur),
  refusée si l'exercice suivant est clôturé définitivement.
- Toute action est tracée dans `closing_events`.
"""
import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func

from app.extensions import db
from app.models import (
    Account, BankAccount, BankTransaction, ClosingEvent, ClosingStep, FiscalYear, Journal, JournalEntry, JournalLine,
    Purchase,
)
from app.models.closing import CLOSING_STEPS
from app.models.fiscal_year import FY_CLOSED, FY_OPEN, FY_PROVISIONAL
from app.models.journal_entry import SOURCE_INVENTORY
from app.services import fec
from app.services.ledger import delete_entries, post_entry
from app.services.purchase_posting import purchase_state

STEP_LABELS = {
    "checks": "Contrôles", "inventory": "Écritures d'inventaire", "dedicated_funds": "Fonds dédiés",
    "result": "Résultat", "fec": "Contrôle du FEC", "close": "Clôture", "opening": "Ouverture de l'exercice suivant",
    "allocation": "Affectation du résultat",
}
DECIDED_BEFORE_CLOSE = ("checks", "inventory", "dedicated_funds", "result", "fec")
LATER_STEPS = ("opening", "allocation")  # phase A.5
INVENTORY_JOURNAL = ("OD", "Opérations diverses")
MIN_NOTE = 5

# Type d'écriture d'inventaire → (classe du compte de charge / produit, contreparties possibles,
# la charge / le produit est-il au débit ?)
INVENTORY_KINDS = {
    "accrued_expense": {"label": "Charge à payer", "classes": ("6",), "counterparts": ("408", "4686"),
                        "account_debit": True},
    "accrued_income": {"label": "Produit à recevoir", "classes": ("7",), "counterparts": ("4687", "418", "441"),
                       "account_debit": False},
    "prepaid_expense": {"label": "Charge constatée d'avance", "classes": ("6",), "counterparts": ("486",),
                        "account_debit": False},
    "deferred_income": {"label": "Produit constaté d'avance", "classes": ("7",), "counterparts": ("487",),
                        "account_debit": True},
}


class ClosingError(Exception):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.message, self.status = message, status


@dataclass
class Check:
    key: str
    label: str
    count: int
    severity: str          # anomaly (motif exigé pour passer) | info
    url: str | None = None


def log(fy, step, action, user_id, **details):
    db.session.add(ClosingEvent(fiscal_year_id=fy.id, step=step, action=action, user_id=user_id,
                                details_json=json.dumps(details, ensure_ascii=False, default=str) if details else None))


# ------------------------------------------------------------------ soldes


def _balances(fy, prefixes) -> dict[str, int]:
    """Solde (débit − crédit) par compte de l'exercice, pour les comptes commençant par `prefixes`."""
    rows = (db.session.query(Account.code, func.sum(JournalLine.debit_cents - JournalLine.credit_cents))
            .join(JournalLine, JournalLine.account_id == Account.id)
            .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
            .filter(JournalEntry.fiscal_year_id == fy.id,
                    db.or_(*[Account.code.like(f"{p}%") for p in prefixes]))
            .group_by(Account.code).all())
    return {code: int(total or 0) for code, total in rows}


def result(fy) -> dict:
    """Produits (classe 7), charges (classe 6) et résultat de l'exercice, en centimes."""
    balances = _balances(fy, ("6", "7"))
    income = -sum(v for k, v in balances.items() if k.startswith("7"))
    expense = sum(v for k, v in balances.items() if k.startswith("6"))
    return {"income_cents": income, "expense_cents": expense, "result_cents": income - expense}


# ------------------------------------------------------------------ étape 1 : contrôles


def checks(fy) -> list[Check]:
    found = []
    unreconciled = (db.session.query(BankAccount.id, BankAccount.label, func.count(BankTransaction.id))
                    .join(BankTransaction, BankTransaction.bank_account_id == BankAccount.id)
                    .filter(BankTransaction.reconciled.is_(False), BankTransaction.is_reversed.is_(False),
                            BankTransaction.transaction_date.between(fy.start_date, fy.end_date))
                    .group_by(BankAccount.id, BankAccount.label).all())
    for ba_id, label, count in unreconciled:
        found.append(Check(f"unreconciled_{ba_id}", f"{count} transaction(s) non rapprochée(s) sur {label}", count,
                           "anomaly", f"/reconciliation/?bank_account_id={ba_id}"))

    sums = (db.session.query(JournalEntry.id, func.sum(JournalLine.debit_cents), func.sum(JournalLine.credit_cents))
            .join(JournalLine, JournalLine.entry_id == JournalEntry.id)
            .filter(JournalEntry.fiscal_year_id == fy.id).group_by(JournalEntry.id).all())
    unbalanced = [eid for eid, d, c in sums if (d or 0) != (c or 0)]
    if unbalanced:
        found.append(Check("unbalanced", f"{len(unbalanced)} écriture(s) déséquilibrée(s)", len(unbalanced), "anomaly",
                           f"/entries/{unbalanced[0]}"))
    outside = JournalEntry.query.filter(JournalEntry.fiscal_year_id == fy.id,
                                        db.not_(JournalEntry.entry_date.between(fy.start_date, fy.end_date))).count()
    if outside:
        found.append(Check("outside", f"{outside} écriture(s) datée(s) hors de l'exercice", outside, "anomaly",
                           "/entries/"))

    purchases = Purchase.query.filter(Purchase.is_hidden.is_(False),
                                      Purchase.issue_date.between(fy.start_date, fy.end_date)).all()
    not_posted = [p for p in purchases if purchase_state(p).code != "posted"]
    if not_posted:
        found.append(Check("purchases_not_posted", f"{len(not_posted)} facture(s) d'achat de l'exercice non "
                           "comptabilisée(s)", len(not_posted), "anomaly", "/purchases/?state=to_complete"))
    unpaid = [p for p in purchases if p.journal_entry_id and p.qonto_status != "paid"
              and not any(pay.journal_entry_id for pay in p.payments)]
    if unpaid:
        found.append(Check("purchases_unpaid", f"{len(unpaid)} facture(s) d'achat non réglée(s) à la clôture : dette "
                           "fournisseur au bilan", len(unpaid), "info", "/purchases/?unpaid=1"))

    for code, balance in sorted(_balances(fy, ("47",)).items()):
        if balance:
            found.append(Check(f"suspense_{code}", f"Compte d'attente {code} non soldé ({fec.amount(balance)} €)", 1,
                               "anomaly", "/reports/balance"))
    for code, balance in sorted(_balances(fy, ("512", "53")).items()):
        if balance < 0:
            found.append(Check(f"credit_{code}", f"Compte {code} créditeur en fin d'exercice ({fec.amount(balance)} €) :"
                               " trésorerie négative ou écriture manquante", 1, "anomaly", "/reports/balance"))
    return found


# ------------------------------------------------------------------ étape 2 : inventaire


def _account(code):
    account = Account.query.filter_by(code=code, is_header=False).first()
    if account is None:
        raise ClosingError(f"Compte {code} absent du plan comptable.", 422)
    return account


def _journal():
    code, label = INVENTORY_JOURNAL
    journal = Journal.query.filter_by(code=code).first()
    if journal is None:
        journal = Journal(code=code, label=label)
        db.session.add(journal)
        db.session.flush()
    return journal


def inventory_entries(fy):
    return (JournalEntry.query.filter_by(fiscal_year_id=fy.id, source=SOURCE_INVENTORY)
            .order_by(JournalEntry.id).all())


def add_inventory(fy, kind, account_code, amount_cents, label, counterpart_code=None, user_id=None):
    """Écriture d'inventaire datée du dernier jour de l'exercice (extournée à l'ouverture de N+1)."""
    if fy.status != FY_OPEN:
        raise ClosingError("Exercice clôturé : rouvrez-le pour ajouter une écriture d'inventaire.")
    spec = INVENTORY_KINDS.get(kind)
    if spec is None:
        raise ClosingError("Type d'écriture d'inventaire inconnu.", 422)
    if not isinstance(amount_cents, int) or amount_cents <= 0:
        raise ClosingError("Montant positif attendu.", 422)
    account = _account(str(account_code or "").strip())
    if not account.code.startswith(spec["classes"]):
        raise ClosingError(f"{spec['label']} : compte de classe {'/'.join(spec['classes'])} attendu.", 422)
    counterpart = _account(counterpart_code or spec["counterparts"][0])
    if not counterpart.code.startswith(spec["counterparts"]):
        raise ClosingError(f"{spec['label']} : contrepartie {', '.join(spec['counterparts'])} attendue.", 422)
    text = (label or "").strip()[:300] or spec["label"]
    debit, credit = (account, counterpart) if spec["account_debit"] else (counterpart, account)
    entry = post_entry(fy.id, _journal().id, fy.end_date, f"{spec['label']} — {text}", [
        {"account_id": debit.id, "label": text, "debit_cents": amount_cents, "credit_cents": 0},
        {"account_id": credit.id, "label": text, "debit_cents": 0, "credit_cents": amount_cents}],
        source=SOURCE_INVENTORY, commit=False)
    entry.inventory_kind = kind
    log(fy, "inventory", "add", user_id, entry=entry.reference, kind=kind, amount_cents=amount_cents)
    db.session.commit()
    return entry


def delete_inventory(fy, entry_id, user_id=None):
    entry = db.session.get(JournalEntry, entry_id)
    if entry is None or entry.fiscal_year_id != fy.id or entry.source != SOURCE_INVENTORY:
        raise ClosingError("Écriture d'inventaire introuvable.", 404)
    reference = entry.reference
    (outcome,) = delete_entries([entry_id])
    if outcome["status"] != "ok":
        raise ClosingError(outcome.get("message") or "Suppression impossible.")
    log(fy, "inventory", "delete", user_id, entry=reference)
    db.session.commit()


# ------------------------------------------------------------------ états des étapes


def _stored(fy) -> dict[str, ClosingStep]:
    return {s.step: s for s in ClosingStep.query.filter_by(fiscal_year_id=fy.id)}


def next_fiscal_year(fy):
    return FiscalYear.query.filter(FiscalYear.start_date > fy.end_date).order_by(FiscalYear.start_date).first()


def steps(fy) -> list[dict]:
    stored = _stored(fy)
    out = []
    for key in CLOSING_STEPS:
        row = stored.get(key)
        state = row.state if row else "todo"
        if key == "close":
            state = {FY_OPEN: "todo", FY_PROVISIONAL: "provisional", FY_CLOSED: "done"}[fy.status]
        out.append({"key": key, "label": STEP_LABELS[key], "state": state, "note": row.note if row else None,
                    "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
                    "available": key not in LATER_STEPS})
    return out


def set_step(fy, step, state, note=None, user_id=None):
    if step not in DECIDED_BEFORE_CLOSE:
        raise ClosingError("Étape non modifiable ici.", 422)
    if fy.status != FY_OPEN:
        raise ClosingError("Exercice clôturé : rouvrez-le pour modifier les étapes.")
    if state not in ("todo", "done", "skipped"):
        raise ClosingError("État inconnu.", 422)
    note = (note or "").strip() or None
    if state == "skipped" and (not note or len(note) < MIN_NOTE):
        raise ClosingError("Motif obligatoire pour ignorer une étape.", 422)
    if state == "done" and step == "checks":
        anomalies = [c for c in checks(fy) if c.severity == "anomaly"]
        if anomalies:
            raise ClosingError(f"{len(anomalies)} anomalie(s) : corrigez-les, ou ignorez l'étape avec un motif.", 422)
    if state == "done" and step == "fec":
        _file, errors, _warnings, problems = fec.preview(fy)
        if errors or problems:
            raise ClosingError("Le FEC ne passe pas les contrôles : " + " ".join((errors + problems)[:3]), 422)
    row = ClosingStep.query.filter_by(fiscal_year_id=fy.id, step=step).first()
    if row is None:
        row = ClosingStep(fiscal_year_id=fy.id, step=step)
        db.session.add(row)
    row.state, row.note, row.user_id = state, note if state == "skipped" else None, user_id
    log(fy, step, f"step_{state}", user_id, note=note)
    db.session.commit()


# ------------------------------------------------------------------ étape 6 : clôture


def close_provisional(fy, user_id=None):
    if fy.status != FY_OPEN:
        raise ClosingError("Cet exercice est déjà clôturé.")
    stored = _stored(fy)
    pending = [STEP_LABELS[s] for s in DECIDED_BEFORE_CLOSE
               if s not in stored or stored[s].state not in ("done", "skipped")]
    if pending:
        raise ClosingError("Étapes à terminer ou à ignorer avant la clôture : " + ", ".join(pending) + ".", 422)
    fy.status = FY_PROVISIONAL
    db.session.flush()
    count = fec.validate(fy, at=datetime.utcnow())
    log(fy, "close", "provisional", user_id, entries=count)
    db.session.commit()


def close_final(fy, user_id=None):
    if fy.status != FY_PROVISIONAL:
        raise ClosingError("La clôture définitive suit la clôture provisoire.")
    try:
        fec_file = fec.freeze(fy)
    except fec.FecError as exc:
        db.session.rollback()
        raise ClosingError("FEC impossible : " + " ".join(exc.errors[:3]), 422) from None
    fy.status, fy.closed_at, fy.closed_by_user_id = FY_CLOSED, datetime.utcnow(), user_id
    log(fy, "close", "final", user_id, fec=fec_file.filename, sha256=fec_file.sha256)
    db.session.commit()


def reopen(fy, user_id=None, reason=None):
    if fy.status != FY_PROVISIONAL:
        raise ClosingError("Seule une clôture provisoire se rouvre ; une clôture définitive est irréversible.")
    following = next_fiscal_year(fy)
    if following is not None and following.is_final:
        raise ClosingError(f"L'exercice suivant ({following.label}) est clôturé définitivement.")
    if not (reason or "").strip():
        raise ClosingError("Motif de réouverture obligatoire.", 422)
    fec.unvalidate(fy)
    fy.status = FY_OPEN
    for row in ClosingStep.query.filter(ClosingStep.fiscal_year_id == fy.id, ClosingStep.step.in_(LATER_STEPS)):
        row.state = "todo"
    log(fy, "close", "reopen", user_id, reason=reason.strip())
    db.session.commit()


def events(fy, limit=50):
    rows = (ClosingEvent.query.filter_by(fiscal_year_id=fy.id)
            .order_by(ClosingEvent.at.desc(), ClosingEvent.id.desc()).limit(limit).all())
    return [{"at": e.at.isoformat(), "step": e.step, "action": e.action, "user_id": e.user_id,
             "details": json.loads(e.details_json) if e.details_json else None} for e in rows]


def inventory_options():
    """Comptes proposés : contreparties existantes par type d'écriture."""
    existing = {a.code: a.label for a in Account.query.filter(Account.is_header.is_(False))}
    return {kind: {"label": spec["label"], "classes": spec["classes"],
                   "counterparts": [{"value": c, "label": f"{c} — {existing[c]}"} for c in spec["counterparts"]
                                    if c in existing]}
            for kind, spec in INVENTORY_KINDS.items()}


