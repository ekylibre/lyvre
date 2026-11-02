"""Solde bancaire d'un compte bancaire (colonne « Solde bancaire » de Banque › Comptes bancaires).

- **Solde bancaire** = solde d'ouverture saisi + transactions importées (OFX, Qonto) depuis sa date,
  hors transactions annulées par la banque, jusqu'à la fin de l'exercice affiché (au plus aujourd'hui).
- **Solde d'ouverture manquant** (jamais saisi, ou daté après la période) : le montant affiché n'est
  que la somme des transactions de l'exercice ; l'écran demande de saisir le solde d'ouverture.
- **Écriture d'apport initial** : à la saisie du solde d'ouverture, quand rien n'est encore passé au
  compte 512 avant cette date (ni écriture, ni à-nouveaux), l'écriture 512 contre fonds propres est
  proposée — contrepartie selon la structure :
    · association : 102 « fonds associatif sans droit de reprise » (mise à disposition définitive),
      103 « avec droit de reprise » sinon ;
    · société, SCI : 101 « capital » ; 108 « compte de l'exploitant » (entreprise individuelle).
  Un compte existant du plan est préféré ; à défaut, le compte racine est créé.
"""
from datetime import date

from sqlalchemy import func, or_

from app.extensions import db
from app.models import Account, BankAccount, BankTransaction, FiscalYear, Journal, JournalEntry, JournalLine
from app.models.journal_entry import SOURCE_OPENING
from app.services.ledger import delete_entries, post_entry
from app.services.ledger_errors import LedgerError

SOURCE_BANK_OPENING = "BANK_OPENING"
OPENING_JOURNAL = ("OD", "Opérations diverses")

# Contreparties possibles par plan comptable : (préfixe, libellé du compte créé à défaut).
COUNTERPARTS = {
    "asso": [("102", "Fonds propres sans droit de reprise"), ("103", "Fonds propres avec droit de reprise")],
    "sci": [("101", "Capital"), ("108", "Compte de l'exploitant")],
    "societe": [("101", "Capital"), ("108", "Compte de l'exploitant")],
}


class BankBalanceError(Exception):
    def __init__(self, message, field=None, status=422):
        super().__init__(message)
        self.message, self.field, self.status = message, field, status


# ------------------------------------------------------------------ solde affiché

def display_fiscal_year(today: date | None = None) -> FiscalYear | None:
    """Exercice qui contient aujourd'hui, à défaut le dernier commencé, à défaut le premier."""
    today = today or date.today()
    fy = FiscalYear.query.filter(FiscalYear.start_date <= today, FiscalYear.end_date >= today).first()
    if fy is None:
        fy = (FiscalYear.query.filter(FiscalYear.start_date <= today)
              .order_by(FiscalYear.start_date.desc()).first())
    return fy or FiscalYear.query.order_by(FiscalYear.start_date).first()


def _sum(ba_id: int, start: date | None, end: date | None) -> int:
    query = (db.session.query(func.sum(BankTransaction.amount_cents))
             .filter(BankTransaction.bank_account_id == ba_id, BankTransaction.is_reversed.is_(False)))
    if start is not None:
        query = query.filter(BankTransaction.transaction_date >= start)
    if end is not None:
        query = query.filter(BankTransaction.transaction_date <= end)
    return int(query.scalar() or 0)


def bank_balance(ba: BankAccount, fy: FiscalYear | None, today: date | None = None) -> dict:
    """{balance_cents, at, opening_missing, fiscal_year} — `at` : date du solde (fin de l'exercice,
    au plus aujourd'hui)."""
    today = today or date.today()
    start, end = (fy.start_date, min(fy.end_date, today)) if fy else (None, today)
    opening = ba.opening_balance_cents is not None and ba.opening_balance_date is not None \
        and ba.opening_balance_date <= end
    if opening:
        balance = ba.opening_balance_cents + _sum(ba.id, ba.opening_balance_date, end)
    else:
        balance = _sum(ba.id, start, end)
    return {"balance_cents": balance, "at": end.isoformat(), "opening_missing": not opening,
            "fiscal_year": fy.label if fy else None}


