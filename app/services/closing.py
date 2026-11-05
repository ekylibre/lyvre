"""Assistant de clôture d'un exercice (phases A.4 et A.5 : étapes 1 à 8).

Étapes : 1 `checks` (contrôles), 2 `inventory` (écritures d'inventaire), 3 `dedicated_funds`
(fonds dédiés, phase A.6), 4 `result`, 5 `fec` (essai à blanc du FEC), 6 `close` (clôture
provisoire puis définitive), 7 `opening` et 8 `allocation` (phase A.5).

- Les contrôles sont **recalculés** à chaque lecture ; seule la décision de l'utilisateur est
  stockée (`closing_steps`) : `done`, ou `skipped` avec un motif obligatoire.
- Clôture provisoire (administrateur ou trésorier) : étapes 1 à 5 décidées, exercice ouvert ;
  écritures verrouillées et numérotées (`fec.validate`). Clôture définitive (administrateur) :
  FEC figé (`fec.freeze`), irréversible. Réouverture d'une clôture provisoire (administrateur),
  refusée si l'exercice suivant est clôturé définitivement ou si le résultat y est déjà affecté ;
  elle supprime les à-nouveaux et extournes de l'exercice suivant (à regénérer).
- Ouverture (exercice au moins en clôture provisoire) : exercice suivant créé au besoin,
  à-nouveaux (journal AN, classes 1 à 5, résultat en 120 / 129, à défaut 12) et extournes des
  écritures d'inventaire, au premier jour de l'exercice suivant ; regénérable tant que
  l'exercice suivant est ouvert et le résultat non affecté.
- Affectation : décision (organe, date dans l'exercice suivant) et répartition du résultat sur
  des comptes 10x, 11x ou 455x (comptes courants des associés d'une SCI) ; annulable.
- Toute action est tracée dans `closing_events`.
"""
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import func

from app.extensions import db
from app.models import (
    Account, BankAccount, BankTransaction, ClosingEvent, ClosingStep, FiscalYear, Journal, JournalEntry, JournalLine,
    Purchase,
)
from app.models.closing import CLOSING_STEPS
from app.models.fiscal_year import FY_CLOSED, FY_OPEN, FY_PROVISIONAL
from app.models.journal_entry import SOURCE_ALLOCATION, SOURCE_INVENTORY, SOURCE_OPENING, SOURCE_REVERSAL
from app.services import fec, period_lock, validation
from app.services.ledger import LedgerError, delete_entries, post_entry
from app.services.purchase_posting import purchase_state
from app.utils.money import euros

STEP_LABELS = {
    "checks": "Contrôles", "inventory": "Écritures d'inventaire", "dedicated_funds": "Fonds dédiés",
    "result": "Résultat", "fec": "Contrôle du FEC", "close": "Clôture", "opening": "Ouverture de l'exercice suivant",
    "allocation": "Affectation du résultat",
}
DECIDED_BEFORE_CLOSE = ("checks", "inventory", "dedicated_funds", "result", "fec")
LATER_STEPS = ("opening", "allocation")  # après la clôture provisoire
INVENTORY_JOURNAL = ("OD", "Opérations diverses")
OPENING_JOURNAL = ("AN", "À-nouveaux")
BALANCE_SHEET_CLASSES = ("1", "2", "3", "4", "5")
# Compte du résultat dans les à-nouveaux : le plus précis présent dans le plan.
RESULT_ACCOUNTS = {True: ("120", "12"), False: ("129", "12")}  # excédent / déficit
ALLOCATION_PREFIXES = ("10", "11", "455")
MIN_NOTE = 5

