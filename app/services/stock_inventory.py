"""Inventaire de clôture : lignes de stock et méthodes de valorisation (lot AG4.a,
claudedocs/design_inventaire_agricole.md §§ 3 et 4, décision AGD21).

- Catégories, comptes de stock et de variation, méthodes permises : `data/agri_stock_accounts.yml`.
- Méthodes : coût réel saisi (Lyvre ne calcule ni CUMP ni PEPS, faute de quantités dans les achats), coût standard
  (barème de l'exploitation), prix de détail moins la décote de la catégorie (refusé pour les approvisionnements et
  les avances aux cultures, PCG 618-13 et 618-14), méthode forfaitaire comme valeur comptable quand l'option
  `flat_stock_method` est en vigueur à la clôture (Q-S4).
- Contrôle de vraisemblance du cours saisi (`data/agri_price_references.yml`) : avertissement, jamais de refus.
- Plan agricole en partie double seulement ; pas d'inventaire au micro-BA (AG4.7). L'inventaire d'un exercice
  clôturé est figé.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path

import yaml
from sqlalchemy import func

from app.extensions import db
from app.models import Account, FiscalYear, JournalEntry, JournalLine, StockLine, StockSettings, StockStandard, TaxOption
from app.models.stock import FLAT_RATES, STOCK_METHODS, STOCK_UNITS

ROOT = Path(__file__).resolve().parents[2] / "data"
MAX_CENTS = 10 ** 11
FLAT_KEYS = {"general": "stock.flat_discount_general_bp", "cattle_wine": "stock.flat_discount_cattle_wine_bp"}
RETAIL_FORBIDDEN = {"supplies", "other_supplies", "goods", "crop_advances"}
FLAT_FORBIDDEN = {"supplies", "other_supplies", "goods", "crop_advances"}


class StockError(Exception):
    def __init__(self, message, field=None, status=422):
        super().__init__(message)
        self.message, self.field, self.status = message, field, status


# ------------------------------------------------------------------ données

@lru_cache(maxsize=1)
def _accounts_data() -> dict:
    data = yaml.safe_load((ROOT / "agri_stock_accounts.yml").read_text(encoding="utf-8"))
    for cat in data["categories"]:
        unknown = set(cat["methods"]) - set(STOCK_METHODS)
        if unknown or cat["group"] not in data["groups"]:
            raise ValueError(f"catégorie {cat['key']} : méthode ou groupe inconnu")
        if cat["key"] in RETAIL_FORBIDDEN and "retail" in cat["methods"]:
            raise ValueError(f"catégorie {cat['key']} : prix de détail interdit")
    return data


def categories() -> list[dict]:
    return _accounts_data()["categories"]


def groups() -> dict:
    return _accounts_data()["groups"]


@lru_cache(maxsize=1)
def price_references() -> dict:
    data = yaml.safe_load((ROOT / "agri_price_references.yml").read_text(encoding="utf-8"))
    data["by_key"] = {r["key"]: r for r in data["references"]}
    return data


def classify(code: str) -> tuple[dict, dict] | None:
    """(catégorie, règle de compte) du compte de stock : le préfixe le plus long l'emporte."""
    best = None
    for cat in categories():
        for rule in cat["accounts"]:
            if code.startswith(rule["prefix"]) and (best is None or len(rule["prefix"]) > len(best[1]["prefix"])):
                best = (cat, rule)
    return best


def category(key: str) -> dict:
    for cat in categories():
        if cat["key"] == key:
            return cat
    raise StockError("Catégorie de stock inconnue.", "category")


# ------------------------------------------------------------------ accès

def enabled() -> bool:
    from app.services.rule_entries import simple_mode
    from app.tenant import is_agri

    return is_agri() and not simple_mode()


def _editable(fy: FiscalYear) -> None:
    if fy.status != "open":
        raise StockError("Exercice clôturé : l'inventaire est figé.", status=409)


def settings(fy: FiscalYear, create: bool = False) -> StockSettings | None:
    row = StockSettings.query.filter_by(fiscal_year_id=fy.id).first()
    if row is None and create:
        row = StockSettings(fiscal_year_id=fy.id, discounts_json="{}")
        db.session.add(row)
        db.session.flush()
    return row