# ------------------------------------------------------------------ solde d'ouverture

def default_opening_date(ba: BankAccount) -> date | None:
    """Date proposée : début de synchro Qonto, sinon début de l'exercice de la première transaction,
    sinon début de l'exercice affiché."""
    if ba.qonto_sync_from:
        return ba.qonto_sync_from
    first = (db.session.query(func.min(BankTransaction.transaction_date))
             .filter(BankTransaction.bank_account_id == ba.id).scalar())
    fy = None
    if first:
        fy = FiscalYear.query.filter(FiscalYear.start_date <= first, FiscalYear.end_date >= first).first()
        if fy is None:
            return first
    fy = fy or display_fiscal_year()
    return fy.start_date if fy else None


def ledger_already_open(ba: BankAccount, on_date: date) -> bool:
    """Vrai si le compte 512 a déjà des mouvements avant `on_date`, ou des à-nouveaux : son solde
    d'ouverture est alors repris par la comptabilité et ne doit pas l'être une seconde fois."""
    query = (db.session.query(JournalLine.id)
             .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
             .filter(JournalLine.account_id == ba.account_id,
                     or_(JournalEntry.entry_date < on_date, JournalEntry.source == SOURCE_OPENING)))
    if ba.opening_entry_id:
        query = query.filter(JournalEntry.id != ba.opening_entry_id)
    return db.session.query(query.exists()).scalar()


def counterpart_options(chart: str) -> list[dict]:
    """Comptes de fonds propres proposés en contrepartie : les comptes existants des préfixes de la
    structure, sinon le compte racine à créer (valeur `new:<code>`)."""
    options = []
    for prefix, label in COUNTERPARTS.get(chart, COUNTERPARTS["asso"]):
        accounts = (Account.query.filter(Account.code.like(f"{prefix}%"), Account.is_header.is_(False))
                    .order_by(Account.code).all())
        if accounts:
            options += [{"value": str(a.id), "label": f"{a.code} — {a.label}"} for a in accounts]
        else:
            options.append({"value": f"new:{prefix}", "label": f"{prefix} — {label} (à créer)"})
    return options


def _counterpart(value, chart: str) -> Account:
    value = str(value or "")
    allowed = [prefix for prefix, _ in COUNTERPARTS.get(chart, COUNTERPARTS["asso"])]
    if value.startswith("new:"):
        code = value[4:]
        labels = dict(COUNTERPARTS.get(chart, COUNTERPARTS["asso"]))
        if code not in labels:
            raise BankBalanceError("Compte de contrepartie inconnu.", "counterpart")
        account = Account.query.filter_by(code=code).first()
        if account is None:  # vérifié : aucun compte de ce préfixe dans le plan
            parent = Account.query.filter_by(code=code[0]).first()
            account = Account(code=code, label=labels[code], account_type="EQUITY",
                              parent_id=parent.id if parent else None)
            db.session.add(account)
            db.session.flush()
        return account
    account = db.session.get(Account, int(value)) if value.isdigit() else None
    if account is None or account.is_header or not account.code.startswith(tuple(allowed)):
        raise BankBalanceError(f"Choisissez un compte {' ou '.join(allowed)}….", "counterpart")
    return account


def _open_fiscal_year(on_date: date) -> FiscalYear:
    fy = FiscalYear.query.filter(FiscalYear.start_date <= on_date, FiscalYear.end_date >= on_date).first()
    if fy is None:
        raise BankBalanceError(f"Aucun exercice ne couvre le {on_date:%d/%m/%Y} : l'écriture d'apport "
                               "ne peut pas être passée.", "date")
    if fy.closed:
        raise BankBalanceError(f"L'exercice {fy.label} est clôturé : l'écriture d'apport ne peut pas être passée.",
                               "date", 409)
    if fy.locked_until and on_date <= fy.locked_until:
        raise BankBalanceError(f"Période verrouillée jusqu'au {fy.locked_until:%d/%m/%Y} : l'écriture d'apport "
                               "ne peut pas être passée.", "date", 409)
    return fy


