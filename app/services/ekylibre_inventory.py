"""Connecteur Ekylibre, lot AG11.d (claudedocs/design_connecteur_ekylibre.md § 5, Q-K4) : quantités d'inventaire.

Ekylibre donne la quantité **courante** de chaque matière (intrant, produit stocké), sans valeur ni date. Lyvre s'en
sert pour remplir les **quantités des lignes d'inventaire** de l'exercice (AG4, `stock_lines`), seulement si la
dernière lecture d'Ekylibre est faite **à 7 jours au plus** de la date d'inventaire (date de comptage saisie, sinon
fin d'exercice). Sinon, l'écart est affiché et rien n'est rempli.

- Les matières sont regroupées par **variante** (quantités additionnées, unité commune).
- Correspondance variante → ligne d'inventaire mémorisée par **compte et libellé** (`ekylibre_variant_links`) : elle
  suit les lignes reprises de l'exercice précédent. Une variante sans correspondance se rattache à une ligne
  existante, ou crée une ligne (compte de stock choisi).
- Unités : t, q et kg se convertissent entre elles, de même hl, l et m³ ; une unité inconnue ou incompatible
  n'est pas reportée (signalée).
- La **valeur** reste celle des méthodes d'AG4 : seule la quantité change (recalcul de la ligne).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models import Account, EkylibreVariantLink, FiscalYear, StockLine
from app.services import ekylibre_sync, stock_inventory
from app.services.stock_inventory import StockError

MAX_GAP_DAYS = 7
UNIT_ALIASES = {
    "t": "t", "tonne": "t", "tonnes": "t", "ton": "t", "q": "q", "quintal": "q", "quintaux": "q",
    "kg": "kg", "kilogram": "kg", "kilogramme": "kg", "kilogrammes": "kg",
    "hl": "hl", "hectolitre": "hl", "hectoliter": "hl", "l": "l", "litre": "l", "litres": "l", "liter": "l",
    "m3": "m3", "m³": "m3", "cubic_meter": "m3", "unit": "unit", "unité": "unit", "unite": "unit", "unity": "unit",
    "u": "unit", "head": "head", "tête": "head", "tete": "head", "têtes": "head",
}
# Facteur vers l'unité de base de chaque dimension (kg, l) ; unité, tête, ha : sans conversion.
FACTORS = {"t": ("mass", Decimal(1000)), "q": ("mass", Decimal(100)), "kg": ("mass", Decimal(1)),
           "m3": ("volume", Decimal(1000)), "hl": ("volume", Decimal(100)), "l": ("volume", Decimal(1))}


def _text(value: Decimal) -> str:
    """Quantité sans zéros inutiles ni notation scientifique (1700, 1.7)."""
    return f"{value.normalize():f}"


def lyvre_unit(raw: str | None) -> str | None:
    return UNIT_ALIASES.get((raw or "").strip().lower())


def convert(quantity: Decimal, source: str | None, target: str) -> Decimal | None:
    if source is None:
        return None
    if source == target:
        return quantity
    a, b = FACTORS.get(source), FACTORS.get(target)
    if a is None or b is None or a[0] != b[0]:
        return None
    return (quantity * a[1] / b[1]).quantize(Decimal("0.001"))


def inventory_date(fy: FiscalYear) -> date:
    row = stock_inventory.settings(fy)
    return row.counted_on if row is not None and row.counted_on else fy.end_date


def _variants() -> tuple[list[dict], object]:
    matters, synced_at = ekylibre_sync.snapshot("matters")
    groups: dict[int, dict] = {}
    for m in matters:
        if m.variant_id is None or m.quantity is None:
            continue
        unit = lyvre_unit(m.unit)
        group = groups.setdefault(m.variant_id, {"variant_id": m.variant_id, "name": m.name, "raw_unit": m.unit,
                                                 "unit": unit, "quantity": Decimal(0), "matters": 0, "mixed": False})
        if unit != group["unit"]:
            converted = convert(m.quantity, unit, group["unit"]) if group["unit"] else None
            if converted is None:
                group["mixed"] = True
                continue
            group["quantity"] += converted
        else:
            group["quantity"] += m.quantity
        group["matters"] += 1
    return sorted(groups.values(), key=lambda g: g["name"].lower()), synced_at


def _line_for(fy: FiscalYear, link: EkylibreVariantLink | None) -> StockLine | None:
    if link is None:
        return None
    return StockLine.query.filter_by(fiscal_year_id=fy.id, account_id=link.account_id, label=link.label).first()


def rows(fy: FiscalYear) -> dict:
    variants, synced_at = _variants()
    when = inventory_date(fy)
    gap = abs((synced_at.date() - when).days) if synced_at else None
    links = {l.variant_id: l for l in EkylibreVariantLink.query.all()}
    items = []
    for v in variants:
        link = links.get(v["variant_id"])
        line = _line_for(fy, link)
        converted = convert(v["quantity"], v["unit"], line.unit) if line is not None else None
        items.append({"variant_id": v["variant_id"], "name": v["name"], "matters": v["matters"],
                      "quantity": _text(v["quantity"]), "unit": v["unit"], "raw_unit": v["raw_unit"],
                      "mixed_units": v["mixed"],
                      "line": {"id": line.id, "label": line.label, "account": line.account.code,
                               "quantity": _text(Decimal(line.quantity)), "unit": line.unit} if line else None,
                      "link": {"account": link.account.code, "label": link.label} if link and line is None else None,
                      "converted": _text(converted) if converted is not None else None})
    return {"fiscal_year": {"id": fy.id, "label": fy.label, "open": fy.status == "open"},
            "inventory_date": when.isoformat(), "synced_at": synced_at.isoformat() if synced_at else None,
            "gap_days": gap, "allowed": gap is not None and gap <= MAX_GAP_DAYS, "max_gap_days": MAX_GAP_DAYS,
            "items": items,
            "lines": [{"value": str(l.id), "label": f"{l.account.code} — {l.label}", "unit": l.unit}
                      for l in StockLine.query.filter_by(fiscal_year_id=fy.id).order_by(StockLine.position, StockLine.id)]}


def _remember(variant_id: int, line: StockLine) -> None:
    link = EkylibreVariantLink.query.filter_by(variant_id=variant_id).first() or EkylibreVariantLink(variant_id=variant_id)
    link.account_id, link.label = line.account_id, line.label
    db.session.add(link)


def apply(fy: FiscalYear, items: list) -> dict:
    """`items` : `{variant_id, line_id?}` (ligne existante ou correspondance mémorisée) ou
    `{variant_id, create: {account_code, label?}}` ; quantité de la ligne = quantité Ekylibre convertie."""
    data = rows(fy)
    if not data["allowed"]:
        if data["synced_at"] is None:
            raise StockError("Ekylibre n'a pas encore été lu.", status=409)
        raise StockError(f"Lecture d'Ekylibre à {data['gap_days']} jours de la date d'inventaire "
                         f"({date.fromisoformat(data['inventory_date']):%d/%m/%Y}) : lisez Ekylibre à "
                         f"{MAX_GAP_DAYS} jours au plus.", status=409)
    if not isinstance(items, list) or not items:
        raise StockError("Aucune quantité choisie.", "items")
    variants = {v["variant_id"]: v for v in _variants()[0]}
    stats = {"filled": 0, "created": 0, "skipped": []}
    for item in items:
        vid = item.get("variant_id") if isinstance(item, dict) else None
        variant = variants.get(vid)
        if variant is None:
            raise StockError("Variante absente de la dernière lecture d'Ekylibre.", "items", 409)
        line = None
        if isinstance(item.get("line_id"), int):
            line = db.session.get(StockLine, item["line_id"])
            if line is None or line.fiscal_year_id != fy.id:
                raise StockError("Ligne d'inventaire introuvable.", "items", 404)
        elif isinstance(item.get("create"), dict):
            unit = variant["unit"] if variant["unit"] else "unit"
            account = Account.query.filter_by(code=str(item["create"].get("account_code") or "").strip()).first()
            label = str(item["create"].get("label") or variant["name"]).strip()[:200]
            line = stock_inventory.create_line(fy, {"account_code": account.code if account else
                                                    item["create"].get("account_code"), "label": label, "unit": unit,
                                                    "quantity": "0"})
            stats["created"] += 1
        else:
            line = _line_for(fy, EkylibreVariantLink.query.filter_by(variant_id=vid).first())
            if line is None:
                raise StockError(f"« {variant['name']} » : choisissez une ligne d'inventaire ou créez-la.", "items")
        quantity = convert(variant["quantity"], variant["unit"], line.unit)
        if quantity is None or variant["mixed"]:
            stats["skipped"].append(f"{variant['name']} ({variant['raw_unit'] or 'sans unité'} → {line.unit})")
            _remember(vid, line)
            continue
        stock_inventory.update_line(fy, line, {"quantity": str(quantity)})
        _remember(vid, line)
        stats["filled"] += 1
    db.session.commit()
    return stats