def discounts(fy: FiscalYear) -> dict[str, int]:
    row = settings(fy)
    try:
        return json.loads(row.discounts_json) if row is not None else {}
    except ValueError:
        return {}


def flat_allowed(fy: FiscalYear) -> bool:
    """Option « méthode forfaitaire des stocks » en vigueur à la clôture."""
    on = fy.end_date
    return any(o.start_date <= on and (o.renounced_on is None or on < o.renounced_on)
               for o in TaxOption.query.filter_by(code="flat_stock_method"))


def flat_discount_bp(rate: str, on: date) -> int | None:
    from app.services import reg_params

    key = FLAT_KEYS.get(rate or "general")
    return reg_params.value(key, on, default=None) if key else None


# ------------------------------------------------------------------ calcul

def _quantity(value) -> Decimal:
    try:
        quantity = Decimal(str(value if value not in (None, "") else 0))
    except (InvalidOperation, ValueError):
        raise StockError("Quantité : nombre attendu.", "quantity") from None
    if quantity < 0 or quantity >= Decimal("1e11"):
        raise StockError("Quantité : nombre positif attendu.", "quantity")
    return quantity.quantize(Decimal("0.001"))


def _times(quantity: Decimal, cents: int) -> int:
    return int((quantity * cents).quantize(Decimal(1), ROUND_HALF_UP))


def _discounted(cents: int, bp: int) -> int:
    return int((Decimal(cents) * (10000 - bp) / 10000).quantize(Decimal(1), ROUND_HALF_UP))


def evaluate(line: StockLine, fy: FiscalYear, discount_map: dict | None = None) -> tuple[int | None, int | None, list[str]]:
    """(valeur unitaire, valeur, avertissements) de la ligne selon sa méthode."""
    warnings: list[str] = []
    unit = None
    if line.method == "crop_advance":
        if line.crop_advance is None:
            return None, None, ["Fiche d'avance aux cultures introuvable."]
        from app.services import crop_advances
        total, _detail, advance_warnings = crop_advances.value(line.crop_advance, fy)
        quantity = Decimal(line.quantity or 0)
        unit = int((Decimal(total) / quantity).quantize(Decimal(1), ROUND_HALF_UP)) if total is not None and quantity else None
        return unit, total, advance_warnings
    if line.method == "actual":
        unit = line.unit_value_cents
        if unit is None:
            warnings.append("Valeur unitaire à saisir.")
    elif line.method == "standard":
        standard = line.standard
        if standard is None:
            warnings.append("Barème de coût standard à choisir.")
        else:
            unit = standard.value_cents
            if standard.unit != line.unit:
                warnings.append(f"Unité du barème ({STOCK_UNITS.get(standard.unit, standard.unit)}) différente de la ligne.")
    elif line.method in ("retail", "flat"):
        if line.market_price_cents is None:
            warnings.append("Cours du jour à la clôture à saisir.")
        elif line.method == "retail":
            bp = (discount_map if discount_map is not None else discounts(fy)).get(line.category)
            if bp is None:
                warnings.append("Décote du prix de détail à fixer pour la catégorie.")
            else:
                unit = _discounted(line.market_price_cents, bp)
        else:
            bp = flat_discount_bp(line.flat_rate or "general", fy.end_date)
            if bp is None:
                warnings.append("Taux de décote forfaitaire introuvable pour la date de clôture.")
            else:
                unit = _discounted(line.market_price_cents, bp)
        warnings += price_warnings(line)
    if line.category in ("animals_long", "animals_short"):
        from app.services import stock_lots
        breeder = stock_lots.breeder_warning(line, fy)                 # lot AG5.d
        if breeder:
            warnings.append(breeder)
    if line.lot is not None:
        from app.services import stock_lots
        summary = stock_lots.summary(line.lot, fy)
        if line.heads is None:
            warnings.append(f"Effectif compté du lot à saisir (théorique : {summary['theoretical']}).")
        elif summary["gap"] and not line.gap_reason:
            warnings.append(f"Écart de {summary['gap']:+d} tête(s) avec l'effectif théorique ({summary['theoretical']}) : "
                            "motif à saisir.")
    value = _times(Decimal(line.quantity or 0), unit) if unit is not None else None
    if line.method == "flat" and not flat_allowed(fy):
        warnings.append("Option de la méthode forfaitaire non enregistrée (Structure › Fiscalité) à la clôture.")
    return unit, value, warnings


