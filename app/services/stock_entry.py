"""Écriture de stock à la clôture (lot AG4.d, claudedocs/design_inventaire_agricole.md § 8, AGD21 Q-S1).

Inventaire intermittent, comme les dossiers réels (journal KF du dossier A) : une écriture OD au dernier jour de
l'exercice, source `STOCK`, gérée par Lyvre et **non extournée** à l'ouverture. Pour chaque compte de stock :
- annulation du stock initial : D variation / C 3x, pour le solde du compte avant cette écriture (à-nouveaux et
  mouvements de l'exercice) ;
- constatation du stock final : D 3x / C variation, pour la somme des valeurs des lignes d'inventaire ;
- dépréciations : reprise du solde 39x (D 39x / C 78173), puis dotation des lignes (D 68173 / C 39x).
Elle se repasse tant que l'exercice est ouvert et que l'écriture n'est pas validée.
"""
from __future__ import annotations

from sqlalchemy import func

from app.extensions import db
from app.models import Account, FiscalYear, JournalEntry, JournalLine, StockLine
from app.models.journal_entry import SOURCE_OPENING, SOURCE_STOCK
from app.services import stock_inventory as inv
from app.services.stock_inventory import StockError

STOCK_PREFIXES = ("31", "32", "33", "35", "37")
DEPRECIATION = {"31": "391", "32": "392", "33": "393", "35": "395", "37": "397"}


def entry(fy: FiscalYear) -> JournalEntry | None:
    return JournalEntry.query.filter_by(fiscal_year_id=fy.id, source=SOURCE_STOCK).first()


def _account(code: str) -> Account:
    account = Account.query.filter_by(code=code, is_header=False).first()
    if account is None:
        raise StockError(f"Compte {code} absent du plan : créez-le pour passer l'écriture de stock.", status=409)
    return account


def _balances(fy: FiscalYear, prefixes, exclude_entry_id=None) -> dict[int, int]:
    """Solde (débit − crédit) par compte de l'exercice, hors écriture de stock donnée."""
    query = (db.session.query(JournalLine.account_id, func.sum(JournalLine.debit_cents - JournalLine.credit_cents))
             .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
             .join(Account, Account.id == JournalLine.account_id)
             .filter(JournalEntry.fiscal_year_id == fy.id, db.or_(*[Account.code.like(f"{p}%") for p in prefixes])))
    if exclude_entry_id is not None:
        query = query.filter(JournalEntry.id != exclude_entry_id)
    return {acc: int(total or 0) for acc, total in query.group_by(JournalLine.account_id) if total}


def plan(fy: FiscalYear) -> dict:
    """Lignes de l'écriture de stock calculées depuis l'inventaire, et blocages."""
    current = entry(fy)
    excluded = current.id if current is not None else None
    discount_map = inv.discounts(fy)
    lines = StockLine.query.filter_by(fiscal_year_id=fy.id).all()
    problems, final = [], {}
    depreciation: dict[str, int] = {}
    for line in lines:
        _unit, value, _warnings = inv.evaluate(line, fy, discount_map)
        if value is None:
            problems.append(f"« {line.label} » : valeur à compléter.")
            continue
        key = (line.account_id, line.variation_account_id)
        final[key] = final.get(key, 0) + value
        if line.depreciation_cents:
            code = DEPRECIATION[line.account.code[:2]]
            depreciation[code] = depreciation.get(code, 0) + line.depreciation_cents
    opening = _balances(fy, STOCK_PREFIXES, excluded)
    variation_of = {}
    for (account_id, variation_id) in final:
        variation_of.setdefault(account_id, variation_id)
    rows = []                                     # (compte, débit, crédit, libellé)
    for account_id, balance in sorted(opening.items()):
        account = db.session.get(Account, account_id)
        variation_id = variation_of.get(account_id)
        if variation_id is None:
            found = inv.classify(account.code)
            if found is None:
                problems.append(f"Compte {account.code} : stock hors des catégories agricoles, à traiter à la main.")
                continue
            variation_id = _account(found[1]["variation"]).id
        label = f"Annulation du stock initial {account.code}"
        if balance > 0:
            rows += [(variation_id, balance, 0, label), (account_id, 0, balance, label)]
        else:
            rows += [(account_id, -balance, 0, label), (variation_id, 0, -balance, label)]
    for (account_id, variation_id), value in sorted(final.items()):
        if value:
            label = f"Stock final {db.session.get(Account, account_id).code}"
            rows += [(account_id, value, 0, label), (variation_id, 0, value, label)]
    reversal = _balances(fy, ("39",), excluded)
    if reversal or depreciation:
        income, expense = (_account("78173").id if reversal else None), (_account("68173").id if depreciation else None)
        for account_id, balance in sorted(reversal.items()):
            if balance < 0:                       # solde créditeur : dépréciation antérieure reprise
                rows += [(account_id, -balance, 0, "Reprise de la dépréciation"), (income, 0, -balance, "Reprise de la dépréciation")]
        for code, cents in sorted(depreciation.items()):
            account_id = _account(code).id
            rows += [(expense, cents, 0, "Dépréciation des stocks"), (account_id, 0, cents, "Dépréciation des stocks")]
    total_final = sum(final.values())
    return {"rows": rows, "problems": problems, "opening_cents": sum(v for v in opening.values()),
            "final_cents": total_final, "depreciation_cents": sum(depreciation.values()),
            "variation_cents": total_final - sum(opening.values())}


