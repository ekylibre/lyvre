"""Versements d'aides reçus sur les relevés (lot AG3.b, claudedocs/design_aides_pac.md § 5, AGD20 Q-P6).

- Payeurs reconnus aux mots du libellé ou de la contrepartie (`data/aids/payers.yml`, normalisation de l'échéancier).
- Un crédit est **proposé** contre les dossiers ouverts, puis rattaché par l'utilisateur, jamais automatiquement :
  un virement de l'ASP réunit souvent plusieurs aides. Il peut se ventiler sur plusieurs dossiers, sans dépasser
  son montant.
- Un virement pas encore comptabilisé l'est au rattachement, entièrement ventilé : une ligne par dossier sur son
  compte (aide mixte : part d'investissement en 131, reste sur le compte d'exploitation), banque au débit. En
  comptabilité simplifiée, sur la catégorie de recette du compte (ou d'un compte parent).
- Un virement déjà comptabilisé n'est jamais réécrit : un compte différent de celui du dossier est signalé.
"""
from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml

from app.extensions import db
from app.models import Account, Aid, AidPayment, BankTransaction, FiscalYear
from app.services import aids
from app.services.aids import AidError

DATA = Path(__file__).resolve().parents[2] / "data" / "aids" / "payers.yml"
# Versements types → jour de l'année de campagne (avance d'octobre, solde de décembre) pour classer les dossiers.
TYPICAL = {"advance": (10, 16), "balance": (12, 1)}


@lru_cache(maxsize=1)
def payers() -> dict[str, tuple[str, ...]]:
    from app.services.deadlines import normalize

    raw = yaml.safe_load(DATA.read_text(encoding="utf-8"))["payers"]
    return {name: tuple(normalize(w) for w in words) for name, words in raw.items()}


def payer_of(tx: BankTransaction) -> str | None:
    """Payeur reconnu d'un virement (mot entier du libellé ou de la contrepartie), sinon None."""
    from app.services.deadlines import normalize

    text = f" {normalize(tx.label or '')} {normalize(tx.counterparty or '')} "
    for name, words in payers().items():
        if any(f" {w} " in text for w in words):
            return name
    return None


def allocated_cents(tx: BankTransaction) -> int:
    return sum(p.amount_cents for p in AidPayment.query.filter_by(bank_transaction_id=tx.id))


def _credit(tx_id) -> BankTransaction:
    tx = db.session.get(BankTransaction, tx_id) if isinstance(tx_id, int) and not isinstance(tx_id, bool) else None
    if tx is None:
        raise AidError("Transaction introuvable.", "bank_transaction_id", 404)
    if tx.amount_cents <= 0:
        raise AidError("Seul un virement reçu (crédit) se rattache à une aide.", "bank_transaction_id")
    if tx.is_reversed:
        raise AidError("Transaction annulée par la banque.", "bank_transaction_id", 409)
    return tx


def _distance(aid: Aid, day: date) -> int:
    try:
        kinds = aids.scheme(aid.scheme).get("payments") or []
    except AidError:
        kinds = []
    days = [abs((date(aid.campaign, *TYPICAL[k]) - day).days) for k in kinds if k in TYPICAL]
    return min(days) if days else 10 ** 4


def booked_accounts(tx: BankTransaction) -> list[str]:
    """Comptes de produit ou de subvention de l'écriture du virement (pièce de règle comprise)."""
    from app.services import rule_entries

    if tx.journal_line is None:
        return []
    entries = [tx.journal_line.entry]
    document = rule_entries.document_of(tx)
    if document is not None:
        entries.append(document)
    codes = {line.account.code for entry in entries for line in entry.lines
             if line.account is not None and line.account.code.startswith(("7", "13", "441"))}
    return sorted(codes)