def _drop_entry(ba: BankAccount) -> None:
    entry_id = ba.opening_entry_id
    if not entry_id:
        return
    ba.opening_entry_id = None  # validé avec la suppression (delete_entries valide la session)
    (outcome,) = delete_entries([entry_id])
    if outcome["status"] != "ok":  # écriture conservée : le lien est rétabli
        ba.opening_entry_id = entry_id
        db.session.commit()
        raise BankBalanceError(f"L'écriture d'apport initial ne peut pas être supprimée : {outcome.get('message')}",
                               status=409)


def set_opening(ba: BankAccount, data: dict, chart: str) -> JournalEntry | None:
    """Enregistre (ou retire, montant vide) le solde d'ouverture ; passe l'écriture d'apport si
    demandé (`post_entry`) et permis. Renvoie l'écriture passée."""
    if ba.kind != "bank":
        raise BankBalanceError("Une caisse n'a pas de solde bancaire.", status=409)
    amount = data.get("amount_cents")
    if amount is None:  # retrait du solde d'ouverture (et de son écriture)
        _drop_entry(ba)
        ba.opening_balance_cents = ba.opening_balance_date = None
        db.session.commit()
        return None
    if not isinstance(amount, int) or isinstance(amount, bool):
        raise BankBalanceError("Montant en centimes attendu.", "amount_cents")
    try:
        on_date = date.fromisoformat(str(data.get("date") or ""))
    except ValueError:
        raise BankBalanceError("Date invalide.", "date") from None

    want_entry = bool(data.get("post_entry")) and amount != 0
    if want_entry:
        if ledger_already_open(ba, on_date):
            raise BankBalanceError(f"Le compte {ba.account.code} a déjà des écritures avant le {on_date:%d/%m/%Y} "
                                   "ou des à-nouveaux : son solde est déjà repris en comptabilité.", "post_entry", 409)
        fy = _open_fiscal_year(on_date)
        counterpart = _counterpart(data.get("counterpart"), chart)

    _drop_entry(ba)
    ba.opening_balance_cents, ba.opening_balance_date = amount, on_date
    entry = None
    if want_entry:
        journal = Journal.query.filter_by(code=OPENING_JOURNAL[0]).first()
        if journal is None:
            journal = Journal(code=OPENING_JOURNAL[0], label=OPENING_JOURNAL[1])
            db.session.add(journal)
            db.session.flush()
        label = f"Solde bancaire d'ouverture — {ba.label}"[:200]
        debit, credit = (amount, 0) if amount > 0 else (0, -amount)
        try:
            entry = post_entry(fy.id, journal.id, on_date, label, [
                {"account_id": ba.account_id, "label": label, "debit_cents": debit, "credit_cents": credit},
                {"account_id": counterpart.id, "label": label, "debit_cents": credit, "credit_cents": debit},
            ], source=SOURCE_BANK_OPENING, source_ref=f"bank_account:{ba.id}", commit=False)
        except LedgerError as exc:
            db.session.rollback()
            raise BankBalanceError(str(exc), "date", 409) from None
        ba.opening_entry_id = entry.id
    db.session.commit()
    return entry


def opening_payload(ba: BankAccount) -> dict:
    """Solde d'ouverture et valeurs proposées pour le formulaire."""
    entry = db.session.get(JournalEntry, ba.opening_entry_id) if ba.opening_entry_id else None
    proposed = ba.opening_balance_date or default_opening_date(ba)
    return {
        "amount_cents": ba.opening_balance_cents,
        "date": ba.opening_balance_date.isoformat() if ba.opening_balance_date else None,
        "proposed_date": proposed.isoformat() if proposed else None,
        "entry": {"id": entry.id, "reference": entry.reference,
                  "counterpart": next((f"{l.account.code} — {l.account.label}" for l in entry.lines
                                       if l.account_id != ba.account_id), None)} if entry else None,
        # Écriture d'apport possible à la date proposée (rien au 512 avant, pas d'à-nouveaux).
        "entry_allowed": bool(proposed) and not ledger_already_open(ba, proposed),
    }