def price_warnings(line: StockLine) -> list[str]:
    ref = price_references()["by_key"].get(line.price_reference or "")
    if ref is None or line.market_price_cents is None:
        return []
    euros = line.market_price_cents / 100
    if euros < ref["min"] / 2 or euros > ref["max"] * 2:
        return [f"Cours de {euros:.2f} {ref['unit']} loin de l'ordre de grandeur ({ref['label']} : {ref['min']:.2f} à "
                f"{ref['max']:.2f} {ref['unit']}, semaine {price_references()['week'][-2:]}) : vérifiez l'unité."
                .replace(".", ",")]
    return []


def recompute(line: StockLine, fy: FiscalYear) -> list[str]:
    unit, value, warnings = evaluate(line, fy)
    if line.method != "actual":
        line.unit_value_cents = unit
    line.value_cents = value
    return warnings


# ------------------------------------------------------------------ saisie

def _cents(value, field, label, allow_none=True):
    if value in (None, ""):
        if allow_none:
            return None
        raise StockError(f"{label} : montant attendu.", field)
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_CENTS:
        raise StockError(f"{label} : montant positif en centimes attendu.", field)
    return value


def _account(code, field, label) -> Account:
    account = Account.query.filter_by(code=str(code or "").strip()).first()
    if account is None:
        raise StockError(f"{label} : compte « {code} » introuvable dans le plan.", field)
    if account.is_header:
        raise StockError(f"{label} : « {account.code} » est un compte d'en-tête.", field)
    return account


FIELDS = {"account_code", "variation_account_code", "label", "production", "quantity", "unit", "method", "standard_id",
          "market_price_cents", "price_source", "price_reference", "flat_rate", "unit_value_cents",
          "depreciation_cents", "depreciation_reason", "notes", "lot_id", "heads", "gap_reason", "fiscal_method",
          "fiscal_value_cents", "fiscal_reason"}