# Type d'écriture d'inventaire → (classe du compte de charge / produit, contreparties possibles,
# la charge / le produit est-il au débit ?)
INVENTORY_KINDS = {
    "accrued_expense": {"label": "Charge à payer", "classes": ("6",), "counterparts": ("408", "4686", "4311"),
                        "account_debit": True},
    "accrued_income": {"label": "Produit à recevoir", "classes": ("7",), "counterparts": ("4687", "418", "441"),
                       "account_debit": False},
    "prepaid_expense": {"label": "Charge constatée d'avance", "classes": ("6",), "counterparts": ("486",),
                        "account_debit": False},
    "deferred_income": {"label": "Produit constaté d'avance", "classes": ("7",), "counterparts": ("487",),
                        "account_debit": True},
    # Exploitation agricole (lot AG1.d) : chaque convention de compte courant (472x) se solde à la clôture en 412
    # (solde débiteur) ou en 402 (solde créditeur), titre 5 art. 132-1 ; extournée à l'ouverture comme les autres.
    "compensation_debit": {"label": "Convention de compte courant : solde débiteur → 412", "classes": ("472",),
                           "counterparts": ("412",), "account_debit": False, "charts": ("agri",)},
    "compensation_credit": {"label": "Convention de compte courant : solde créditeur → 402", "classes": ("472",),
                            "counterparts": ("402",), "account_debit": True, "charts": ("agri",)},
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

    drafts = validation.drafts(fy).count()
    if drafts:
        found.append(Check("drafts", f"{drafts} écriture(s) en brouillard : la clôture provisoire les validera",
                           drafts, "info", f"/entries/?fy_id={fy.id}&state=draft"))

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

    from app.tenant import current_chart
    agri = current_chart() == "agri"
    if agri:
        found += _agri_checks(fy)
    for code, balance in sorted(_balances(fy, ("47",)).items()):
        if balance and not (agri and code.startswith("472")):
            found.append(Check(f"suspense_{code}", f"Compte d'attente {code} non soldé ({fec.amount(balance)} €)", 1,
                               "anomaly", "/reports/balance"))
    for code, balance in sorted(_balances(fy, ("58",)).items()):
        if balance:
            found.append(Check(f"transfer_{code}", f"Virements internes {code} non soldés ({fec.amount(balance)} €) : "
                               "dépôt d'espèces ou virement sans sa contrepartie", 1, "anomaly", "/reports/balance"))
    for code, balance in sorted(_balances(fy, ("512", "53")).items()):
        if balance < 0:
            found.append(Check(f"credit_{code}", f"Compte {code} créditeur en fin d'exercice ({fec.amount(balance)} €) :"
                               " trésorerie négative ou écriture manquante", 1, "anomaly", "/reports/balance"))
    return found


def _agri_checks(fy) -> list[Check]:
    """Contrôles de l'exploitation agricole (lot AG1.d, design § 6.5)."""
    from app.models import Asset
    from app.models.journal_entry import SOURCE_OPENING

    found = []
    for code, balance in sorted(_balances(fy, ("472",)).items()):
        if balance:
            side = "débiteur : en 412" if balance > 0 else "créditeur : en 402"
            found.append(Check(f"compensation_{code}", f"Convention de compte courant {code} non soldée "
                               f"({fec.amount(balance)} €) : soldez le solde {side} (écriture d'inventaire)", 1,
                               "anomaly", f"/fiscal-years/{fy.id}/closing"))
    credited = (db.session.query(func.coalesce(func.sum(JournalLine.credit_cents), 0))
                .join(Account, Account.id == JournalLine.account_id)
                .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
                .filter(JournalEntry.fiscal_year_id == fy.id, JournalEntry.source != SOURCE_OPENING,
                        Account.code.like("24%")).scalar())
    disposals = _balances(fy, ("6571", "7571"))
    if credited and not any(disposals.values()):
        found.append(Check("living_disposal", "Biens vivants immobilisés sortis (compte 24 crédité) sans cession en "
                           "7571 / 6571 : la cession d'un bien vivant se porte en résultat d'exploitation", 1,
                           "anomaly", "/reports/grand-livre"))
    living = {code: v for code, v in _balances(fy, ("24",)).items() if v > 0}
    registered = {a.account_id for a in Asset.query.join(Account, Account.id == Asset.account_id)
                  .filter(Account.code.like("24%"))}
    accounts = {a.code: a.id for a in Account.query.filter(Account.code.in_(living))} if living else {}
    missing = [code for code in living if accounts.get(code) not in registered]
    if missing:
        found.append(Check("living_register", f"Biens vivants immobilisés sans fiche au registre des immobilisations "
                           f"({', '.join(missing)})", len(missing), "info", "/assets/"))
    from app.services import aid_payments    # lot AG3.b

    unlinked = aid_payments.unlinked_credits(fy.start_date, fy.end_date)
    if unlinked:
        found.append(Check("aid_unlinked", "Virements reçus d'un payeur d'aides (ASP, FranceAgriMer, Région…) rattachés "
                           "à aucun dossier d'aide", len(unlinked), "info", "/aids/"))
    from app.services import stock_entry    # lot AG4.d

    from app.services import stock_tax    # lot AG4.e

    for key, label, count, severity in [*stock_entry.checks(fy), *stock_tax.checks(fy)]:
        found.append(Check(key, label, count, severity, f"/inventory/?fiscal_year={fy.id}"))
    from app.services import living_assets    # lot AG5.b

    from app.services import living_exits    # lot AG5.c

    from app.services import stock_lots    # lot AG5.d

    for key, label, count, severity in stock_lots.checks(fy):
        found.append(Check(key, label, count, severity, f"/inventory/?fiscal_year={fy.id}&group=animals"))
    for key, label, count, severity in [*living_assets.checks(fy), *living_exits.checks(fy)]:
        found.append(Check(key, label, count, severity, f"/fiscal-years/{fy.id}/closing"))
    from app.services import aid_closing    # lot AG3.c

    for key, label, count, severity in aid_closing.checks(fy):
        url = "/aids/" if key == "aid_issues" else f"/fiscal-years/{fy.id}/closing"
        found.append(Check(key, label, count, severity, url))
    return found


# ------------------------------------------------------------------ étape 2 : inventaire


def _account(code):
    account = Account.query.filter_by(code=code, is_header=False).first()
    if account is None:
        raise ClosingError(f"Compte {code} absent du plan comptable.", 422)
    return account


def _journal(spec=INVENTORY_JOURNAL):
    code, label = spec
    journal = Journal.query.filter_by(code=code).first()
    if journal is None:
        journal = Journal(code=code, label=label)
        db.session.add(journal)
        db.session.flush()
    return journal


def inventory_entries(fy):
    return (JournalEntry.query.filter_by(fiscal_year_id=fy.id, source=SOURCE_INVENTORY)
            .order_by(JournalEntry.id).all())


def add_inventory(fy, kind, account_code, amount_cents, label, counterpart_code=None, user_id=None, source_ref=None):
    """Écriture d'inventaire datée du dernier jour de l'exercice (extournée à l'ouverture de N+1)."""
    if fy.status != FY_OPEN:
        raise ClosingError("Exercice clôturé : rouvrez-le pour ajouter une écriture d'inventaire.")
    spec = INVENTORY_KINDS.get(kind)
    if spec is None or not _kind_applies(spec):
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
        source=SOURCE_INVENTORY, source_ref=source_ref, commit=False)
    entry.inventory_kind = kind
    log(fy, "inventory", "add", user_id, entry=entry.reference, kind=kind, amount_cents=amount_cents)
    db.session.commit()
    return entry


