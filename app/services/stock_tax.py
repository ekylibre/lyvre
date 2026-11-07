"""Valeur fiscale des stocks (lot AG4.e, claudedocs/design_inventaire_agricole.md § 6, AGD21).

Par ligne d'inventaire, à côté de la valeur comptable :
- **valeur comptable** (méthode `none`, par défaut) ;
- **méthode forfaitaire** (art. 74 b, option `flat_stock_method` en vigueur à la clôture) : cours du jour × (1 − décote
  de 20 %, ou 30 % pour les bovins et la viticulture), écrêtée à ± 20 % de la valeur d'ouverture sauf renonciation
  (lot CG3.d) ; ni approvisionnements ni avances aux cultures ;
- **stock bloqué** (art. 72 B bis, option `stock_freeze_72_b_bis` en vigueur à la clôture), stocks à rotation de
  plus d'un an (lot CG3.d) : option **globale** (toute ligne à rotation lente est bloquée, saisie motivée possible) ;
  **couches** reconstituées d'exercice en exercice depuis la clôture qui précède l'option : la couche de référence à sa
  valeur fiscale unitaire, chaque hausse de quantité à la valeur comptable unitaire de l'exercice où elle apparaît
  (première inscription), chaque baisse consomme les couches les plus anciennes (PEPS) ;
- **valeur saisie** avec un motif.
L'écart (valeur fiscale − valeur comptable) est sans écriture : il est repris au tableau de passage fiscal (AG6.3).
"""
from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.extensions import db
from app.models import FiscalYear, StockLine, TaxOption
from app.models.stock import FISCAL_METHODS
from app.services import reg_params
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


def slow(line: StockLine) -> bool:
    """Rotation de plus d'un an : la case de la ligne, sinon les animaux d'élevage (lot CG3.d)."""
    if line.slow_rotation is not None:
        return bool(line.slow_rotation)
    return line.category == "animals_long"


def _frozen_line(line: StockLine, opts: dict) -> bool:
    return opts["frozen"] and line.category in FROZEN_ALLOWED and slow(line)


def allowed(line: StockLine, fy: FiscalYear, opts: dict | None = None) -> list[str]:
    opts = opts or options(fy)
    if _frozen_line(line, opts):                   # option globale : la ligne lente est bloquée (ou saisie motivée)
        return ["frozen", "manual"]
    out = ["none", "manual"]
    if opts["flat"] and line.category not in FLAT_FORBIDDEN:
        out.append("flat")
    return out


def effective_method(line: StockLine, fy: FiscalYear, opts: dict | None = None) -> str:
    opts = opts or options(fy)
    method = line.fiscal_method or "none"
    if _frozen_line(line, opts) and method != "manual":
        return "frozen"
    if method == "frozen":                         # option close ou ligne devenue rapide
        return "none"
    return method


key = inv.line_key
_same = inv.same_line


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
    """Valeur bloquée en couches (lot CG3.d, Q7) : référence, entrées à leur première inscription, sorties PEPS."""
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
    layers = [[Decimal(ref_line.quantity or 0), ref_unit, ref_year.label]]
    chain, year = [], fy
    while year is not None and year.end_date > ref_year.end_date:
        chain.append(year)
        year = inv.previous_fiscal_year(year)
    for current in reversed(chain):
        current_line = line if current.id == fy.id else _same(current.id, wanted)
        quantity = Decimal(current_line.quantity or 0) if current_line is not None else Decimal(0)
        held = sum(layer[0] for layer in layers)
        if quantity < held:                        # sortie : premières entrées, premières sorties
            out = held - quantity
            for layer in layers:
                take = min(layer[0], out)
                layer[0] -= take
                out -= take
            layers = [layer for layer in layers if layer[0] > 0]
        elif quantity > held:                      # entrée : bloquée à sa valeur de première inscription
            unit, _value = _accounting(current_line, current)
            if unit is None:
                return {"error": f"Valeur comptable unitaire inconnue en {current.label} pour l'entrée en stock."}
            layers.append([quantity - held, unit, current.label])
    value = int(sum(q * u for q, u, _ in layers).quantize(Decimal(1), ROUND_HALF_UP)) if layers else 0
    reference = next((q for q, _u, label in layers if label == ref_year.label), Decimal(0))
    return {"reference_year": ref_year.label, "reference_unit_cents": ref_unit, "blocked_quantity": str(reference),
            "surplus_quantity": str(sum((q for q, _u, label in layers if label != ref_year.label), Decimal(0))),
            "layers": [{"quantity": str(q), "unit_cents": u, "since": label} for q, u, label in layers],
            "value_cents": value}