def candidates(tx_id) -> dict:
    tx = _credit(tx_id)
    payer = payer_of(tx)
    free = tx.amount_cents - allocated_cents(tx)
    linked = {p.aid_id for p in AidPayment.query.filter_by(bank_transaction_id=tx.id)}
    rows = []
    for aid in Aid.query.filter(Aid.status.notin_(("refused", "closed"))):
        remaining = aids.acquired_cents(aid) - aids.paid_cents(aid)
        if remaining <= 0 and aid.id not in linked:
            continue
        match = bool(payer and aid.payer == payer)
        rows.append({"aid": aids.payload(aid, with_payments=False), "payer_match": match,
                     "suggested_cents": max(min(remaining, free), 0), "already_linked": aid.id in linked,
                     "_key": (not match, remaining != free, abs(remaining - free), _distance(aid, tx.transaction_date), aid.id)})
    rows.sort(key=lambda r: r.pop("_key"))
    return {"transaction": {"id": tx.id, "label": tx.label, "counterparty": tx.counterparty,
                            "transaction_date": tx.transaction_date.isoformat(), "amount_cents": tx.amount_cents,
                            "booked": tx.journal_line_id is not None or tx.reconciled,
                            "booked_accounts": booked_accounts(tx)},
            "payer": payer, "allocated_cents": tx.amount_cents - free, "free_cents": free, "items": rows}


def _lines_for(aid: Aid, amount: int) -> list[tuple[Account, int]]:
    """Ventilation d'un montant d'un dossier sur ses comptes (aide mixte : prorata de la part d'investissement)."""
    investment_account = aid.account
    if aid.grant_entry_id is not None and aid.nature in ("investment", "mixed"):
        from app.services.aid_grants import _account
        investment_account = _account("441")              # octroi passé (AG3.d) : le versement solde le 441
    if aid.nature != "mixed" or aid.operating_account is None:
        return [(investment_account, amount)]
    total = aids.acquired_cents(aid)
    if not total or aid.investment_share_cents is None:
        raise AidError(f"« {aid.label} » : saisissez la ventilation (part d'investissement) avant de comptabiliser.",
                       "allocations")
    investment = round(amount * aid.investment_share_cents / total)
    return [(acc, cents) for acc, cents in ((investment_account, investment), (aid.operating_account, amount - investment))
            if cents]


def _simple_account(account: Account) -> Account:
    """Comptabilité simplifiée : compte de la catégorie de recette du compte, ou d'un compte parent."""
    from app.models import SimpleCategory

    by_account = {c.account_id for c in SimpleCategory.query.filter_by(kind="income")}
    current = account
    while current is not None:
        if current.id in by_account:
            return current
        current = current.parent
    for length in range(len(account.code) - 1, 1, -1):          # plan chargé sans lien de parenté : par préfixe
        parent = Account.query.filter_by(code=account.code[:length], is_header=False).first()
        if parent is not None and parent.id in by_account:
            return parent
    raise AidError(f"Aucune catégorie de recette pour le compte {account.code} : créez-la dans Configuration › "
                   "Catégories, ou comptabilisez le virement depuis les opérations.", "allocations", 409)


def _book(tx: BankTransaction, parts: list[tuple[Aid, int]]) -> None:
    from app.services import simple_operations
    from app.services.ledger import post_entry
    from app.services.rule_entries import _journal, simple_mode

    fy = FiscalYear.query.filter(FiscalYear.start_date <= tx.transaction_date,
                                 FiscalYear.end_date >= tx.transaction_date).first()
    if fy is None:
        raise AidError(f"Aucun exercice ne couvre le {tx.transaction_date:%d/%m/%Y} : créez-le pour comptabiliser.",
                       "bank_transaction_id", 409)
    simple = simple_mode()
    label = (tx.label or "Versement d'aide")[:300]
    credits: dict[tuple[int, str | None], int] = {}
    for aid, amount in parts:
        for account, cents in _lines_for(aid, amount):
            account = _simple_account(account) if simple else account
            key = (account.id, aid.analytic_target)                 # lot AG8.c : affectation du dossier
            credits[key] = credits.get(key, 0) + cents
    bank_id = tx.bank_account.account_id
    lines = [{"account_id": bank_id, "label": label, "debit_cents": tx.amount_cents, "credit_cents": 0}]
    lines += [{"account_id": acc, "label": label, "debit_cents": 0, "credit_cents": cents,
               "analytic": target, "analytic_origin": "aid"} for (acc, target), cents in credits.items()]
    if simple:
        entry = post_entry(fy.id, simple_operations._journal("bank").id, tx.transaction_date, label, lines,  # noqa: SLF001
                           source=simple_operations.SOURCE_SIMPLE, commit=False)
    else:
        entry = post_entry(fy.id, _journal("BQ", "Banque").id, tx.transaction_date, label, lines,
                           source="QONTO_IMPORT" if tx.source == "qonto" else "OFX_IMPORT",
                           source_ref=f"FITID:{tx.fitid}", commit=False, auto_date=True)
    bank_line = next(l for l in entry.lines if l.account_id == bank_id)
    tx.journal_line_id, tx.reconciled = bank_line.id, True
    db.session.flush()


