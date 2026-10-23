"""Opérations du compte courant d'un associé (module « Associés », lot A3).

- facture d'achat réglée par un associé : écriture au journal AS « Associés », 401 du
  fournisseur au débit, 455 de l'associé au crédit ; paiement `origin = "associate"` (D9) ;
- note de frais (dépense avancée sans facture) : charge (et TVA déductible) au débit, 455 de
  l'associé au crédit, justificatif rangé sous `frais/AAAA/MM/` (D10) ;
- apport ou remboursement par la banque : écriture préremplie depuis la transaction
  (512 / 455), enregistrée et rapprochée par l'éditeur d'écritures habituel ;
- relevé du compte courant et soldes à la fin de chaque exercice.

Rien n'est écrit dans Qonto (Q7). Les écritures portent `source = "ASSOCIATE"` et une référence
de pièce (`PURCHASE_PAYMENT:<id>`, `EXPENSE:<id>`).
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from app.extensions import db
from app.models import (
    Account, Associate, BankTransaction, FiscalYear, Journal, JournalEntry, JournalLine, Purchase, PurchasePayment,
)
from app.models.associate import AssociateExpense
from app.services import attachments, catalog
from app.services.ledger import LedgerError, delete_entries, post_entry
from app.services.purchase_posting import fiscal_year_for, supplier_account, vat_account

JOURNAL = ("AS", "Associés")
SOURCE = "ASSOCIATE"


class OperationError(ValueError):
    def __init__(self, message, field=None):
        super().__init__(message)
        self.field = field


def journal() -> Journal:
    found = Journal.query.filter_by(code=JOURNAL[0]).first()
    if found is None:
        found = Journal(code=JOURNAL[0], label=JOURNAL[1])
        db.session.add(found)
        db.session.flush()
    return found


def _open_year(day: date, field=None) -> FiscalYear:
    fy = fiscal_year_for(day)
    if fy is None:
        raise OperationError(f"Aucun exercice ne couvre le {day:%d/%m/%Y}.", field)
    if fy.closed:
        raise OperationError(f"L'exercice « {fy.label} » est clôturé.", field)
    return fy


def _date(value, field) -> date:
    try:
        return date.fromisoformat(str(value or ""))
    except ValueError:
        raise OperationError("Date invalide.", field) from None


def _associate(value) -> Associate:
    try:
        associate = db.session.get(Associate, int(value))
    except (TypeError, ValueError):
        associate = None
    if associate is None:
        raise OperationError("Choisissez un associé.", "associate_id")
    return associate


# ------------------------------------------------------------------ facture réglée par un associé

def payment_blocker(p: Purchase) -> str | None:
    """Motif qui empêche de régler la facture par un associé ; None si c'est possible."""
    if p.journal_entry_id is None:
        return "La facture n'est pas comptabilisée : complétez-la d'abord."
    if p.is_credit_note:
        return "Un avoir ne se règle pas par un associé."
    if p.entity is None:
        return "La facture n'a pas de fournisseur."
    if p.payments:
        return "La facture a déjà un règlement."
    return None


def pay_purchase(p: Purchase, associate_id, paid_on) -> PurchasePayment:
    """Règle la facture par le compte courant de l'associé (commit) ; OperationError sinon."""
    blocker = payment_blocker(p)
    if blocker:
        raise OperationError(blocker)
    associate = _associate(associate_id)
    day = _date(paid_on, "paid_on")
    fy = _open_year(day, "paid_on")
    try:
        payment = PurchasePayment(purchase=p, origin="associate", associate=associate)
        db.session.add(payment)
        db.session.flush()
        label = f"Règlement {p.entity.name} — {p.invoice_number or 'sans numéro'} par {associate.name}"[:255]
        entry = post_entry(fy.id, journal().id, day, label[:500], [
            {"account_id": supplier_account(p.entity).id, "label": label, "debit_cents": p.total_cents, "credit_cents": 0},
            {"account_id": associate.account_id, "label": label, "debit_cents": 0, "credit_cents": p.total_cents},
        ], source=SOURCE, source_ref=f"PURCHASE_PAYMENT:{payment.id}", commit=False)
        payment.journal_entry_id = entry.id
        db.session.commit()
    except LedgerError as exc:
        db.session.rollback()
        raise OperationError(str(exc)) from None
    return payment


