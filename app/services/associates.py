"""Associés d'une société : option de l'instance, associés et comptes courants (lot A1).

Option `organization.has_associates` (claudedocs/design_associes.md, D1–D2). Un associé est une
entité avec un compte courant, sous-compte 455 proposé de 4551001 à 4551999 (D4) ; son solde se
lit dans le grand livre (créditeur positif : la société doit à l'associé). La situation des parts
à une date est la somme des lignes du registre jusqu'à cette date.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from flask import g

from app.extensions import db
from app.models import Account, Associate, Entity, JournalEntry, JournalLine, PurchasePayment
from app.models.associate import AssociateExpense, PART_NATURES, ShareMovement, ShareMovementLine
from app.services.catalog import format_rate, parse_rate_bp
from app.services.counterparties import name_key

ACCOUNT_PREFIX = "4551"
FIRST_NUMBER, LAST_NUMBER = 1, 999
NATURES = tuple(code for code, _ in PART_NATURES)
MAX_RATE_BP = 2000


class AssociateError(ValueError):
    def __init__(self, message, field=None):
        super().__init__(message)
        self.field = field


def enabled() -> bool:
    """Option de l'instance courante (base méta)."""
    instance = getattr(g, "current_instance", None)
    return bool(instance is not None and instance.has_associates)


def next_account_code() -> str:
    """Premier sous-compte libre 4551001… 4551999."""
    taken = {code for (code,) in db.session.query(Account.code).filter(Account.code.like(f"{ACCOUNT_PREFIX}___"))}
    for number in range(FIRST_NUMBER, LAST_NUMBER + 1):
        code = f"{ACCOUNT_PREFIX}{number:03d}"
        if code not in taken:
            return code
    raise AssociateError("Plus de sous-compte libre de 4551001 à 4551999 : indiquez un compte 455.", "account_code")


def parse_rate(value) -> int | None:
    """Taux annuel en % (« 1,5 ») → points de base ; vide → None."""
    if value is None or str(value).strip() == "":
        return None
    try:
        rate = parse_rate_bp(value)
    except ValueError:
        rate = None
    if rate is None or not 0 <= rate <= MAX_RATE_BP:
        raise AssociateError("Taux d'intérêt de 0 à 20 %.", "interest_rate")
    return rate


def _account(code: str | None, entity: Entity, current: Account | None = None) -> Account:
    """Compte courant : code donné (455…, créé s'il manque) ou prochain 4551…."""
    code = (code or "").strip() or (current.code if current else next_account_code())
    if not code.startswith("455") or not code.isdigit() or len(code) > 20:
        raise AssociateError("Le compte courant est un compte 455 (chiffres seulement).", "account_code")
    account = Account.query.filter_by(code=code).first()
    if account is None:
        parent = Account.query.filter_by(code="455").first()
        account = Account(code=code, label=f"Compte courant — {entity.name}"[:255], account_type="TIERS",
                          parent=parent)
        db.session.add(account)
    elif account.is_header:
        raise AssociateError(f"Le compte {code} est un compte de regroupement.", "account_code")
    taken = Associate.query.filter_by(account_id=account.id).first() if account.id else None
    if taken is not None and (current is None or account.id != current.id):
        raise AssociateError(f"Le compte {code} est déjà celui de {taken.name}.", "account_code")
    return account


def _entity(data) -> Entity:
    if data.get("entity_id"):
        entity = db.session.get(Entity, int(data["entity_id"]))
        if entity is None:
            raise AssociateError("Entité introuvable.", "entity_id")
        return entity
    name = str(data.get("new_name") or "").strip()
    if not name:
        raise AssociateError("Choisissez une entité ou indiquez le nom du nouvel associé.", "entity_id")
    key = name_key(name)
    existing = next((e for e in Entity.query.order_by(Entity.id) if name_key(e.name) == key), None)
    if existing is not None:
        return existing
    entity = Entity(name=name[:200], entity_type="AUTRE")
    db.session.add(entity)
    return entity