def delete_inventory(fy, entry_id, user_id=None):
    entry = db.session.get(JournalEntry, entry_id)
    if entry is None or entry.fiscal_year_id != fy.id or entry.source != SOURCE_INVENTORY:
        raise ClosingError("Écriture d'inventaire introuvable.", 404)
    reference = entry.reference
    (outcome,) = delete_entries([entry_id], allow_managed=True)
    if outcome["status"] != "ok":
        raise ClosingError(outcome.get("message") or "Suppression impossible.")
    log(fy, "inventory", "delete", user_id, entry=reference)
    db.session.commit()


# ------------------------------------------------------------------ états des étapes


def _stored(fy) -> dict[str, ClosingStep]:
    return {s.step: s for s in ClosingStep.query.filter_by(fiscal_year_id=fy.id)}


def next_fiscal_year(fy):
    return FiscalYear.query.filter(FiscalYear.start_date > fy.end_date).order_by(FiscalYear.start_date).first()


def step_keys() -> tuple[str, ...]:
    """Étapes de la structure : les fonds dédiés n'existent que pour une association."""
    from app.tenant import is_association
    return CLOSING_STEPS if is_association() else tuple(s for s in CLOSING_STEPS if s != "dedicated_funds")


def decided_before_close() -> tuple[str, ...]:
    keys = step_keys()
    return tuple(s for s in DECIDED_BEFORE_CLOSE if s in keys)