def _apply(line: StockLine, data: dict, fy: FiscalYear, creating: bool) -> None:
    unknown = set(data) - FIELDS
    if unknown:
        raise StockError(f"Champ inconnu : {sorted(unknown)[0]}.", sorted(unknown)[0])
    lot = None
    if data.get("lot_id") is not None:
        from app.models import StockLot
        lot = db.session.get(StockLot, data["lot_id"]) if isinstance(data["lot_id"], int) else None
        if lot is None:
            raise StockError("Lot d'animaux introuvable.", "lot_id")
        if StockLine.query.filter(StockLine.fiscal_year_id == fy.id, StockLine.lot_id == lot.id,
                                  StockLine.id != (line.id or 0)).first() is not None:
            raise StockError("Ce lot a déjà sa ligne dans l'inventaire de l'exercice.", "lot_id", 409)
        if not data.get("account_code"):
            data = {**data, "account_code": lot.account.code}
        if creating and not data.get("label"):
            data = {**data, "label": lot.label}
    if creating or "account_code" in data:
        account = _account(data.get("account_code"), "account_code", "Compte de stock")
        found = classify(account.code)
        if found is None:
            raise StockError(f"Compte {account.code} : compte de stock agricole attendu (31, 32, 33, 35, 37).",
                             "account_code")
        cat, rule = found
        line.account, line.category = account, cat["key"]
        if not data.get("variation_account_code"):
            line.variation_account = _account(rule["variation"], "variation_account_code", "Compte de variation")
    if data.get("variation_account_code"):
        variation = _account(data["variation_account_code"], "variation_account_code", "Compte de variation")
        if not variation.code.startswith(("603", "713")):
            raise StockError("Compte de variation 603… ou 713… attendu.", "variation_account_code")
        line.variation_account = variation
    if creating or "label" in data:
        label = str(data.get("label") or "").strip()[:200]
        if not label:
            raise StockError("Libellé obligatoire.", "label")
        line.label = label
    for field, limit in (("production", 120), ("price_source", 200), ("depreciation_reason", 300)):
        if field in data:
            setattr(line, field, str(data[field] or "").strip()[:limit] or None)
    if "notes" in data:
        line.notes = str(data["notes"] or "").strip()[:5000] or None
    if "quantity" in data or creating:
        line.quantity = _quantity(data.get("quantity"))
    if "unit" in data or creating:
        unit = data.get("unit") or "unit"
        if unit not in STOCK_UNITS:
            raise StockError("Unité inconnue.", "unit")
        line.unit = unit
    if "method" in data or creating:
        method = data.get("method") or "actual"
        if method not in STOCK_METHODS:
            raise StockError("Méthode inconnue.", "method")
        line.method = method
    cat = category(line.category)
    if line.method == "crop_advance" and line.crop_advance_id is None:
        raise StockError("Créez la fiche de la culture en terre : elle alimente sa ligne d'inventaire.", "method")
    if line.crop_advance_id is not None and ("account_code" in data or "method" in data or "quantity" in data):
        raise StockError("Ligne tenue par sa fiche d'avance aux cultures : modifiez la fiche.", "method", 409)
    if line.method not in cat["methods"]:
        reason = {"retail": " : le prix de détail est interdit pour les approvisionnements et les avances aux cultures "
                            "(PCG 618-13, 618-14)",
                  "flat": " : la méthode forfaitaire ne s'applique ni aux approvisionnements achetés ni aux avances aux "
                          "cultures"}.get(line.method, "")
        raise StockError(f"{STOCK_METHODS[line.method]} non permis pour « {cat['label']} »{reason}.", "method")
    if "standard_id" in data:
        sid = data["standard_id"]
        if sid is not None and (not isinstance(sid, int) or db.session.get(StockStandard, sid) is None):
            raise StockError("Barème introuvable.", "standard_id")
        line.standard_id = sid
    for field, label in (("market_price_cents", "Cours du jour"), ("unit_value_cents", "Valeur unitaire"),
                         ("depreciation_cents", "Dépréciation")):
        if field in data:
            setattr(line, field, _cents(data[field], field, label))
    if "price_reference" in data:
        ref = data["price_reference"] or None
        if ref is not None and ref not in price_references()["by_key"]:
            raise StockError("Référence de cours inconnue.", "price_reference")
        line.price_reference = ref
    if "flat_rate" in data:
        rate = data["flat_rate"] or None
        if rate is not None and rate not in FLAT_RATES:
            raise StockError("Taux forfaitaire inconnu.", "flat_rate")
        line.flat_rate = rate
    if "lot_id" in data:
        line.lot = lot
    if line.lot is not None and line.lot.account_id != line.account.id:
        raise StockError("Le compte de la ligne doit être celui du lot.", "account_code")
    if "heads" in data:
        heads = data["heads"]
        if heads is not None and (isinstance(heads, bool) or not isinstance(heads, int) or not 0 <= heads < 10 ** 7):
            raise StockError("Effectif compté : nombre de têtes attendu.", "heads")
        line.heads = heads
    if "gap_reason" in data:
        line.gap_reason = str(data["gap_reason"] or "").strip()[:300] or None
    if line.lot is not None and line.heads is not None:
        if line.unit == "head":
            line.quantity = Decimal(line.heads)
        elif line.unit == "kg":
            if line.lot.average_weight_kg is None:
                raise StockError("Poids moyen du lot à saisir pour une valeur au kg.", "unit")
            line.quantity = (Decimal(line.heads) * line.lot.average_weight_kg).quantize(Decimal("0.001"))
        else:
            raise StockError("Ligne d'un lot : unité tête ou kg.", "unit")
    from app.services import stock_tax
    stock_tax.apply(line, data, fy)
    if line.depreciation_cents and not line.depreciation_reason:
        raise StockError("Motif de la dépréciation obligatoire (prix, intempéries, maladie…).", "depreciation_reason")
    if line.depreciation_cents and line.depreciation_cents > (evaluate(line, fy)[1] or 0):
        raise StockError("La dépréciation dépasse la valeur de la ligne.", "depreciation_cents")