def link(tx_id, allocations, book: bool = False) -> dict:
    """Rattache un virement à un ou plusieurs dossiers (sans commit) ; `book` comptabilise un virement libre."""
    tx = _credit(tx_id)
    if not isinstance(allocations, list) or not allocations:
        raise AidError("Indiquez au moins un dossier et son montant.", "allocations")
    parts: list[tuple[Aid, int]] = []
    for row in allocations:
        if not isinstance(row, dict):
            raise AidError("Ventilation invalide.", "allocations")
        aid = db.session.get(Aid, row.get("aid_id")) if isinstance(row.get("aid_id"), int) else None
        if aid is None:
            raise AidError("Dossier introuvable.", "allocations", 404)
        if aid.status == "refused":
            raise AidError(f"« {aid.label} » est refusé : rien à y rattacher.", "allocations")
        amount = row.get("amount_cents")
        if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
            raise AidError("Montant positif attendu pour chaque dossier.", "allocations")
        kind = row.get("kind") or "other"
        if kind not in ("advance", "balance", "installment", "other"):
            raise AidError("Type de versement inconnu.", "allocations")
        parts.append((aid, amount))
        row["kind"] = kind
    if len({a.id for a, _ in parts}) != len(parts):
        raise AidError("Un même dossier figure deux fois.", "allocations")
    total = sum(amount for _, amount in parts)
    free = tx.amount_cents - allocated_cents(tx)
    if total > free:
        raise AidError(f"La ventilation ({total / 100:.2f} €) dépasse le montant restant du virement "
                       f"({free / 100:.2f} €).".replace(".", ","), "allocations")
    booked = tx.journal_line_id is not None or tx.reconciled
    if book:
        if booked:
            raise AidError("Virement déjà comptabilisé : il est rattaché sans nouvelle écriture.", "book", 409)
        if allocated_cents(tx) or total != tx.amount_cents:
            raise AidError("Pour comptabiliser, ventilez la totalité du virement.", "allocations")
        _book(tx, parts)
    for (aid, amount), row in zip(parts, allocations):
        db.session.add(AidPayment(aid=aid, paid_on=tx.transaction_date, amount_cents=amount, kind=row["kind"],
                                  bank_transaction_id=tx.id))
    db.session.flush()
    return {"booked": book, "warnings": mismatches(tx, [a for a, _ in parts])}


def mismatches(tx: BankTransaction, linked: list[Aid]) -> list[str]:
    """Virement comptabilisé sur un autre compte que celui de ses dossiers (signalé, jamais réécrit)."""
    codes = booked_accounts(tx)
    if not codes:
        return []
    out = []
    for aid in linked:
        expected = {aid.account.code} | ({aid.operating_account.code} if aid.operating_account else set())
        if aid.grant_entry_id is not None:
            expected.add("441")
        if not expected & set(codes):
            out.append(f"« {aid.label} » est en {', '.join(sorted(expected))}, mais le virement est comptabilisé en "
                       f"{', '.join(codes)} : corrigez l'écriture si besoin.")
    return out


def unlinked_credits(start: date, end: date) -> list[BankTransaction]:
    """Virements reçus d'un payeur d'aides, sur la période, rattachés à aucun dossier."""
    linked = db.session.query(AidPayment.bank_transaction_id).filter(AidPayment.bank_transaction_id.isnot(None))
    rows = (BankTransaction.query.filter(BankTransaction.amount_cents > 0, BankTransaction.is_reversed.is_(False),
                                         BankTransaction.transaction_date >= start,
                                         BankTransaction.transaction_date <= end,
                                         BankTransaction.id.notin_(linked)).all())
    return [tx for tx in rows if payer_of(tx)]