def _signature(rows) -> list:
    totals: dict[int, int] = {}
    for account_id, debit, credit, _label in rows:
        totals[account_id] = totals.get(account_id, 0) + debit - credit
    return sorted((k, v) for k, v in totals.items() if v)


def status(fy: FiscalYear) -> dict:
    current = entry(fy)
    data = plan(fy)
    stale = False
    if current is not None:
        posted = [(l.account_id, l.debit_cents, l.credit_cents, l.label) for l in current.lines]
        stale = _signature(posted) != _signature(data["rows"])
    return {"entry": {"id": current.id, "reference": current.reference, "validated": bool(current.is_validated)}
            if current is not None else None, "stale": stale, "problems": data["problems"],
            "opening_cents": data["opening_cents"], "final_cents": data["final_cents"],
            "variation_cents": data["variation_cents"], "depreciation_cents": data["depreciation_cents"],
            "lines": StockLine.query.filter_by(fiscal_year_id=fy.id).count()}


def cancel(fy: FiscalYear) -> None:
    from app.services.ledger import delete_entries

    current = entry(fy)
    if current is None:
        return
    if fy.status != "open":
        raise StockError("Exercice clôturé : l'écriture de stock est figée.", status=409)
    if current.is_validated:
        raise StockError("Écriture de stock validée : annulez d'abord son lot de validation.", status=409)
    (outcome,) = delete_entries([current.id], allow_managed=True)
    if outcome["status"] != "ok":
        raise StockError(outcome.get("message") or "Suppression impossible.", status=409)


def post(fy: FiscalYear, user_id=None) -> JournalEntry | None:
    """Passe (ou repasse) l'écriture de stock de l'exercice (sans commit)."""
    from app.services.closing import log
    from app.services.ledger import post_entry

    if not inv.enabled():
        raise StockError("Écriture de stock réservée aux exploitations au réel (partie double).", status=409)
    if fy.status != "open":
        raise StockError("Exercice clôturé : rouvrez-le pour passer l'écriture de stock.", status=409)
    data = plan(fy)
    if data["problems"]:
        raise StockError("Inventaire incomplet : " + " ".join(data["problems"]), status=422)
    cancel(fy)
    db.session.flush()
    if not data["rows"]:
        return None
    from app.services.assets import _journal
    lines = [{"account_id": a, "label": label[:300], "debit_cents": d, "credit_cents": c} for a, d, c, label in data["rows"]]
    result = post_entry(fy.id, _journal().id, fy.end_date, f"Inventaire des stocks au {fy.end_date:%d/%m/%Y}", lines,
                        source=SOURCE_STOCK, commit=False)
    log(fy, "inventory", "stock", user_id, entry=result.reference, final_cents=data["final_cents"])
    return result


def checks(fy: FiscalYear) -> list[tuple[str, str, int, str]]:
    """Contrôles de clôture : (clé, libellé, nombre, sévérité)."""
    if not inv.enabled():
        return []
    current = entry(fy)
    lines = StockLine.query.filter_by(fiscal_year_id=fy.id).all()
    out = []
    excluded = current.id if current is not None else None
    opening = _balances(fy, STOCK_PREFIXES, excluded)
    counted = {line.account_id for line in lines}
    if current is None:
        missing = [db.session.get(Account, a).code for a in opening if a not in counted]
        if missing and not lines:
            out.append(("stock_forgotten", f"Stocks à l'ouverture sans inventaire de clôture ({', '.join(sorted(missing))}) : "
                        "saisissez l'inventaire et passez l'écriture de stock", len(missing), "anomaly"))
        elif lines:
            out.append(("stock_entry", "Inventaire saisi, écriture de stock non passée", 1, "anomaly"))
            if missing:
                out.append(("stock_uncounted", f"Comptes de stock sans ligne d'inventaire ({', '.join(sorted(missing))}) : leur "
                            "stock sera ramené à zéro", len(missing), "info"))
    else:
        if status(fy)["stale"]:
            out.append(("stock_stale", "Inventaire modifié depuis l'écriture de stock : repassez-la", 1, "anomaly"))
    discount_map = inv.discounts(fy)
    incomplete = [line for line in lines if inv.evaluate(line, fy, discount_map)[2]]
    if incomplete:
        out.append(("stock_warnings", "Lignes d'inventaire à compléter ou à vérifier (valeur, décote, écart d'effectif…)",
                    len(incomplete), "info"))
    moved = (db.session.query(func.count(JournalLine.id))
             .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
             .join(Account, Account.id == JournalLine.account_id)
             .filter(JournalEntry.fiscal_year_id == fy.id, db.or_(*[Account.code.like(f"{p}%") for p in STOCK_PREFIXES]),
                     db.or_(JournalEntry.source.is_(None), JournalEntry.source.notin_((SOURCE_OPENING, SOURCE_STOCK)))).scalar())
    if moved:
        out.append(("stock_moves", "Mouvements de comptes de stock hors de l'écriture d'inventaire et des à-nouveaux "
                    "(stock tenu ailleurs ?)", int(moved), "info"))
    return out