def steps(fy) -> list[dict]:
    stored = _stored(fy)
    out = []
    for key in step_keys():
        row = stored.get(key)
        state = row.state if row else "todo"
        if key == "close":
            state = {FY_OPEN: "todo", FY_PROVISIONAL: "provisional", FY_CLOSED: "done"}[fy.status]
        out.append({"key": key, "label": STEP_LABELS[key], "state": state, "note": row.note if row else None,
                    "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
                    "available": _available(fy, key, stored)})
    return out


def _available(fy, key, stored) -> bool:
    if key == "opening":
        return fy.status != FY_OPEN
    if key == "allocation":
        return fy.status != FY_OPEN and "opening" in stored and stored["opening"].state == "done"
    return True


def _mark(fy, step, state, user_id=None):
    row = ClosingStep.query.filter_by(fiscal_year_id=fy.id, step=step).first()
    if row is None:
        row = ClosingStep(fiscal_year_id=fy.id, step=step)
        db.session.add(row)
    row.state, row.note, row.user_id = state, None, user_id


def set_step(fy, step, state, note=None, user_id=None):
    if step not in decided_before_close():
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
    pending = [STEP_LABELS[s] for s in decided_before_close()
               if s not in stored or stored[s].state not in ("done", "skipped")]
    if pending:
        raise ClosingError("Étapes à terminer ou à ignorer avant la clôture : " + ", ".join(pending) + ".", 422)
    fy.status = FY_PROVISIONAL
    db.session.flush()
    try:
        count = fec.validate(fy, at=datetime.utcnow(), user_id=user_id)
    except LedgerError as exc:
        db.session.rollback()
        problems = getattr(exc, "problems", [])
        raise ClosingError(" ".join([str(exc), *problems[:3]]), 422) from None
    period_lock.on_provisional_close(fy)
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
    carried = opening_entries(fy)
    if following is not None and (carried or allocation_entry(fy)):
        if allocation_entry(fy) is not None or fy.allocation_decided_on:
            raise ClosingError(f"Résultat déjà affecté en {following.label} : annulez d'abord l'affectation (étape 8).")
        if following.status != FY_OPEN:
            raise ClosingError(f"L'exercice suivant ({following.label}) est clôturé : ses à-nouveaux ne peuvent "
                               "plus être regénérés.")
    if any(entry.is_validated for entry in carried):
        raise ClosingError(f"Les à-nouveaux de {following.label} sont validés : annulez d'abord leur lot de "
                           "validation (Exercices).")
    _drop(carried)
    # La clôture a validé les brouillards restants : la réouverture annule ce lot s'il est le dernier.
    last = validation.last_batch(fy)
    if last is not None and last.kind == "closing":
        validation.undo_last_batch(fy, f"Réouverture : {reason.strip()}", user_id, allow_locked=True)
    period_lock.on_reopen(fy)
    fy.status = FY_OPEN
    for row in ClosingStep.query.filter(ClosingStep.fiscal_year_id == fy.id, ClosingStep.step.in_(LATER_STEPS)):
        row.state = "todo"
    log(fy, "close", "reopen", user_id, reason=reason.strip(), dropped=len(carried))
    db.session.commit()


