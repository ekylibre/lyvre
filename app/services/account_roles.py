"""Comptes par rôle (lot F3) : les comptes que Lyvre choisit seul (écart de lettrage, puis dotations,
cessions…) ne sont pas codés en dur ; défauts par référentiel dans `data/account_roles.json`,
choix de l'administrateur dans `account_roles`."""
import json
from functools import lru_cache
from pathlib import Path

from app.extensions import db
from app.models import Account, AccountRole

ROLES_FILE = Path(__file__).resolve().parents[2] / "data" / "account_roles.json"


class RoleError(Exception):
    pass


@lru_cache(maxsize=1)
def definitions() -> dict:
    return json.loads(ROLES_FILE.read_text(encoding="utf-8"))["roles"]


def _chart() -> str:
    try:
        from app.tenant import current_chart
        return current_chart()
    except RuntimeError:  # hors requête (tâche de fond)
        return "asso"


def default_account(role: str, chart: str | None = None) -> Account | None:
    """Premier code du référentiel présent et utilisable, sinon son premier sous-compte."""
    for code in definitions()[role].get(chart or _chart(), []):
        account = Account.query.filter_by(code=code).first()
        if account is not None and not account.is_header:
            return account
        child = (Account.query.filter(Account.code.like(f"{code}%"), Account.is_header.is_(False))
                 .order_by(Account.code).first())
        if child is not None:
            return child
    return None


def account_for(role: str) -> Account:
    chosen = db.session.get(AccountRole, role)
    account = chosen.account if chosen else default_account(role)
    if account is None:
        raise RoleError(f"Aucun compte pour « {definitions()[role]['label']} » : choisissez-le dans "
                        "Configuration › Comptes par défaut.")
    return account


def listing() -> list[dict]:
    rows = []
    for role, spec in definitions().items():
        chosen = db.session.get(AccountRole, role)
        default = default_account(role)
        account = chosen.account if chosen else default
        rows.append({"role": role, "label": spec["label"], "custom": chosen is not None,
                     "account": {"id": account.id, "code": account.code, "label": account.label} if account else None,
                     "default_code": default.code if default else None})
    return rows


def set_role(role: str, account_id: int | None) -> None:
    if role not in definitions():
        raise RoleError("Rôle inconnu.")
    chosen = db.session.get(AccountRole, role)
    if account_id is None:
        if chosen is not None:
            db.session.delete(chosen)
        return
    account = db.session.get(Account, account_id)
    if account is None or account.is_header:
        raise RoleError("Compte introuvable ou de regroupement.")
    if chosen is None:
        db.session.add(AccountRole(role=role, account_id=account.id))
    else:
        chosen.account_id = account.id
