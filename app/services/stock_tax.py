"""Valeur fiscale des stocks (lot AG4.e, claudedocs/design_inventaire_agricole.md § 6, AGD21).

Par ligne d'inventaire, à côté de la valeur comptable :
- **valeur comptable** (méthode `none`, par défaut) ;
- **méthode forfaitaire** (art. 74 b, option `flat_stock_method` en vigueur à la clôture) : cours du jour × (1 − décote
  de 20 %, ou 30 % pour les bovins et la viticulture) ; ni approvisionnements ni avances aux cultures ;
- **stock bloqué** (art. 72 B bis, option `stock_freeze_72_b_bis` en vigueur à la clôture), produits et animaux :
  valeur unitaire fiscale de la clôture qui précède l'option, pour la ligne de même clé. **Règle proposée, à valider
  (Q-S5)** : la quantité bloquée est la plus petite des quantités de référence, de l'exercice précédent et de
  l'exercice (une sortie la réduit, elle ne se reconstitue pas) ; le surplus est évalué à la valeur comptable ;
- **valeur saisie** avec un motif.
L'écart (valeur fiscale − valeur comptable) est sans écriture : il est repris au tableau de passage fiscal (AG6.3).
"""
from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.extensions import db
from app.models import FiscalYear, StockLine, TaxOption
from app.models.stock import FISCAL_METHODS
from app.services import stock_inventory as inv
from app.services.stock_inventory import StockError

FLAT_FORBIDDEN = ("supplies", "other_supplies", "goods", "crop_advances")
FROZEN_ALLOWED = ("animals_long", "animals_short", "plants", "in_progress", "intermediate", "finished")


def _option(code: str, on: date) -> TaxOption | None:
    for option in TaxOption.query.filter_by(code=code).order_by(TaxOption.start_date.desc()):
        if option.start_date <= on and (option.renounced_on is None or on < option.renounced_on):
            return option
    return None


def options(fy: FiscalYear) -> dict:
    flat, frozen = _option("flat_stock_method", fy.end_date), _option("stock_freeze_72_b_bis", fy.end_date)
    return {"flat": flat is not None, "frozen": frozen is not None,
            "frozen_since": frozen.start_date.isoformat() if frozen is not None else None}


def allowed(line: StockLine, fy: FiscalYear, opts: dict | None = None) -> list[str]:
    opts = opts or options(fy)
    out = ["none", "manual"]
    if opts["flat"] and line.category not in FLAT_FORBIDDEN:
        out.append("flat")
    if opts["frozen"] and line.category in FROZEN_ALLOWED:
        out.append("frozen")
    return out


def key(line: StockLine) -> tuple:
    if line.lot_id is not None:
        return (line.account_id, "lot", line.lot_id)
    text = (line.production or line.label or "").strip().lower()
    return (line.account_id, "label", text)


def _same(fy_id: int, wanted: tuple) -> StockLine | None:
    for line in StockLine.query.filter_by(fiscal_year_id=fy_id):
        if key(line) == wanted:
            return line
    return None


def _reference_year(fy: FiscalYear) -> FiscalYear | None:
    """Exercice dont la clôture précède l'option de blocage en vigueur."""
    option = _option("stock_freeze_72_b_bis", fy.end_date)
    if option is None:
        return None
    return (FiscalYear.query.filter(FiscalYear.end_date < option.start_date)
            .order_by(FiscalYear.end_date.desc()).first())


def _accounting(line: StockLine, fy: FiscalYear) -> tuple[int | None, int | None]:
    unit, value, _ = inv.evaluate(line, fy)
    return unit, value


def frozen(line: StockLine, fy: FiscalYear) -> dict:
    """Valeur bloquée : référence, quantité bloquée, surplus évalué à la valeur comptable."""
    ref_year = _reference_year(fy)
    if ref_year is None:
        return {"error": "Aucun exercice clos avant l'option de blocage : valeur de référence introuvable."}
    wanted = key(line)
    ref_line = _same(ref_year.id, wanted)
    if ref_line is None:
        return {"error": f"Aucune ligne de même clé à la clôture du {ref_year.end_date:%d/%m/%Y} (avant l'option)."}
    ref_unit = _fiscal_unit(ref_line, ref_year)
    if ref_unit is None:
        return {"error": "Valeur unitaire de référence inconnue."}
    blocked = Decimal(ref_line.quantity or 0)
    year = inv.previous_fiscal_year(fy)
    chain = []
    while year is not None and year.end_date > ref_year.end_date:
        chain.append(year)
        year = inv.previous_fiscal_year(year)
    for previous in reversed(chain):                      # la quantité bloquée ne se reconstitue jamais
        prev_line = _same(previous.id, wanted)
        blocked = min(blocked, Decimal(prev_line.quantity or 0) if prev_line is not None else Decimal(0))
    quantity = Decimal(line.quantity or 0)
    blocked = min(blocked, quantity)
    unit, _value = _accounting(line, fy)
    surplus = quantity - blocked
    if surplus and unit is None:
        return {"error": "Valeur comptable unitaire inconnue pour le surplus."}
    value = int((blocked * ref_unit + surplus * (unit or 0)).quantize(Decimal(1), ROUND_HALF_UP))
    return {"reference_year": ref_year.label, "reference_unit_cents": ref_unit, "blocked_quantity": str(blocked),
            "surplus_quantity": str(surplus), "value_cents": value}