def create_line(fy: FiscalYear, data: dict) -> StockLine:
    _editable(fy)
    line = StockLine(fiscal_year_id=fy.id)
    _apply(line, data, fy, creating=True)
    line.position = (db.session.query(func.max(StockLine.position)).filter_by(fiscal_year_id=fy.id).scalar() or 0) + 1
    recompute(line, fy)
    db.session.add(line)
    db.session.flush()
    return line


def update_line(fy: FiscalYear, line: StockLine, data: dict) -> StockLine:
    _editable(fy)
    if line.fiscal_year_id != fy.id:
        raise StockError("Ligne introuvable.", status=404)
    _apply(line, data, fy, creating=False)
    recompute(line, fy)
    db.session.flush()
    return line


def delete_line(fy: FiscalYear, line: StockLine) -> None:
    _editable(fy)
    if line.fiscal_year_id != fy.id:
        raise StockError("Ligne introuvable.", status=404)
    db.session.delete(line)
    db.session.flush()


def set_settings(fy: FiscalYear, data: dict) -> StockSettings:
    _editable(fy)
    row = settings(fy, create=True)
    if "discounts" in data:
        raw = data["discounts"]
        if not isinstance(raw, dict):
            raise StockError("Décotes par catégorie attendues.", "discounts")
        clean = {}
        for key, bp in raw.items():
            if category(key)["key"] in RETAIL_FORBIDDEN:
                raise StockError("Pas de décote de prix de détail pour cette catégorie.", "discounts")
            if bp is None:
                continue
            if isinstance(bp, bool) or not isinstance(bp, int) or not 0 <= bp < 10000:
                raise StockError("Décote en points de base, entre 0 et 9 999.", "discounts")
            clean[key] = bp
        row.discounts_json = json.dumps(clean, sort_keys=True)
    if "counted_on" in data:
        try:
            row.counted_on = date.fromisoformat(str(data["counted_on"])[:10]) if data["counted_on"] else None
        except ValueError:
            raise StockError("Date du comptage : AAAA-MM-JJ.", "counted_on") from None
    db.session.flush()
    for line in StockLine.query.filter_by(fiscal_year_id=fy.id):
        recompute(line, fy)
    db.session.flush()
    return row


def previous_fiscal_year(fy: FiscalYear) -> FiscalYear | None:
    return FiscalYear.query.filter(FiscalYear.end_date == fy.start_date - timedelta(days=1)).first()


def copy_previous(fy: FiscalYear) -> int:
    """Reprend les lignes de l'exercice précédent (comptes, méthodes, barèmes), quantités à zéro."""
    _editable(fy)
    previous = previous_fiscal_year(fy)
    if previous is None:
        raise StockError("Aucun exercice précédent.", status=404)
    if StockLine.query.filter_by(fiscal_year_id=fy.id).first() is not None:
        raise StockError("L'inventaire de l'exercice a déjà des lignes.", status=409)
    count = 0
    for old in StockLine.query.filter_by(fiscal_year_id=previous.id).order_by(StockLine.position, StockLine.id):
        if old.crop_advance_id is not None:
            continue                                   # avance aux cultures : nouvelle fiche à chaque clôture
        line = StockLine(fiscal_year_id=fy.id, category=old.category, account_id=old.account_id,
                         variation_account_id=old.variation_account_id, label=old.label, production=old.production,
                         quantity=0, unit=old.unit, method=old.method, standard_id=old.standard_id,
                         price_reference=old.price_reference, flat_rate=old.flat_rate,
                         unit_value_cents=old.unit_value_cents if old.method == "actual" else None,
                         lot_id=old.lot_id if old.lot is not None and old.lot.active else None, position=old.position)
        db.session.add(line)
        recompute(line, fy)
        count += 1
    previous_settings = settings(previous)
    if previous_settings is not None and settings(fy) is None:
        db.session.add(StockSettings(fiscal_year_id=fy.id, discounts_json=previous_settings.discounts_json))
    db.session.flush()
    return count


