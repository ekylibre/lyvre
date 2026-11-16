"""Stock d'entrée au passage du micro-BA au réel (lot CG5.c, claudedocs/design_fiabilisation_cegara.md § 8.3).

Règles relues le 07/11/2026 (BOI-BA-REG-40-10-10, version du 01/07/2020) :
- stock évalué au prix de revient, ou au cours du jour à la date du changement s'il est inférieur (§ 190 et § 195) ;
- option : prix de revient reconstitué à partir du cours du jour à la date du changement (§ 193), toujours limité au
  cours du jour (§ 195) ;
- avances aux cultures au prix de revient (§ 200, art. 72 A) ;
- valeur figée tant que les biens restent au bilan (§ 197) ;
- note détaillant la composition et le mode d'évaluation du stock initial, jointe à la première déclaration (§ 470).

L'écriture d'ouverture (débit des comptes de stock) a pour contrepartie le compte de l'exploitant (108) en entreprise
individuelle, ou les comptes courants d'associés (455), au prorata des parts du capital, en société (D-CG5.1). Elle
n'est pas validée : l'utilisateur la relit et la valide. Une écriture validée fige le stock d'entrée.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.extensions import db
from app.models import Account, Associate, FiscalYear, Journal, JournalEntry, OpeningStockLine
from app.models.journal_entry import SOURCE_STOCK_OPENING
from app.models.stock import OPENING_STOCK_METHODS, STOCK_UNITS
from app.services.stock_inventory import StockError

JOURNAL = ("OD", "Opérations diverses")


def applies(fy: FiscalYear) -> bool:
    """Premier exercice au réel après le micro-BA, ou stock d'entrée déjà saisi."""
    from app.services import ba_regimes
    return ba_regimes._first_real_year(fy) or OpeningStockLine.query.filter_by(fiscal_year_id=fy.id).first() is not None  # noqa: SLF001


def value(line: OpeningStockLine) -> int | None:
    """Valeur retenue de la ligne (centimes), ou None si une donnée manque."""
    if line.method == "crop_advance":
        return line.amount_cents
    if line.cost_unit_cents is None:
        return None
    unit = line.cost_unit_cents
    if line.market_unit_cents is not None:
        unit = min(unit, line.market_unit_cents)               # § 195 : cours du jour s'il est inférieur
    return int((Decimal(line.quantity or 0) * unit).quantize(Decimal(1), ROUND_HALF_UP))


def entry(fy: FiscalYear) -> JournalEntry | None:
    return JournalEntry.query.filter_by(fiscal_year_id=fy.id, source=SOURCE_STOCK_OPENING).first()


def _frozen(fy: FiscalYear) -> None:
    current = entry(fy)
    if fy.closed or (current is not None and current.is_validated):
        raise StockError("Stock d'entrée figé : écriture d'ouverture validée ou exercice clôturé (BOI-BA-REG-40-10-10 "
                         "§ 197).", status=409)


def _apply(line: OpeningStockLine, data: dict) -> None:
    unknown = set(data) - {"account_code", "label", "quantity", "unit", "method", "cost_unit_cents", "market_unit_cents",
                           "amount_cents"}
    if unknown:
        raise StockError(f"Champ inconnu : {sorted(unknown)[0]}.", sorted(unknown)[0])
    if "account_code" in data or line.account_id is None:
        account = Account.query.filter_by(code=str(data.get("account_code") or "").strip(), is_header=False).first()
        if account is None or not account.code.startswith("3"):
            raise StockError("Compte de stock (classe 3) attendu.", "account_code")
        line.account_id = account.id
    if "label" in data or not line.label:
        label = str(data.get("label") or "").strip()[:200]
        if not label:
            raise StockError("Libellé obligatoire.", "label")
        line.label = label
    if "quantity" in data:
        try:
            quantity = Decimal(str(data["quantity"]).replace(",", "."))
        except InvalidOperation:
            raise StockError("Quantité invalide.", "quantity") from None
        if quantity < 0:
            raise StockError("Quantité positive attendue.", "quantity")
        line.quantity = quantity
    if "unit" in data:
        if data["unit"] not in STOCK_UNITS:
            raise StockError("Unité inconnue.", "unit")
        line.unit = data["unit"]
    if "method" in data:
        if data["method"] not in OPENING_STOCK_METHODS:
            raise StockError("Méthode d'évaluation inconnue.", "method")
        line.method = data["method"]
    for field in ("cost_unit_cents", "market_unit_cents", "amount_cents"):
        if field in data:
            amount = data[field]
            if amount is not None and (isinstance(amount, bool) or not isinstance(amount, int) or amount < 0):
                raise StockError("Montant positif en centimes attendu.", field)
            setattr(line, field, amount)


def add_line(fy: FiscalYear, data: dict) -> OpeningStockLine:
    _frozen(fy)
    line = OpeningStockLine(fiscal_year_id=fy.id, quantity=0, unit="unit", method="lower")
    _apply(line, data)
    db.session.add(line)
    db.session.flush()
    return line


def update_line(fy: FiscalYear, line: OpeningStockLine, data: dict) -> None:
    _frozen(fy)
    _apply(line, data)
    db.session.flush()


def delete_line(fy: FiscalYear, line: OpeningStockLine) -> None:
    _frozen(fy)
    db.session.delete(line)
    db.session.flush()