def _fiscal_unit(line: StockLine, fy: FiscalYear) -> int | None:
    """Valeur unitaire fiscale d'une ligne (référence du blocage) : sa valeur fiscale ÷ quantité."""
    value = fiscal_value(line, fy)["fiscal_value_cents"]
    quantity = Decimal(line.quantity or 0)
    if value is None or not quantity:
        return None
    return int((Decimal(value) / quantity).quantize(Decimal(1), ROUND_HALF_UP))


def fiscal_value(line: StockLine, fy: FiscalYear) -> dict:
    """{fiscal_method, fiscal_value_cents, gap_cents, warnings, frozen?} de la ligne."""
    _unit, accounting = _accounting(line, fy)
    method = line.fiscal_method or "none"
    warnings: list[str] = []
    out: dict = {"fiscal_method": method}
    if method == "none":
        value = accounting
    elif method == "manual":
        value = line.fiscal_value_cents
        if value is None:
            warnings.append("Valeur fiscale à saisir.")
    elif method == "flat":
        if line.method == "flat":
            value = accounting                            # forfaitaire déjà retenu en comptabilité (Q-S4)
        elif line.market_price_cents is None:
            value = None
            warnings.append("Cours du jour à saisir pour la valeur forfaitaire.")
        else:
            bp = inv.flat_discount_bp(line.flat_rate or "general", fy.end_date)
            unit = inv._discounted(line.market_price_cents, bp) if bp is not None else None  # noqa: SLF001
            value = int((Decimal(line.quantity or 0) * unit).quantize(Decimal(1), ROUND_HALF_UP)) if unit is not None else None
        if not options(fy)["flat"]:
            warnings.append("Option de la méthode forfaitaire non en vigueur à la clôture.")
    else:                                                 # frozen
        detail = frozen(line, fy)
        out["frozen"] = detail
        value = detail.get("value_cents")
        if "error" in detail:
            warnings.append(detail["error"])
        warnings.append("Stock bloqué : règle de l'excédent et des sorties à valider (Q-S5).")
    out["fiscal_value_cents"] = value
    out["gap_cents"] = None if value is None or accounting is None else value - accounting
    out["warnings"] = warnings
    return out


def apply(line: StockLine, data: dict, fy: FiscalYear) -> None:
    """Champs fiscaux d'une ligne (appelé par la saisie des lignes)."""
    if "fiscal_method" in data:
        method = data["fiscal_method"] or "none"
        if method not in FISCAL_METHODS:
            raise StockError("Méthode fiscale inconnue.", "fiscal_method")
        if method not in allowed(line, fy):
            raise StockError(f"{FISCAL_METHODS[method]} non permise pour cette ligne (option fiscale en vigueur à la "
                             "clôture, catégorie de stock).", "fiscal_method")
        line.fiscal_method = method
    if "fiscal_value_cents" in data:
        value = data["fiscal_value_cents"]
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10 ** 11):
            raise StockError("Valeur fiscale positive en centimes attendue.", "fiscal_value_cents")
        line.fiscal_value_cents = value
    if "fiscal_reason" in data:
        line.fiscal_reason = str(data["fiscal_reason"] or "").strip()[:300] or None
    if line.fiscal_method == "manual" and line.fiscal_value_cents is not None and not line.fiscal_reason:
        raise StockError("Motif de la valeur fiscale saisie obligatoire.", "fiscal_reason")


def totals(fy: FiscalYear) -> dict:
    """Totaux comptable et fiscal de l'inventaire, écart (pour le tableau de passage d'AG6)."""
    accounting = fiscal = 0
    missing = 0
    rows = []
    for line in StockLine.query.filter_by(fiscal_year_id=fy.id).order_by(StockLine.position, StockLine.id):
        _unit, value = _accounting(line, fy)
        data = fiscal_value(line, fy)
        accounting += value or 0
        if data["fiscal_value_cents"] is None:
            missing += 1
        fiscal += data["fiscal_value_cents"] if data["fiscal_value_cents"] is not None else (value or 0)
        if data["gap_cents"]:
            rows.append({"line_id": line.id, "label": line.label, "fiscal_method": data["fiscal_method"],
                         "gap_cents": data["gap_cents"]})
    return {"accounting_cents": accounting, "fiscal_cents": fiscal, "gap_cents": fiscal - accounting,
            "missing": missing, "gaps": rows, **options(fy)}


def checks(fy: FiscalYear) -> list[tuple[str, str, int, str]]:
    if not inv.enabled():
        return []
    opts = options(fy)
    if not opts["flat"] and not opts["frozen"]:
        return []
    lines = StockLine.query.filter_by(fiscal_year_id=fy.id).all()
    pending = [l for l in lines if (l.fiscal_method or "none") == "none" and len(allowed(l, fy, opts)) > 2
               and not (opts["flat"] and l.method == "flat")]
    incomplete = [l for l in lines if fiscal_value(l, fy)["fiscal_value_cents"] is None]
    out = []
    if pending:
        out.append(("stock_fiscal", "Option forfaitaire ou de blocage (72 B bis) en vigueur : valeur fiscale des lignes de "
                    "produits et d'animaux à choisir", len(pending), "info"))
    if incomplete:
        out.append(("stock_fiscal_missing", "Valeurs fiscales de stock incomplètes", len(incomplete), "info"))
    return out