# ------------------------------------------------------------------ étape 7 : ouverture de N+1


def _following_entries(fy, source):
    following = next_fiscal_year(fy)
    if following is None:
        return []
    return (JournalEntry.query.filter_by(fiscal_year_id=following.id, source=source)
            .order_by(JournalEntry.id).all())


def opening_entries(fy):
    """À-nouveaux et extournes portés dans l'exercice suivant."""
    return _following_entries(fy, SOURCE_OPENING) + _following_entries(fy, SOURCE_REVERSAL)


def allocation_entry(fy):
    entries = _following_entries(fy, SOURCE_ALLOCATION)
    return entries[0] if entries else None


def _drop(entries):
    """Suppression sans validation (même transaction que la regénération)."""
    for entry in entries:
        line_ids = [line.id for line in entry.lines]
        if line_ids:
            BankTransaction.query.filter(BankTransaction.journal_line_id.in_(line_ids)).update(
                {"journal_line_id": None, "reconciled": False}, synchronize_session="fetch")
        db.session.delete(entry)
    db.session.flush()


def _result_account(surplus: bool):
    """120 / 129 (ou un sous-compte : 120000…), à défaut le compte 12 lui-même (plan SCI)."""
    precise, fallback = RESULT_ACCOUNTS[surplus]
    usable = Account.query.filter(Account.is_header.is_(False))
    account = (usable.filter(Account.code == precise).first()
               or usable.filter(Account.code.like(f"{precise}%")).order_by(Account.code).first()
               or usable.filter(Account.code == fallback).first())
    if account is not None:
        return account
    raise ClosingError(f"Compte {RESULT_ACCOUNTS[surplus][0]} absent du plan comptable.", 422)


def _cumulative(fy, prefixes, until, before=False) -> dict[str, int]:
    """Solde (débit − crédit) par compte, toutes années confondues, hors à-nouveaux, jusqu'à `until`
    (inclus, ou exclu si `before`)."""
    rows = (db.session.query(Account.code, func.sum(JournalLine.debit_cents - JournalLine.credit_cents))
            .join(JournalLine, JournalLine.account_id == Account.id)
            .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
            .filter(JournalEntry.source != SOURCE_OPENING,
                    JournalEntry.entry_date < until if before else JournalEntry.entry_date <= until,
                    db.or_(*[Account.code.like(f"{p}%") for p in prefixes]))
            .group_by(Account.code).all())
    return {code: int(total or 0) for code, total in rows}


def cumulative_opening(fy) -> bool:
    """Premier exercice clôturé en partie double après des exercices sans à-nouveaux (comptabilité
    simplifiée, D.5) : les soldes se calculent en cumulé depuis l'origine."""
    has_opening = JournalEntry.query.filter_by(fiscal_year_id=fy.id, source=SOURCE_OPENING).first() is not None
    has_prior = JournalEntry.query.filter(JournalEntry.entry_date < fy.start_date).first() is not None
    return has_prior and not has_opening


def _retained_account(positive: bool):
    """Report à nouveau : 110 (créditeur) / 119 (débiteur), ou sous-compte, à défaut 11."""
    precise = "110" if positive else "119"
    usable = Account.query.filter(Account.is_header.is_(False))
    account = (usable.filter(Account.code == precise).first()
               or usable.filter(Account.code.like(f"{precise}%")).order_by(Account.code).first()
               or usable.filter(Account.code == "11").first())
    if account is None:
        raise ClosingError(f"Compte {precise} (report à nouveau) absent du plan comptable.", 422)
    return account