# ------------------------------------------------------------------ import (tableur)

COLUMNS = {"compte": "account_code", "libellé": "label", "libelle": "label", "production": "production",
           "quantité": "quantity", "quantite": "quantity", "unité": "unit", "unite": "unit", "méthode": "method",
           "methode": "method", "valeur unitaire": "unit_value_cents", "cours": "market_price_cents",
           "variation": "variation_account_code", "notes": "notes"}
METHOD_NAMES = {**{k: k for k in STOCK_METHODS}, "coût réel": "actual", "cout reel": "actual", "réel": "actual",
                "standard": "standard", "coût standard": "standard", "prix de détail": "retail", "détail": "retail",
                "forfaitaire": "flat"}
UNIT_NAMES = {**{k: k for k in STOCK_UNITS}, **{v: k for k, v in STOCK_UNITS.items()}, "tête": "head", "tete": "head",
              "têtes": "head", "u": "unit"}


def _euros_to_cents(text) -> int | None:
    if text in (None, ""):
        return None
    try:
        return int((Decimal(str(text).replace(" ", "").replace(" ", "").replace(",", ".")) * 100)
                   .quantize(Decimal(1), ROUND_HALF_UP))
    except InvalidOperation:
        raise StockError(f"Montant illisible : « {text} ».") from None


def _rows(filename: str, content: bytes) -> list[list]:
    name = filename.lower()
    if name.endswith(".xlsx"):
        from io import BytesIO

        from openpyxl import load_workbook
        sheet = load_workbook(BytesIO(content), read_only=True, data_only=True).active
        return [list(row) for row in sheet.iter_rows(values_only=True)]
    if name.endswith((".csv", ".txt")):
        import csv
        text = content.decode("utf-8-sig", errors="replace")
        dialect = ";" if text.count(";") >= text.count(",") else ","
        return list(csv.reader(text.splitlines(), delimiter=dialect))
    raise StockError("Fichier CSV ou XLSX attendu.", "file")


def import_lines(fy: FiscalYear, filename: str, content: bytes) -> int:
    """Lignes d'un tableur (première ligne : en-têtes Compte, Libellé, Quantité, Unité, Méthode, Valeur unitaire,
    Cours, Production, Variation, Notes) ; tout ou rien."""
    _editable(fy)
    rows = [r for r in _rows(filename, content) if any(c not in (None, "") for c in r)]
    if len(rows) < 2:
        raise StockError("Fichier vide : une ligne d'en-têtes puis une ligne par stock.", "file")
    header = [COLUMNS.get(str(c or "").strip().lower()) for c in rows[0]]
    if "account_code" not in header or "label" not in header:
        raise StockError("Colonnes « Compte » et « Libellé » obligatoires.", "file")
    count = 0
    for number, row in enumerate(rows[1:], start=2):
        data = {field: row[i] for i, field in enumerate(header) if field and i < len(row) and row[i] not in (None, "")}
        try:
            if "method" in data:
                data["method"] = METHOD_NAMES.get(str(data["method"]).strip().lower(), str(data["method"]).strip())
            if "unit" in data:
                data["unit"] = UNIT_NAMES.get(str(data["unit"]).strip().lower(), str(data["unit"]).strip())
            for field in ("unit_value_cents", "market_price_cents"):
                if field in data:
                    data[field] = _euros_to_cents(data[field])
            if "quantity" in data:
                data["quantity"] = str(data["quantity"]).replace(",", ".").replace(" ", "")
            for field in ("account_code", "variation_account_code"):
                if field in data:
                    data[field] = str(data[field]).strip().split(".")[0]
            create_line(fy, data)
        except StockError as exc:
            raise StockError(f"Ligne {number} : {exc.message}", "file") from None
        count += 1
    return count


# ------------------------------------------------------------------ repères et restitution

def _balance_before(fy: FiscalYear, account_id: int) -> int:
    """Solde (débit − crédit) du compte dans l'exercice, à-nouveaux compris (stock initial)."""
    total = (db.session.query(func.coalesce(func.sum(JournalLine.debit_cents - JournalLine.credit_cents), 0))
             .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
             .filter(JournalEntry.fiscal_year_id == fy.id, JournalLine.account_id == account_id).scalar())
    return int(total or 0)