def _counterparts(fy: FiscalYear, total: int) -> list[tuple[Account, int]]:
    """108 en entreprise individuelle ; 455 de chaque associé au prorata des parts du capital en société."""
    from app.services import associates, organization
    if organization.get().legal_form_code in (None, "EI"):
        account = Account.query.filter_by(code="108", is_header=False).first()
        if account is None:
            raise StockError("Compte 108 (compte de l'exploitant) absent du plan.", status=409)
        return [(account, total)]
    held = associates.holdings(fy.start_date)
    parts = {aid: h["full"] + h["bare"] for aid, h in held.items() if h["full"] + h["bare"] > 0}
    capital = sum(parts.values())
    if not capital:
        raise StockError("Société sans parts enregistrées à la date du changement : impossible de répartir le stock "
                         "d'entrée entre les comptes courants d'associés.", status=409)
    out, done = [], 0
    for index, (aid, count) in enumerate(sorted(parts.items())):
        associate = db.session.get(Associate, aid)
        share = total - done if index == len(parts) - 1 else round(total * count / capital)
        done += share
        out.append((associate.account, share))
    return out


def post(fy: FiscalYear) -> JournalEntry:
    """(Re)passe l'écriture d'ouverture, non validée, à la date de début de l'exercice."""
    from app.services.ledger import post_entry
    _frozen(fy)
    lines = OpeningStockLine.query.filter_by(fiscal_year_id=fy.id).order_by(OpeningStockLine.id).all()
    if not lines:
        raise StockError("Aucune ligne de stock d'entrée.", status=409)
    missing = [l.label for l in lines if value(l) is None]
    if missing:
        raise StockError(f"Valeur à compléter : {', '.join(missing)}.", status=409)
    by_account: dict[int, int] = {}
    for line in lines:
        by_account[line.account_id] = by_account.get(line.account_id, 0) + value(line)
    total = sum(by_account.values())
    current = entry(fy)
    if current is not None:
        db.session.delete(current)
        db.session.flush()
    journal = Journal.query.filter_by(code=JOURNAL[0]).first()
    if journal is None:
        journal = Journal(code=JOURNAL[0], label=JOURNAL[1])
        db.session.add(journal)
        db.session.flush()
    label = "Stock d'entrée au passage au réel"
    rows = [{"account_id": acc, "label": label, "debit_cents": cents, "credit_cents": 0}
            for acc, cents in sorted(by_account.items()) if cents]
    rows += [{"account_id": account.id, "label": label, "debit_cents": 0, "credit_cents": cents}
             for account, cents in _counterparts(fy, total) if cents]
    return post_entry(fy.id, journal.id, fy.start_date, label, rows, source=SOURCE_STOCK_OPENING,
                      source_ref=f"fiscal_year:{fy.id}", commit=False)


def note(fy: FiscalYear) -> str:
    """Note de la composition et du mode d'évaluation du stock initial (BOI-BA-REG-40-10-10 § 470)."""
    lines = OpeningStockLine.query.filter_by(fiscal_year_id=fy.id).order_by(OpeningStockLine.id).all()
    out = [f"Stock initial au {fy.start_date:%d/%m/%Y}, passage du micro-BA au régime réel (CGI ann. III art. 38 "
           "sexdecies O et R).", ""]
    for l in lines:
        v = value(l)
        unit = STOCK_UNITS.get(l.unit, l.unit)
        if l.method == "crop_advance":
            detail = "avances aux cultures au prix de revient"
        else:
            cost = f"{l.cost_unit_cents / 100:.2f}" if l.cost_unit_cents is not None else "?"
            market = f"{l.market_unit_cents / 100:.2f}" if l.market_unit_cents is not None else "non saisi"
            basis = "prix de revient reconstitué" if l.method == "market_reconstructed" else "prix de revient"
            detail = (f"{l.quantity} {unit}, {basis} {cost} €, cours du jour {market} € ; "
                      "valeur la plus faible retenue").replace(".", ",")
        out.append(f"- {l.account.code} {l.label} : {detail} → {(v or 0) / 100:,.2f} €".replace(",", " ").replace(".", ","))
    total = sum(value(l) or 0 for l in lines)
    out += ["", f"Total : {total / 100:,.2f} €".replace(",", " ").replace(".", ",")]
    return "\n".join(out)


def payload(fy: FiscalYear) -> dict:
    lines = OpeningStockLine.query.filter_by(fiscal_year_id=fy.id).order_by(OpeningStockLine.id).all()
    current = entry(fy)
    return {"applies": applies(fy),
            "lines": [{"id": l.id, "account_code": l.account.code, "label": l.label, "quantity": str(l.quantity),
                       "unit": l.unit, "method": l.method, "method_label": OPENING_STOCK_METHODS[l.method],
                       "cost_unit_cents": l.cost_unit_cents, "market_unit_cents": l.market_unit_cents,
                       "amount_cents": l.amount_cents, "value_cents": value(l)} for l in lines],
            "total_cents": sum(value(l) or 0 for l in lines),
            "entry": {"id": current.id, "validated": current.is_validated} if current else None,
            "frozen": fy.closed or bool(current and current.is_validated),
            "methods": [{"value": k, "label": v} for k, v in OPENING_STOCK_METHODS.items()],
            "note": note(fy) if lines else None}