def opening_lines(fy) -> list[dict]:
    """Lignes des à-nouveaux : soldes des comptes de bilan, résultat en 120 / 129 (ou 12).
    Après des exercices sans à-nouveaux (comptabilité simplifiée), soldes cumulés depuis l'origine
    et résultats antérieurs en report à nouveau (110 / 119)."""
    cumulative = cumulative_opening(fy)
    if cumulative:
        balances = {code: v for code, v in _cumulative(fy, BALANCE_SHEET_CLASSES, fy.end_date).items() if v}
    else:
        balances = {code: v for code, v in _balances(fy, BALANCE_SHEET_CLASSES).items() if v}
    accounts = {a.code: a for a in Account.query.filter(Account.code.in_(balances))} if balances else {}
    detailed = {} if cumulative else _open_lines_by_account(fy)
    lines = []
    for code in sorted(set(balances) | set(detailed)):
        v = balances.get(code, 0)
        if code in detailed:
            lines += _detailed_lines(detailed[code], v)
            continue
        lines.append({"account_id": accounts[code].id, "account_code": code, "label": accounts[code].label,
                      "debit_cents": max(v, 0), "credit_cents": max(-v, 0)})
    if cumulative:
        earlier = _cumulative(fy, ("6", "7"), fy.start_date, before=True)
        retained = -sum(earlier.values())  # produits (créditeurs) − charges (débitrices)
        if retained:
            account = _retained_account(retained > 0)
            lines.append({"account_id": account.id, "account_code": account.code, "label": account.label,
                          "debit_cents": max(-retained, 0), "credit_cents": max(retained, 0)})
    amount = result(fy)["result_cents"]
    if amount:
        account = _result_account(amount > 0)
        lines.append({"account_id": account.id, "account_code": account.code, "label": account.label,
                      "debit_cents": max(-amount, 0), "credit_cents": max(amount, 0)})
    gap = sum(line["debit_cents"] - line["credit_cents"] for line in lines)
    if gap:
        raise ClosingError(f"À-nouveaux déséquilibrés de {euros(gap)} : des comptes hors classes 1 à 7 "
                           "(classe 8 ?) ne sont pas soldés.", 422)
    return lines


def _open_lines_by_account(fy) -> dict[str, list]:
    """Lot F3 : lignes non lettrées (ou d'un lettrage partiel) des comptes lettrables de l'exercice."""
    from app.services.lettering import _open
    from app.models import Lettering
    rows = (JournalLine.query.join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
            .join(Account, Account.id == JournalLine.account_id)
            .outerjoin(Lettering, Lettering.id == JournalLine.lettering_id)
            .filter(JournalEntry.fiscal_year_id == fy.id, Account.lettrable.is_(True), _open())
            .order_by(Account.code, JournalEntry.entry_date, JournalLine.id).all())
    grouped = {}
    for line in rows:
        if line.debit_cents or line.credit_cents:
            grouped.setdefault(line.account.code, []).append(line)
    return grouped


def _detailed_lines(open_lines, balance) -> list[dict]:
    """À-nouveaux détaillés d'un compte lettrable : une ligne par ligne ouverte, reliée à elle
    (`carried_from_line_id`) ; un reste éventuel (lettrage à cheval sur deux exercices) en une ligne."""
    rows = []
    for line in open_lines:
        entry = line.entry
        text = f"{entry.reference or ''} {entry.entry_date:%d/%m/%Y} — {line.label or entry.description or ''}".strip()
        rows.append({"account_id": line.account_id, "account_code": line.account.code, "label": text[:300],
                     "debit_cents": line.debit_cents, "credit_cents": line.credit_cents,
                     "carried_from_line_id": line.id, "entity_id": line.entity_id})
    rest = balance - sum(r["debit_cents"] - r["credit_cents"] for r in rows)
    if rest:
        account = open_lines[0].account
        rows.append({"account_id": account.id, "account_code": account.code, "label": f"{account.label} (non détaillé)",
                     "debit_cents": max(rest, 0), "credit_cents": max(-rest, 0)})
    return rows


def create_next_fiscal_year(fy):
    start = fy.end_date + timedelta(days=1)
    try:
        end = start.replace(year=start.year + 1) - timedelta(days=1)
    except ValueError:  # 29 février
        end = date(start.year + 1, 3, 1) - timedelta(days=1)
    label = str(start.year) if (start.month, start.day) == (1, 1) else f"{start.year}-{end.year}"
    following = FiscalYear(label=label, start_date=start, end_date=end, vat_liable=fy.vat_liable)
    db.session.add(following)
    db.session.flush()
    return following