def unpay_purchase(payment: PurchasePayment) -> None:
    """Défait le règlement par un associé : écriture supprimée (exercice ouvert), paiement retiré."""
    if payment.origin != "associate":
        raise OperationError("Ce règlement n'est pas celui d'un associé.")
    if payment.journal_entry is not None and payment.journal_entry.fiscal_year.closed:
        raise OperationError("Exercice clôturé : le règlement ne peut plus être défait.")
    entry_id = payment.journal_entry_id
    db.session.delete(payment)
    db.session.flush()
    if entry_id is not None:
        results = delete_entries([entry_id])
        if results[0]["status"] != "ok":
            db.session.rollback()
            raise OperationError(results[0]["message"])
    else:
        db.session.commit()


# ------------------------------------------------------------------ notes de frais

def _amount(value, field, required=True) -> int | None:
    text = str(value if value is not None else "").replace(" ", "").replace(" ", "").replace("€", "").replace(",", ".")
    if not text:
        if required:
            raise OperationError("Montant obligatoire.", field)
        return None
    try:
        return int((Decimal(text) * 100).quantize(Decimal("1")))
    except InvalidOperation:
        raise OperationError("Montant invalide.", field) from None


def create_expense(data: dict, token: str | None = None) -> AssociateExpense:
    """Note de frais : `{associate_id, expense_date, label, account_code (6…), untaxed, vat_rate?, vat?}`."""
    associate = _associate(data.get("associate_id"))
    day = _date(data.get("expense_date"), "expense_date")
    label = str(data.get("label") or "").strip()[:255]
    if not label:
        raise OperationError("Libellé obligatoire.", "label")
    code = str(data.get("account_code") or "").strip()
    account = Account.query.filter_by(code=code, is_header=False).first() if code else None
    if account is None or not code.startswith("6"):
        raise OperationError("Compte de charge (6…) du plan comptable attendu.", "account_code")
    untaxed = _amount(data.get("untaxed"), "untaxed")
    if untaxed <= 0:
        raise OperationError("Montant HT positif attendu.", "untaxed")
    try:
        rate = catalog.parse_rate_bp(data.get("vat_rate"))
    except ValueError as exc:
        raise OperationError(str(exc), "vat_rate") from None
    vat = _amount(data.get("vat"), "vat", required=False)
    if vat is None:
        vat = round(untaxed * rate / 10000) if rate else 0
    if vat < 0:
        raise OperationError("TVA positive attendue.", "vat")
    fy = _open_year(day, "expense_date")
    vat_gl = vat_account() if vat else None
    if vat and vat_gl is None:
        raise OperationError("Compte de TVA déductible (44566) absent du plan comptable.", "vat")
    total = untaxed + vat
    try:
        expense = AssociateExpense(associate=associate, expense_date=day, label=label, account=account,
                                   untaxed_cents=untaxed, vat_rate_bp=rate, vat_cents=vat, total_cents=total)
        db.session.add(expense)
        db.session.flush()
        text = f"Note de frais {associate.name} — {label}"[:255]
        lines = [{"account_id": account.id, "label": text, "debit_cents": untaxed, "credit_cents": 0}]
        if vat:
            lines.append({"account_id": vat_gl.id, "label": text, "debit_cents": vat, "credit_cents": 0})
        lines.append({"account_id": associate.account_id, "label": text, "debit_cents": 0, "credit_cents": total})
        entry = post_entry(fy.id, journal().id, day, text, lines, source=SOURCE,
                           source_ref=f"EXPENSE:{expense.id}", commit=False)
        expense.journal_entry_id = entry.id
        if token:
            attachments.store(expense, token, folder="frais", day=day)
        db.session.commit()
    except LedgerError as exc:
        db.session.rollback()
        raise OperationError(str(exc)) from None
    except Exception:
        db.session.rollback()
        raise
    return expense


def delete_expense(expense: AssociateExpense) -> None:
    if expense.journal_entry is not None and expense.journal_entry.fiscal_year.closed:
        raise OperationError("Exercice clôturé : la note de frais ne peut plus être supprimée.")
    path = attachments.path_of(expense)
    entry_id = expense.journal_entry_id
    db.session.delete(expense)
    db.session.flush()
    if entry_id is not None:
        results = delete_entries([entry_id])
        if results[0]["status"] != "ok":
            db.session.rollback()
            raise OperationError(results[0]["message"])
    else:
        db.session.commit()
    if path is not None:
        path.unlink(missing_ok=True)