def purchases_cents(fy: FiscalYear, prefix: str | None) -> int | None:
    """Repère du coût réel : charges de l'exercice sur le compte d'achat correspondant (hors à-nouveaux)."""
    if not prefix:
        return None
    from app.models.journal_entry import SOURCE_OPENING

    total = (db.session.query(func.coalesce(func.sum(JournalLine.debit_cents - JournalLine.credit_cents), 0))
             .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
             .join(Account, Account.id == JournalLine.account_id)
             .filter(JournalEntry.fiscal_year_id == fy.id, Account.code.like(f"{prefix}%"),
                     db.or_(JournalEntry.source.is_(None), JournalEntry.source != SOURCE_OPENING)).scalar())
    return int(total or 0)


def line_payload(line: StockLine, fy: FiscalYear, discount_map: dict) -> dict:
    unit, value, warnings = evaluate(line, fy, discount_map)
    found = classify(line.account.code)
    return {"id": line.id, "category": line.category, "account": {"id": line.account_id, "code": line.account.code,
                                                                  "label": line.account.label},
            "variation_account": {"id": line.variation_account_id, "code": line.variation_account.code},
            "label": line.label, "production": line.production, "quantity": str(line.quantity), "unit": line.unit,
            "method": line.method, "standard_id": line.standard_id,
            "standard": {"id": line.standard.id, "label": line.standard.label, "value_cents": line.standard.value_cents,
                         "unit": line.standard.unit, "year": line.standard.year} if line.standard else None,
            "market_price_cents": line.market_price_cents, "price_source": line.price_source,
            "price_reference": line.price_reference, "flat_rate": line.flat_rate,
            "unit_value_cents": unit if line.method != "actual" else line.unit_value_cents, "value_cents": value,
            "depreciation_cents": line.depreciation_cents, "depreciation_reason": line.depreciation_reason,
            "notes": line.notes, "warnings": warnings, "lot_id": line.lot_id, "heads": line.heads,
            "crop_advance_id": line.crop_advance_id, "fiscal": _fiscal(line, fy),
            "gap_reason": line.gap_reason,
            "purchase_account": found[1].get("purchase") if found else None}


def _fiscal(line: StockLine, fy: FiscalYear) -> dict:
    from app.services import stock_tax
    data = stock_tax.fiscal_value(line, fy)
    return {**data, "allowed": stock_tax.allowed(line, fy), "fiscal_reason": line.fiscal_reason,
            "manual_cents": line.fiscal_value_cents}


def overview(fy: FiscalYear) -> dict:
    discount_map = discounts(fy)
    lines = StockLine.query.filter_by(fiscal_year_id=fy.id).order_by(StockLine.position, StockLine.id).all()
    items = [line_payload(line, fy, discount_map) for line in lines]
    by_cat: dict[str, dict] = {}
    for item in items:
        row = by_cat.setdefault(item["category"], {"value_cents": 0, "depreciation_cents": 0, "lines": 0})
        row["value_cents"] += item["value_cents"] or 0
        row["depreciation_cents"] += item["depreciation_cents"] or 0
        row["lines"] += 1
    stock_accounts = Account.query.filter(db.or_(*[Account.code.like(f"{p}%") for p in ("31", "32", "33", "35", "37")]),
                                          Account.is_header.is_(False)).all()
    opening = []
    for account in stock_accounts:
        balance = _balance_before(fy, account.id)
        if balance:
            opening.append({"code": account.code, "label": account.label, "balance_cents": balance,
                            "counted": any(i["account"]["id"] == account.id for i in items)})
    purchase_hints = {}
    for cat in categories():
        for rule in cat["accounts"]:
            if rule.get("purchase") and rule["purchase"] not in purchase_hints:
                purchase_hints[rule["purchase"]] = purchases_cents(fy, rule["purchase"])
    row = settings(fy)
    return {"fiscal_year": {"id": fy.id, "label": fy.label, "end_date": fy.end_date.isoformat(), "status": fy.status},
            "editable": fy.status == "open", "items": items, "totals": by_cat,
            "total_cents": sum(i["value_cents"] or 0 for i in items), "discounts": discount_map,
            "counted_on": row.counted_on.isoformat() if row is not None and row.counted_on else None,
            "opening": sorted(opening, key=lambda o: o["code"]), "purchases": purchase_hints,
            "flat_allowed": flat_allowed(fy), "has_previous": previous_fiscal_year(fy) is not None,
            "lots": _lots(fy), "crop_advances": _advances(fy), "fiscal": _fiscal_totals(fy)}