def create(data: dict) -> Associate:
    """`{entity_id | new_name, account_code?, interest_rate?, notes?, is_manager?}` → associé (commit) ;
    AssociateError sans rien laisser en session."""
    try:
        with db.session.no_autoflush:
            rate = parse_rate(data.get("interest_rate"))
            entity = _entity(data)
            if entity.id is not None and Associate.query.filter_by(entity_id=entity.id).first():
                raise AssociateError(f"{entity.name} est déjà associé.", "entity_id")
            account = _account(data.get("account_code"), entity)
            associate = Associate(entity=entity, account=account, interest_rate_bp=rate,
                                  notes=(str(data.get("notes") or "").strip() or None),
                                  is_manager=bool(data.get("is_manager")))
            db.session.add(associate)
        extra = {k: data[k] for k in ("is_operator", "young_farmer_since", "profit_share") if k in data}
        if extra:                                               # lot AG6.a : champs agricoles (commit inclus)
            _update(associate, extra)
        db.session.commit()
    except AssociateError:
        db.session.rollback()
        raise
    return associate


def update(associate: Associate, data: dict) -> Associate:
    """Compte courant (tant qu'il n'a pas d'écriture), taux, notes, gérant."""
    try:
        _update(associate, data)
    except AssociateError:
        db.session.rollback()
        raise
    return associate


def _update(associate: Associate, data: dict) -> None:
    if "account_code" in data and (data.get("account_code") or "").strip() != associate.account.code:
        if has_entries(associate.account):
            raise AssociateError("Le compte courant a des écritures : il ne peut plus changer.", "account_code")
        associate.account = _account(data.get("account_code"), associate.entity, associate.account)
    if "interest_rate" in data:
        associate.interest_rate_bp = parse_rate(data.get("interest_rate"))
    if "notes" in data:
        associate.notes = str(data.get("notes") or "").strip() or None
    if "is_manager" in data:
        associate.is_manager = bool(data.get("is_manager"))
    if "is_operator" in data:                                # lot AG6.a : associé exploitant
        associate.is_operator = bool(data.get("is_operator"))
    if "young_farmer_since" in data:
        value = data.get("young_farmer_since")
        try:
            associate.young_farmer_since = date.fromisoformat(str(value)[:10]) if value else None
        except ValueError:
            raise AssociateError("Date de la première aide JA : AAAA-MM-JJ.", "young_farmer_since") from None
    if "profit_share" in data:                               # % des droits aux bénéfices (statuts), vide : parts
        raw = str(data.get("profit_share") or "").strip().replace(",", ".").replace("%", "")
        try:
            share = round(float(raw) * 100) if raw else None
        except ValueError:
            raise AssociateError("Part des droits aux bénéfices : pourcentage attendu.", "profit_share") from None
        if share is not None and not 0 <= share <= 10000:
            raise AssociateError("Part des droits aux bénéfices entre 0 et 100 %.", "profit_share")
        associate.profit_share_bp = share
    db.session.commit()


def has_entries(account: Account) -> bool:
    return db.session.query(JournalLine.id).filter(JournalLine.account_id == account.id).first() is not None


def delete_blockers(associate: Associate) -> list[str]:
    reasons = []
    if ShareMovementLine.query.filter_by(associate_id=associate.id).first():
        reasons.append("il figure dans le registre des parts")
    if has_entries(associate.account):
        reasons.append("son compte courant a des écritures")
    if PurchasePayment.query.filter_by(associate_id=associate.id).first() or \
            AssociateExpense.query.filter_by(associate_id=associate.id).first():
        reasons.append("il a réglé des factures ou des notes de frais")
    return reasons


def delete(associate: Associate) -> None:
    """Supprime l'associé (l'entité et le compte restent) ; refusé s'il a un historique."""
    reasons = delete_blockers(associate)
    if reasons:
        raise AssociateError("Suppression impossible : " + " ; ".join(reasons) + ".")
    db.session.delete(associate)
    db.session.commit()


# ------------------------------------------------------------------ situation