def expense_payload(e: AssociateExpense) -> dict:
    entry = e.journal_entry
    return {
        "id": e.id, "associate_id": e.associate_id, "associate": e.associate.name,
        "expense_date": e.expense_date.isoformat(), "label": e.label, "account_code": e.account.code,
        "account_label": e.account.label, "untaxed_cents": e.untaxed_cents, "vat_cents": e.vat_cents,
        "vat_rate": catalog.format_rate(e.vat_rate_bp).replace(" %", ""), "total_cents": e.total_cents,
        "attachment": ({"name": e.attachment_name, "url": f"/api/v1/associate-expenses/{e.id}/attachment"}
                       if e.attachment_path else None),
        "entry": {"id": entry.id, "reference": entry.reference} if entry else None,
    }


# ------------------------------------------------------------------ banque

def bank_entry_lines(bt: BankTransaction, associate: Associate) -> list[dict]:
    """Lignes préremplies : apport (entrée d'argent) 512 / 455, remboursement 455 / 512."""
    amount, inflow = abs(bt.amount_cents), bt.amount_cents >= 0
    label = f"{'Apport' if inflow else 'Remboursement'} compte courant — {associate.name}"
    return [
        {"account": bt.bank_account.account, "label": bt.label or label,
         "debit_cents": amount if inflow else 0, "credit_cents": 0 if inflow else amount},
        {"account": associate.account, "label": label,
         "debit_cents": 0 if inflow else amount, "credit_cents": amount if inflow else 0},
    ]


# ------------------------------------------------------------------ relevé

ORIGINS = (("PURCHASE_PAYMENT:", "Facture réglée"), ("EXPENSE:", "Note de frais"), ("INTEREST:", "Intérêts"),
           ("OPENING:", "Reprise"))


def _origin(entry: JournalEntry) -> str:
    ref = entry.source_ref or ""
    for prefix, label in ORIGINS:
        if ref.startswith(prefix):
            return label
    if entry.source == "ALLOCATION":
        return "Affectation du résultat"
    if any(line.account.account_type == "BANK" or line.account.code.startswith("512") for line in entry.lines):
        return "Banque"
    return "Écriture"


def statement(associate: Associate, start: date | None = None, end: date | None = None) -> dict:
    """Lignes du compte courant (créditeur positif) avec solde progressif et origine."""
    query = db.session.query(JournalLine, JournalEntry).join(JournalEntry) \
        .filter(JournalLine.account_id == associate.account_id)
    opening = 0
    if start is not None:
        before = query.filter(JournalEntry.entry_date < start).all()
        opening = sum(line.credit_cents - line.debit_cents for line, _e in before)
        query = query.filter(JournalEntry.entry_date >= start)
    if end is not None:
        query = query.filter(JournalEntry.entry_date <= end)
    rows, running = [], opening
    for line, entry in query.order_by(JournalEntry.entry_date, JournalEntry.id, JournalLine.id).all():
        amount = line.credit_cents - line.debit_cents
        running += amount
        rows.append({"date": entry.entry_date.isoformat(), "entry_id": entry.id, "reference": entry.reference,
                     "label": line.label or entry.description or "", "origin": _origin(entry),
                     "amount_cents": amount, "balance_cents": running})
    return {"opening_cents": opening, "lines": rows, "closing_cents": running}


def balances_by_fiscal_year() -> dict:
    """Solde de chaque compte courant à la fin de chaque exercice (graphique empilé)."""
    from app.services.associates import balance

    years = FiscalYear.query.order_by(FiscalYear.start_date).all()
    associates_ = Associate.query.all()
    return {
        "years": [fy.label for fy in years],
        "series": [{"name": a.name, "values": [balance(a.account_id, fy.end_date) for fy in years]}
                   for a in sorted(associates_, key=lambda a: a.name)],
    }


# ------------------------------------------------------------------ intérêts (clôture)

INTEREST_ACCOUNT = ("6615", "Intérêts des comptes courants et des dépôts créditeurs")
DAYS_PER_YEAR = 365  # exact / 365


def interest_account() -> Account:
    """Compte 6615, créé s'il manque (absent du plan SCI) ; sans commit."""
    account = Account.query.filter_by(code=INTEREST_ACCOUNT[0], is_header=False).first()
    if account is None:
        parent = next((a for code in ("661", "66") if (a := Account.query.filter_by(code=code).first())), None)
        account = Account(code=INTEREST_ACCOUNT[0], label=INTEREST_ACCOUNT[1], account_type="EXPENSE", parent=parent)
        db.session.add(account)
        db.session.flush()
    return account


