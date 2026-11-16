"""Agronomie d'une restauration Ekylibre (lot RE4, claudedocs/design_restauration_ekylibre.md § 8, Q7).

- **Activités** : une activité Lyvre par activité Ekylibre (`ekylibre_id`), atelier de sa famille, nature, cycle
  et unité d'Ekylibre ; une activité suspendue est archivée.
- **Campagnes** : une par exercice repris (année de fin), plus les campagnes d'Ekylibre des cultures de la période.
- **Surfaces** : pour chaque activité en hectares et chaque campagne, somme des cultures (`activity_productions`)
  rattachées à la campagne, ou en place cette année-là ; mesure `measure_source = "ekylibre"`, comme AG11.
- **Dernier inventaire** : les inventaires d'Ekylibre passés en comptabilité (`reflected`) du dernier exercice repris
  qui en a ; une ligne d'inventaire Lyvre par article compté (quantité, unité, valeur unitaire), sur le compte de
  stock de l'écriture d'inventaire d'Ekylibre. **Aucune écriture** (D-R2 révisé) : un contrôle compare la valeur
  reprise au solde des comptes de stock à la fin de l'exercice.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.services.ekylibre.data import EkyData, cents, day

UNITS = {"hectare": "hectare", "unity": "unity", "unit": "unity", "head": "head", "square_meter": "square_meter",
         "cubic_meter": "cubic_meter"}
STOCK_UNITS = {"hl": "hl", "hectoliter": "hl", "litre": "l", "liter": "l", "l": "l", "kg": "kg", "kilogram": "kg",
               "t": "t", "ton": "t", "tonne": "t", "quintal": "q", "q": "q", "m3": "m3", "cubic_meter": "m3",
               "head": "head", "hectare": "ha", "ha": "ha"}


def _year_bounds(year: int) -> tuple[date, date]:
    return date(year, 1, 1), date(year, 12, 31)


def campaign_years(data: EkyData) -> list[int]:
    years = {day(fy["stopped_on"]).year for fy in data.rows["financial_years"]
             if day(fy["stopped_on"]) >= data.start and day(fy["started_on"]) <= data.until}
    harvests = {c["id"]: int(c["harvest_year"]) for c in data.rows["campaigns"] if c.get("harvest_year")}
    for production in data.rows["activity_productions"]:
        year = harvests.get(production.get("campaign_id"))
        if year is not None and data.start.year <= year <= data.until.year:
            years.add(year)
    return sorted(years)


def surfaces(data: EkyData) -> dict[tuple[str, int], Decimal]:
    """(activité Ekylibre, campagne) → hectares ; seulement les activités mesurées en surface nette (ha)."""
    in_hectares = {a["id"] for a in data.rows["activities"]
                   if a.get("size_indicator_name") == "net_surface_area" and a.get("size_unit_name") == "hectare"}
    harvests = {c["id"]: int(c["harvest_year"]) for c in data.rows["campaigns"] if c.get("harvest_year")}
    out: dict[tuple[str, int], Decimal] = defaultdict(Decimal)
    for year in campaign_years(data):
        first, last = _year_bounds(year)
        for p in data.rows["activity_productions"]:
            if p.get("activity_id") not in in_hectares or not p.get("size_value") or p.get("state") == "aborted":
                continue
            if p.get("campaign_id"):
                active = harvests.get(p["campaign_id"]) == year
            else:
                started, stopped = day(p.get("started_on")), day(p.get("stopped_on"))
                active = (started is None or started <= last) and (stopped is None or stopped >= first)
            if active:
                out[(p["activity_id"], year)] += Decimal(p["size_value"])
    return dict(out)


@dataclass
class InventoryLine:
    number: str            # compte de stock Ekylibre
    label: str
    quantity: Decimal
    unit: str
    unit_value: Decimal    # euros par unité
    value: int             # centimes


@dataclass
class Inventory:
    fiscal_year: dict
    names: list = field(default_factory=list)
    lines: list = field(default_factory=list)
    skipped: int = 0       # articles comptés à zéro

    @property
    def total(self) -> int:
        return sum(line.value for line in self.lines)

    def by_account(self) -> Counter:
        out = Counter()
        for line in self.lines:
            out[line.number] += line.value
        return out


def _stock_unit(variant: dict) -> str:
    for raw in (variant.get("unit_name"), variant.get("default_unit_name")):
        unit = STOCK_UNITS.get((raw or "").strip().lower())
        if unit:
            return unit
    return "unit"


def last_inventory(data: EkyData) -> Inventory | None:
    """Inventaires passés en comptabilité du dernier exercice repris qui en a."""
    years = {fy["id"]: fy for fy in data.rows["financial_years"]
             if day(fy["stopped_on"]) >= data.start and day(fy["stopped_on"]) <= data.until}
    reflected = [i for i in data.rows["inventories"] if i.get("reflected") == "t" and i.get("financial_year_id") in years]
    if not reflected:
        return None
    fy = max((years[i["financial_year_id"]] for i in reflected), key=lambda f: f["stopped_on"])
    chosen = sorted((i for i in reflected if i["financial_year_id"] == fy["id"]), key=lambda i: (i.get("name") or "", i["id"]))
    products = {p["id"]: p for p in data.rows["products"]}
    variants = {v["id"]: v for v in data.rows["product_nature_variants"]}
    categories = {c["id"]: c for c in data.rows["product_nature_categories"]}
    inventory = Inventory(fiscal_year=fy, names=[i.get("name") or i.get("number") or i["id"] for i in chosen])
    for inv in chosen:
        booked = Counter()                                   # comptes de stock de l'écriture d'inventaire
        for item in data.items_by_entry.get(inv.get("journal_entry_id"), []):
            number = data.account_number(item["account_id"]) or ""
            if number.startswith("3"):
                booked[number] += abs(cents(item["real_debit"]) - cents(item["real_credit"]))
        fallback = data.account_number((categories.get(inv.get("product_nature_category_id")) or {}).get("stock_account_id"))
        for item in (x for x in data.rows["inventory_items"] if x["inventory_id"] == inv["id"]):
            quantity = Decimal(item.get("actual_population") or 0)
            if not quantity:
                inventory.skipped += 1
                continue
            product = products.get(item.get("product_id")) or {}
            variant = variants.get(product.get("variant_id")) or {}
            own = data.account_number((categories.get(product.get("category_id")) or {}).get("stock_account_id"))
            if booked:
                number = own if own in booked else booked.most_common(1)[0][0]
            else:
                number = own or fallback
            if not number:
                continue
            unit_value = Decimal(item.get("unit_pretax_stock_amount") or 0)
            value = int((quantity * unit_value * 100).quantize(Decimal(1), ROUND_HALF_UP))
            inventory.lines.append(InventoryLine(number, (product.get("name") or variant.get("name") or "Article")[:200],
                                                 quantity, _stock_unit(variant), unit_value, value))
    return inventory


def stock_control(data: EkyData, inventory: Inventory) -> list[tuple[str, int, int]]:
    """(compte Ekylibre, valeur de l'inventaire, solde du compte à la fin de l'exercice) pour chaque compte de stock."""
    end = day(inventory.fiscal_year["stopped_on"])
    from datetime import timedelta
    balances = data.balances_before(end + timedelta(days=1))
    values = inventory.by_account()
    numbers = set(values) | {n for n, v in balances.items() if n and n[:1] == "3" and n[:2] != "39" and v}
    return [(n, values.get(n, 0), balances.get(n, 0)) for n in sorted(numbers)]


# ------------------------------------------------------------------ écriture dans Lyvre (importeur)


def import_activities(ctx) -> None:
    from app.models import Activity
    from app.models.analytic import ACTIVITY_CYCLES, ACTIVITY_FAMILIES, ACTIVITY_NATURES
    from app.services import analytic
    from app.services.import_activities import _workshop
    data = ctx.data
    for row in sorted(data.rows["activities"], key=lambda a: int(a["id"])):
        family = row.get("family") if row.get("family") in ACTIVITY_FAMILIES else "plant_farming"
        activity = Activity.query.filter_by(ekylibre_id=int(row["id"])).first()
        if activity is None:
            activity = analytic.save_activity(None, {
                "workshop_id": _workshop(family).id, "name": (row.get("name") or f"Activité {row['id']}")[:120],
                "nature": row.get("nature") if row.get("nature") in ACTIVITY_NATURES else "main",
                "cycle": row.get("production_cycle") if row.get("production_cycle") in ACTIVITY_CYCLES else "annual",
                "unit": UNITS.get(row.get("size_unit_name") or "", "unity"),
                "archived": row.get("suspended") == "t"})
            activity.ekylibre_id = int(row["id"])
            ctx.stats["activities"] += 1
        ctx.activities[row["id"]] = activity
    for year in campaign_years(data):
        analytic.ensure_campaign(year)
        ctx.stats["campaigns"] += 1
    for (eky_id, year), surface in sorted(surfaces(data).items()):
        activity = ctx.activities.get(eky_id)
        if activity is None or activity.unit != "hectare":
            continue
        analytic.set_measure(activity.id, year, {"measure": str(surface), "source": "ekylibre",
                                                 "note": "Surface des cultures Ekylibre (reprise)"})
        ctx.stats["surfaces"] += 1


def import_inventory(ctx) -> None:
    from app.services import stock_inventory
    from app.services.stock_inventory import StockError
    inventory = last_inventory(ctx.data)
    ctx.inventory = inventory
    if inventory is None:
        return
    fy = ctx.years.get(inventory.fiscal_year["id"])
    if fy is None:
        return
    for line in inventory.lines:
        target = ctx.accounts.get(line.number)
        if target is None:
            ctx.notes.append(f"Inventaire : « {line.label} » sur le compte {line.number}, absent des comptes repris.")
            continue
        unit_cents = int((line.unit_value * 100).quantize(Decimal(1), ROUND_HALF_UP))
        try:
            stock_line = stock_inventory.create_line(fy, {"account_code": target.code, "label": line.label,
                                                          "unit": line.unit, "quantity": str(line.quantity),
                                                          "method": "actual", "unit_value_cents": unit_cents})
        except StockError as exc:
            ctx.notes.append(f"Inventaire : « {line.label} » ({target.code}) non repris : {exc}")
            continue
        stock_line.notes = f"Inventaire Ekylibre ({', '.join(inventory.names)})"
        ctx.stats["stock_lines"] += 1
    if inventory.skipped:
        ctx.notes.append(f"Inventaire : {inventory.skipped} article(s) compté(s) à zéro non repris.")