def generate_opening(fy, user_id=None, create_next=False):
    """À-nouveaux et extournes dans l'exercice suivant (regénérés s'ils existent)."""
    if fy.status == FY_OPEN:
        raise ClosingError("Clôturez d'abord l'exercice (au moins provisoirement).")
    following = next_fiscal_year(fy)
    if following is None:
        if not create_next:
            raise ClosingError("Aucun exercice suivant : créez-le pour y porter les à-nouveaux.", 422)
        following = create_next_fiscal_year(fy)
    if following.start_date != fy.end_date + timedelta(days=1):
        raise ClosingError(f"L'exercice {following.label} ne commence pas le lendemain de la clôture.", 422)
    if following.status != FY_OPEN:
        raise ClosingError(f"L'exercice suivant ({following.label}) est clôturé.")
    if allocation_entry(fy) is not None or fy.allocation_decided_on:
        raise ClosingError("Résultat déjà affecté : annulez d'abord l'affectation (étape 8).")
    lines = opening_lines(fy)
    if any(entry.is_validated for entry in opening_entries(fy)):
        raise ClosingError(f"Les à-nouveaux de {following.label} sont validés : annulez d'abord leur lot de "
                           "validation pour les regénérer.")
    _drop(opening_entries(fy))
    opening = None
    if lines:
        opening = post_entry(following.id, _journal(OPENING_JOURNAL).id, following.start_date,
                             f"À-nouveaux de l'exercice {fy.label}",
                             [{k: line[k] for k in ("account_id", "debit_cents", "credit_cents", "label",
                                                     "carried_from_line_id", "entity_id") if k in line} for line in lines],
                             source=SOURCE_OPENING, commit=False)
    reversals = []
    for entry in inventory_entries(fy):
        reversal = post_entry(following.id, _journal().id, following.start_date, f"Extourne — {entry.description}", [
            {"account_id": line.account_id, "label": line.label, "debit_cents": line.credit_cents,
             "credit_cents": line.debit_cents} for line in entry.lines], source=SOURCE_REVERSAL, commit=False)
        reversal.reverses_entry_id = entry.id
        reversals.append(reversal)
    _mark(fy, "opening", "done", user_id)
    log(fy, "opening", "generate", user_id, fiscal_year=following.label,
        entry=opening.reference if opening else None, reversals=len(reversals))
    db.session.commit()
    return following, opening, reversals


# ------------------------------------------------------------------ étape 8 : affectation


def result_to_allocate(fy) -> int:
    """Résultat porté par les à-nouveaux (positif : excédent), 0 sans à-nouveaux."""
    total = 0
    for entry in _following_entries(fy, SOURCE_OPENING):
        total += sum(line.credit_cents - line.debit_cents for line in entry.lines if line.account.code.startswith("12"))
    return total


def allocation_options():
    accounts = (Account.query.filter(Account.is_header.is_(False),
                                     db.or_(*[Account.code.like(f"{p}%") for p in ALLOCATION_PREFIXES]))
                .order_by(Account.code).all())
    return [{"value": a.code, "label": f"{a.code} — {a.label}"} for a in accounts]


