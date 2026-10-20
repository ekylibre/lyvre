"""Synchronisation Qonto → comptes et transactions bancaires.

Rattachement des comptes : un compte Qonto est lié à un `BankAccount`
(`qonto_account_id`), existant (même IBAN proposé d'office) ou créé avec son
compte comptable. Seuls les comptes rattachés sont synchronisés.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.extensions import db
from app.models import BankAccount, FiscalYear


class QontoLinkError(ValueError):
    """Rattachement impossible (message affichable)."""


@dataclass(frozen=True)
class QontoAccountView:
    qonto_id: str
    name: str
    iban: str | None
    status: str
    main: bool
    balance_cents: int | None
    linked: BankAccount | None     # compte bancaire déjà rattaché
    proposed: BankAccount | None   # compte non rattaché de même IBAN

    @property
    def is_closed(self) -> bool:
        return self.status != "active"


def normalize_iban(iban) -> str | None:
    value = (iban or "").replace(" ", "").upper()
    return value or None


def default_sync_from(today=None) -> date:
    """Début de l'exercice ouvert qui contient aujourd'hui, sinon 1er janvier."""
    today = today or date.today()
    fy = (
        FiscalYear.query
        .filter(FiscalYear.start_date <= today, FiscalYear.end_date >= today,
                FiscalYear.closed.is_(False))
        .order_by(FiscalYear.start_date.desc())
        .first()
    )
    return fy.start_date if fy else date(today.year, 1, 1)


def list_accounts(qonto_accounts: list[dict]) -> list[QontoAccountView]:
    """Comptes Qonto (réponse de l'API) avec leur rattachement local."""
    bank_accounts = BankAccount.query.all()
    by_qonto_id = {ba.qonto_account_id: ba for ba in bank_accounts if ba.qonto_account_id}
    unlinked_by_iban = {
        normalize_iban(ba.iban): ba for ba in bank_accounts
        if not ba.qonto_account_id and normalize_iban(ba.iban)
    }
    views = []
    for acc in qonto_accounts:
        iban = normalize_iban(acc.get("iban"))
        linked = by_qonto_id.get(acc["id"])
        views.append(QontoAccountView(
            qonto_id=acc["id"],
            name=acc.get("name") or "Compte Qonto",
            iban=iban,
            status=acc.get("status") or "active",
            main=bool(acc.get("main")),
            balance_cents=acc.get("balance_cents"),
            linked=linked,
            proposed=None if linked else unlinked_by_iban.get(iban),
        ))
    return views


def link_account(qonto_account: dict, *, bank_account_id=None, label=None,
                 gl_account_id=None, sync_from=None) -> BankAccount:
    """Rattache un compte Qonto à un compte bancaire existant, ou en crée un."""
    qonto_id = qonto_account["id"]
    already = BankAccount.query.filter_by(qonto_account_id=qonto_id).first()
    if already is not None:
        raise QontoLinkError(f"Ce compte Qonto est déjà rattaché à « {already.label} ».")

    if bank_account_id:
        bank_account = db.session.get(BankAccount, bank_account_id)
        if bank_account is None:
            raise QontoLinkError("Compte bancaire introuvable.")
        if bank_account.qonto_account_id:
            raise QontoLinkError(f"« {bank_account.label} » est déjà rattaché à un autre compte Qonto.")
        if not bank_account.iban:
            bank_account.iban = normalize_iban(qonto_account.get("iban"))
    else:
        label = (label or "").strip() or f"Qonto — {qonto_account.get('name') or 'compte'}"
        if not gl_account_id:
            raise QontoLinkError("Choisissez le compte comptable (classe 512) du nouveau compte.")
        bank_account = BankAccount(
            label=label,
            iban=normalize_iban(qonto_account.get("iban")),
            account_id=gl_account_id,
        )
        db.session.add(bank_account)

    bank_account.qonto_account_id = qonto_id
    bank_account.qonto_sync_from = sync_from or default_sync_from()
    bank_account.qonto_synced_at = None
    db.session.commit()
    return bank_account


def unlink_account(bank_account: BankAccount) -> None:
    """Détache le compte Qonto ; les transactions déjà importées sont conservées."""
    bank_account.qonto_account_id = None
    bank_account.qonto_synced_at = None
    db.session.commit()


def set_sync_from(bank_account: BankAccount, sync_from: date) -> None:
    """Change la date de début. Si elle recule, la prochaine synchro repart de zéro
    (les transactions déjà importées ne sont pas dupliquées)."""
    if bank_account.qonto_sync_from and sync_from < bank_account.qonto_sync_from:
        bank_account.qonto_synced_at = None
    bank_account.qonto_sync_from = sync_from
    db.session.commit()