def rate_of(associate: Associate) -> int:
    """Taux annuel (points de base) : celui de l'associé, sinon celui de la structure."""
    from app.services import organization

    if associate.interest_rate_bp is not None:
        return associate.interest_rate_bp
    return organization.get().associate_interest_rate_bp or 0


def _interest_ref(fy: FiscalYear, associate_id=None) -> str:
    return f"INTEREST:{fy.id}:" + ("" if associate_id is None else str(associate_id))


def interest_entries(fy: FiscalYear) -> list[JournalEntry]:
    return (JournalEntry.query.filter(JournalEntry.source == SOURCE,
                                      JournalEntry.source_ref.like(_interest_ref(fy) + "%"))
            .order_by(JournalEntry.id).all())


def _daily_credit_sum(associate: Associate, fy: FiscalYear) -> int:
    """Σ des soldes créditeurs de fin de journée (centimes × jours), hors intérêts de l'exercice."""
    excluded = {e.id for e in interest_entries(fy)}
    rows = db.session.query(JournalEntry.id, JournalEntry.entry_date, JournalLine.credit_cents - JournalLine.debit_cents) \
        .join(JournalLine).filter(JournalLine.account_id == associate.account_id,
                                  JournalEntry.entry_date <= fy.end_date).all()
    balance = sum(amount for entry_id, day, amount in rows if day < fy.start_date and entry_id not in excluded)
    by_day: dict[date, int] = {}
    for entry_id, day, amount in rows:
        if day >= fy.start_date and entry_id not in excluded:
            by_day[day] = by_day.get(day, 0) + amount
    total, day = 0, fy.start_date
    while day <= fy.end_date:
        balance += by_day.get(day, 0)
        total += max(balance, 0)
        day += timedelta(days=1)
    return total


def interest_preview(fy: FiscalYear) -> dict:
    """Intérêts par associé sur l'exercice : taux, solde créditeur moyen, intérêts (arrondis au centime)."""
    days = (fy.end_date - fy.start_date).days + 1
    rows = []
    for associate in sorted(Associate.query.all(), key=lambda a: a.name):
        rate = rate_of(associate)
        cents_days = _daily_credit_sum(associate, fy)
        interest = round(cents_days * rate / 10000 / DAYS_PER_YEAR) if rate else 0
        rows.append({"associate_id": associate.id, "name": associate.name, "account_code": associate.account.code,
                     "rate": catalog.format_rate(rate).replace(" %", "") if rate else "0",
                     "average_balance_cents": round(cents_days / days), "interest_cents": interest})
    posted = interest_entries(fy)
    return {"rows": rows, "total_cents": sum(r["interest_cents"] for r in rows),
            "entries": [{"id": e.id, "reference": e.reference,
                         "amount_cents": sum(l.credit_cents for l in e.lines if l.account.code.startswith("455"))}
                        for e in posted]}


def post_interest(fy: FiscalYear) -> list[JournalEntry]:
    """Passe (ou remplace) les intérêts de l'exercice : une écriture AS par associé au dernier jour,
    6615 au débit, 455 de l'associé au crédit. Exercice ouvert seulement ; taux nul : rien."""
    if fy.closed:
        raise OperationError(f"L'exercice « {fy.label} » est clôturé.")
    old = [e.id for e in interest_entries(fy)]
    if old:
        results = delete_entries(old)
        failed = [r for r in results if r["status"] != "ok"]
        if failed:
            raise OperationError(failed[0].get("message") or "Écritures d'intérêts non supprimées.")
    rows = [r for r in interest_preview(fy)["rows"] if r["interest_cents"] > 0]
    entries = []
    try:
        account = interest_account() if rows else None
        for row in rows:
            associate = db.session.get(Associate, row["associate_id"])
            label = f"Intérêts du compte courant {fy.label} — {associate.name} ({row['rate']} %)"[:255]
            entries.append(post_entry(fy.id, journal().id, fy.end_date, label, [
                {"account_id": account.id, "label": label, "debit_cents": row["interest_cents"], "credit_cents": 0},
                {"account_id": associate.account_id, "label": label, "debit_cents": 0, "credit_cents": row["interest_cents"]},
            ], source=SOURCE, source_ref=_interest_ref(fy, associate.id), commit=False))
        db.session.commit()
    except LedgerError as exc:
        db.session.rollback()
        raise OperationError(str(exc)) from None
    return entries