def allocate(fy, decided_on, body, lines, user_id=None):
    """Décision d'affectation : écriture en OD datée de la décision, dans l'exercice suivant."""
    following = next_fiscal_year(fy)
    stored = _stored(fy)
    if following is None or "opening" not in stored or stored["opening"].state != "done":
        raise ClosingError("Générez d'abord les à-nouveaux (étape 7).", 422)
    if following.status != FY_OPEN:
        raise ClosingError(f"L'exercice suivant ({following.label}) est clôturé.")
    if allocation_entry(fy) is not None or fy.allocation_decided_on:
        raise ClosingError("Résultat déjà affecté : annulez l'affectation pour la modifier.")
    try:
        decided = date.fromisoformat(str(decided_on or ""))
    except ValueError:
        raise ClosingError("Date de la décision invalide.", 422) from None
    if not (following.start_date <= decided <= following.end_date):
        raise ClosingError(f"La décision doit être datée dans l'exercice {following.label}.", 422)
    body = (body or "").strip()[:100]
    if not body:
        raise ClosingError("Organe de décision obligatoire (assemblée générale, assemblée des associés…).", 422)
    amount = result_to_allocate(fy)
    targets = []
    for item in lines or []:
        cents = item.get("amount_cents") if isinstance(item, dict) else None
        if not isinstance(cents, int) or cents <= 0:
            raise ClosingError("Montant positif attendu sur chaque ligne d'affectation.", 422)
        account = _account(str(item.get("account_code") or "").strip())
        if not account.code.startswith(ALLOCATION_PREFIXES):
            raise ClosingError(f"Compte {account.code} : affectation sur un compte 10x, 11x ou 455x.", 422)
        targets.append((account, cents))
    if sum(cents for _a, cents in targets) != abs(amount):
        raise ClosingError(f"La répartition doit totaliser {euros(abs(amount))} (résultat à affecter).", 422)
    entry = None
    if amount:
        source = _result_account(amount > 0)
        text = f"Affectation du résultat {fy.label} — {body} du {decided:%d/%m/%Y}"
        rows = [{"account_id": source.id, "label": text, "debit_cents": max(amount, 0), "credit_cents": max(-amount, 0)}]
        rows += [{"account_id": account.id, "label": text, "debit_cents": cents if amount < 0 else 0,
                  "credit_cents": cents if amount > 0 else 0} for account, cents in targets]
        entry = post_entry(following.id, _journal().id, decided, text, rows, source=SOURCE_ALLOCATION, commit=False)
    fy.allocation_decided_on, fy.allocation_body = decided, body
    _mark(fy, "allocation", "done", user_id)
    log(fy, "allocation", "allocate", user_id, body=body, decided_on=decided.isoformat(),
        entry=entry.reference if entry else None, lines=[[a.code, c] for a, c in targets])
    db.session.commit()
    return entry


def cancel_allocation(fy, user_id=None):
    following = next_fiscal_year(fy)
    entry = allocation_entry(fy)
    if entry is None and not fy.allocation_decided_on:
        raise ClosingError("Aucune affectation à annuler.", 404)
    if following is not None and following.status != FY_OPEN:
        raise ClosingError(f"L'exercice suivant ({following.label}) est clôturé.")
    _drop([entry] if entry else [])
    fy.allocation_decided_on = fy.allocation_body = None
    _mark(fy, "allocation", "todo", user_id)
    log(fy, "allocation", "cancel", user_id, entry=entry.reference if entry else None)
    db.session.commit()


def events(fy, limit=50):
    rows = (ClosingEvent.query.filter_by(fiscal_year_id=fy.id)
            .order_by(ClosingEvent.at.desc(), ClosingEvent.id.desc()).limit(limit).all())
    # `at` est en UTC (utcnow) : suffixe Z pour un affichage en heure locale dans la SPA.
    return [{"at": e.at.isoformat() + "Z", "step": e.step, "action": e.action, "user_id": e.user_id,
             "details": json.loads(e.details_json) if e.details_json else None} for e in rows]


def inventory_options():
    """Comptes proposés : contreparties existantes par type d'écriture."""
    existing = {a.code: a.label for a in Account.query.filter(Account.is_header.is_(False))}
    return {kind: {"label": spec["label"], "classes": spec["classes"],
                   "counterparts": [{"value": c, "label": f"{c} — {existing[c]}"} for c in spec["counterparts"]
                                    if c in existing]}
            for kind, spec in INVENTORY_KINDS.items() if _kind_applies(spec)}


def _kind_applies(spec) -> bool:
    from app.tenant import current_chart
    return "charts" not in spec or current_chart() in spec["charts"]