def _fiscal_unit(line: StockLine, fy: FiscalYear) -> int | None:
    """Valeur unitaire fiscale d'une ligne (référence du blocage) : sa valeur fiscale ÷ quantité."""
    value = fiscal_value(line, fy)["fiscal_value_cents"]
    quantity = Decimal(line.quantity or 0)
    if value is None or not quantity:
        return None
    return int((Decimal(value) / quantity).quantize(Decimal(1), ROUND_HALF_UP))


def _opening_flat_unit(previous: StockLine, previous_fy: FiscalYear) -> int | None:
    """Valeur unitaire d'ouverture pour l'écrêtement fiscal : la valeur fiscale de la ligne à la clôture précédente,
    si elle était au forfait."""
    if effective_method(previous, previous_fy) != "flat" and previous.method != "flat":
        return None
    return _fiscal_unit(previous, previous_fy)


def fiscal_value(line: StockLine, fy: FiscalYear) -> dict:
    """{fiscal_method, fiscal_value_cents, gap_cents, warnings, frozen?} de la ligne."""
    _unit, accounting = _accounting(line, fy)
    method = effective_method(line, fy)
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
        else:                                              # écrêtement sur la valeur fiscale d'ouverture (CG3.d)
            unit, note = inv.flat_unit(line, fy, previous_unit=_opening_flat_unit)
            if note:
                warnings.append(note)
            value = int((Decimal(line.quantity or 0) * unit).quantize(Decimal(1), ROUND_HALF_UP)) if unit is not None else None
        if not options(fy)["flat"]:
            warnings.append("Option de la méthode forfaitaire non en vigueur à la clôture.")
    else:                                                 # frozen
        detail = frozen(line, fy)
        out["frozen"] = detail
        value = detail.get("value_cents")
        if "error" in detail:
            warnings.append(detail["error"])
    out["fiscal_value_cents"] = value
    out["gap_cents"] = None if value is None or accounting is None else value - accounting
    out["warnings"] = warnings
    return out


def apply(line: StockLine, data: dict, fy: FiscalYear) -> None:
    """Champs fiscaux d'une ligne (appelé par la saisie des lignes)."""
    if "slow_rotation" in data:
        value = data["slow_rotation"]
        if value is not None and not isinstance(value, bool):
            raise StockError("Rotation lente : oui, non ou vide.", "slow_rotation")
        line.slow_rotation = value
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
    if opts["frozen"]:
        out += _de_minimis(fy)
    return out


def _de_minimis(fy: FiscalYear) -> list[tuple[str, str, int, str]]:
    """Blocage 72 B bis : écart de valeur cumulé sur l'exercice et les 2 précédents, rapproché du plafond de minimis
    agricole (lot CG3.d). L'aide est l'avantage fiscal et social qui en résulte, non l'écart lui-même."""
    years, year = [], fy
    while year is not None and len(years) < 3:
        years.append(year)
        year = inv.previous_fiscal_year(year)
    gap = 0
    for y in years:
        opts = options(y)
        for line in StockLine.query.filter_by(fiscal_year_id=y.id):
            if effective_method(line, y, opts) == "frozen":
                data = fiscal_value(line, y)
                gap += max(-(data["gap_cents"] or 0), 0)
    if not gap:
        return []
    cap = reg_params.value("aid.de_minimis.agri_cap_cents", fy.end_date, default=None)
    euros = lambda c: f"{c / 100:,.0f} €".replace(",", " ")  # noqa: E731
    label = (f"Blocage 72 B bis : valeur des stocks minorée de {euros(gap)} sur {len(years)} exercice(s). L'avantage "
             "fiscal et social qui en résulte est une aide de minimis")
    label += f", plafonnée à {euros(cap)} sur 3 exercices toutes aides de minimis agricoles confondues" if cap else ""
    return [("stock_freeze_de_minimis", label, 1, "info")]