def _fiscal_totals(fy: FiscalYear) -> dict:
    from app.services import stock_tax
    return stock_tax.totals(fy)


def _advances(fy: FiscalYear) -> list[dict]:
    from app.models import CropAdvance
    from app.services import crop_advances
    return [crop_advances.payload(a) for a in CropAdvance.query.filter_by(fiscal_year_id=fy.id).order_by(CropAdvance.id)]


def _lots(fy: FiscalYear) -> list[dict]:
    from app.services import stock_lots
    return stock_lots.lots_overview(fy)


def meta() -> dict:
    refs = price_references()
    return {"categories": [{"key": c["key"], "label": c["label"], "group": c["group"], "methods": c["methods"],
                            "retail": c["key"] not in RETAIL_FORBIDDEN,
                            "accounts": [{"prefix": r["prefix"], "variation": r["variation"]} for r in c["accounts"]]}
                           for c in categories()],
            "groups": [{"value": k, "label": v} for k, v in groups().items()],
            "methods": [{"value": k, "label": v} for k, v in STOCK_METHODS.items()],
            "units": [{"value": k, "label": v} for k, v in STOCK_UNITS.items()],
            "flat_rates": [{"value": k, "label": v} for k, v in FLAT_RATES.items()],
            "price_references": {"source": refs["source"], "week": refs["week"],
                                 "items": [{k: r[k] for k in ("key", "label", "unit", "min", "max")} for r in refs["references"]]},
            "standards": [standard_payload(s) for s in StockStandard.query.order_by(StockStandard.label, StockStandard.year.desc())]}


# ------------------------------------------------------------------ barèmes

def standard_payload(s: StockStandard) -> dict:
    return {"id": s.id, "key": s.key, "label": s.label, "unit": s.unit, "value_cents": s.value_cents, "year": s.year,
            "source": s.source}


def save_standard(row: StockStandard | None, data: dict) -> StockStandard:
    row = row or StockStandard()
    label = str(data.get("label", row.label) or "").strip()[:200]
    if not label:
        raise StockError("Libellé obligatoire.", "label")
    unit = data.get("unit", row.unit)
    if unit not in STOCK_UNITS:
        raise StockError("Unité inconnue.", "unit")
    year = data.get("year", row.year)
    if isinstance(year, bool) or not isinstance(year, int) or not 2000 <= year <= 2100:
        raise StockError("Année attendue.", "year")
    value = _cents(data.get("value_cents", row.value_cents), "value_cents", "Valeur", allow_none=False)
    key = str(data.get("key") or row.key or label).strip().lower()[:60]
    duplicate = StockStandard.query.filter(StockStandard.key == key, StockStandard.year == year)
    if row.id is not None:
        duplicate = duplicate.filter(StockStandard.id != row.id)
    if duplicate.first() is not None:
        raise StockError("Ce barème existe déjà pour cette année.", "key")
    row.key, row.label, row.unit, row.year, row.value_cents = key, label, unit, year, value
    row.source = str(data.get("source", row.source) or "").strip()[:300] or None
    if row.id is None:
        db.session.add(row)
    db.session.flush()
    return row


def delete_standard(row: StockStandard) -> None:
    if StockLine.query.filter_by(standard_id=row.id).join(FiscalYear).filter(FiscalYear.status != "open").first():
        raise StockError("Barème utilisé par l'inventaire d'un exercice clôturé.", status=409)
    StockLine.query.filter_by(standard_id=row.id).update({"standard_id": None})
    db.session.delete(row)
    db.session.flush()