def holdings(at: date | None = None) -> dict[int, dict[str, int]]:
    """Parts par associé et par nature à la date (incluse) ; toutes dates si `at` est None."""
    query = db.session.query(ShareMovementLine.associate_id, ShareMovementLine.nature,
                             db.func.sum(ShareMovementLine.parts)).join(ShareMovement)
    if at is not None:
        query = query.filter(ShareMovement.movement_date <= at)
    result: dict[int, dict[str, int]] = defaultdict(lambda: dict.fromkeys(NATURES, 0))
    for associate_id, nature, parts in query.group_by(ShareMovementLine.associate_id, ShareMovementLine.nature):
        result[associate_id][nature] = int(parts or 0)
    return result


def capital_parts(held: dict[int, dict[str, int]]) -> int:
    """Parts du capital : une part démembrée compte une fois (pleine propriété + nue-propriété)."""
    return sum(h["full"] + h["bare"] for h in held.values())


def balance(account_id: int, at: date | None = None) -> int:
    """Solde du compte courant, créditeur positif (la société doit à l'associé)."""
    query = db.session.query(db.func.coalesce(db.func.sum(JournalLine.credit_cents - JournalLine.debit_cents), 0)) \
        .join(JournalEntry).filter(JournalLine.account_id == account_id)
    if at is not None:
        query = query.filter(JournalEntry.entry_date <= at)
    return int(query.scalar() or 0)


def summary(associate: Associate, held: dict[int, dict[str, int]], total_parts: int, at: date | None) -> dict:
    parts = held.get(associate.id, dict.fromkeys(NATURES, 0))
    rate = associate.interest_rate_bp
    return {
        "id": associate.id, "name": associate.name, "entity_id": associate.entity_id,
        "account_code": associate.account.code, "account_label": associate.account.label,
        "parts": parts,
        # % du capital détenu par nature (une part démembrée compte chez l'usufruitier et le nu-propriétaire).
        "percent": {n: round(100 * parts[n] / total_parts, 2) if total_parts else 0.0 for n in NATURES},
        "balance_cents": balance(associate.account_id, at),
        "interest_rate": format_rate(rate).replace(" %", "") if rate is not None else "",
        "notes": associate.notes,
        "is_manager": associate.is_manager,
        "is_operator": associate.is_operator,
        "young_farmer_since": associate.young_farmer_since.isoformat() if associate.young_farmer_since else None,
        "profit_share": str(associate.profit_share_bp / 100).replace(".", ",") if associate.profit_share_bp is not None else "",
        "email": associate.entity.email,
        "is_out": not any(parts.values()),
    }


def listing(at: date | None = None) -> dict:
    held = holdings(at)
    total = capital_parts(held)
    associates = Associate.query.join(Entity).order_by(Entity.name).all()
    rows = [summary(a, held, total, at) for a in associates]
    accounts_total = sum(r["balance_cents"] for r in rows)
    return {"items": rows, "total_parts": total, "balances_total_cents": accounts_total}


# ------------------------------------------------------------------ affectation du résultat

def allocation_proposal(fy) -> dict:
    """Répartition du résultat à affecter entre les associés, au prorata de leurs parts en pleine
    propriété et en usufruit à la date de clôture (les nus-propriétaires n'y ont pas droit) ;
    centimes répartis au plus fort reste. À valider par la décision des associés (modifiable)."""
    from app.services import closing

    amount = closing.result_to_allocate(fy)
    held = holdings(fy.end_date)
    eligible = {a: h["full"] + h["usufruct"] for a, h in held.items() if h["full"] + h["usufruct"] > 0}
    total_parts = sum(eligible.values())
    target = abs(amount)
    lines = []
    if target and total_parts:
        by_id = {a.id: a for a in Associate.query.filter(Associate.id.in_(list(eligible))).all()}
        shares = {a: target * parts // total_parts for a, parts in eligible.items()}
        rest = target - sum(shares.values())
        remainders = sorted(eligible, key=lambda a: (-(target * eligible[a] % total_parts), by_id[a].name))
        for a in remainders[:rest]:
            shares[a] += 1
        lines = [{"associate_id": a, "name": by_id[a].name, "account_code": by_id[a].account.code,
                  "parts": eligible[a], "amount_cents": shares[a]}
                 for a in sorted(eligible, key=lambda a: by_id[a].name)]
    return {"result_cents": amount, "total_parts": total_parts, "lines": lines}
