"""Marge par activité et par atelier (lot AG8.d, claudedocs/design_analytique_agricole.md §§ 6 et 7, AGD25).

Pour chaque production (activité × campagne) de l'exercice :
- **production** : ventes, autres produits et aides affectés, variation des stocks de produits et en-cours des lignes
  d'inventaire de l'activité (stock final − stock initial), moins les achats d'animaux (RICA : production nette des
  achats d'animaux) ;
- **charges opérationnelles** : charges spécifiques végétaux et animaux (RICA) affectées, et variation des stocks
  d'approvisionnements correspondants (stock initial − stock final) ;
- **marge brute**, par unité de mesure (ha, tête) ;
- **charges de structure directes** : autres charges affectées, amortissements des immobilisations rattachées.
Classes : `data/analytic/margin_classes.yml`. Les lignes de dotation aux amortissements sont remplacées par les
dotations des fiches (activité de la fiche). Les lignes affectées à une clé « marge brute » attendent AG8.e.
Tous modes de tenue (sans inventaire ni amortissements en comptabilité simplifiée et au micro-BA).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path

import yaml

from app.extensions import db
from app.models import Activity, ActivityProduction, AnalyticKey, Campaign, FiscalYear, StockLine
from app.models.analytic import ACTIVITY_UNITS
from app.models.journal_entry import SOURCE_DEPRECIATION
from app.services import analytic, analytic_allocation as alloc

DATA = Path(__file__).resolve().parents[2] / "data" / "analytic" / "margin_classes.yml"
FULL = Decimal(10000)
SUMMED = ("production_cents", "operational_cents", "gross_margin_cents", "structure_cents", "result_cents",
          "auxiliary_cents", "result_after_cents")
UNALLOCATED = "unallocated"


@lru_cache(maxsize=1)
def _config() -> dict:
    return yaml.safe_load(DATA.read_text(encoding="utf-8"))


def classes() -> dict:
    return _config()["classes"]


def account_class(code: str, family: str | None = None) -> str | None:
    """Classe de marge d'un compte (préfixe le plus long), « by_family » résolu par la famille de l'atelier."""
    prefixes = _config()["prefixes"]
    best = max((p for p in prefixes if code.startswith(p)), key=len, default=None)
    if best is None:
        return None
    cls = prefixes[best]
    if cls == "by_family":
        return _config()["families"].get(family or "", "structure")
    return cls


def _bucket():
    return defaultdict(Decimal)


def _cents(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), ROUND_HALF_UP))


# ------------------------------------------------------------------ sources

def _lines(fy: FiscalYear, buckets: dict, unallocated: dict, deferred: dict, warnings: set) -> None:
    activities = {a.id: a for a in Activity.query.all()}
    for item in alloc.resolve_all(fy):
        if item["entry"].source == SOURCE_DEPRECIATION:
            continue                                            # remplacées par les dotations des fiches
        code, amount = item["account"].code, Decimal(item["amount_cents"])
        day = item["entry"].entry_date
        placed = Decimal(0)
        for target in item["targets"]:
            share = Decimal(target["share_bp"]) / FULL
            activity = activities.get(target["id"]) if target["kind"] == "activity" else None
            key = db.session.get(AnalyticKey, target["id"]) if target["kind"] == "key" else None
            if activity is None and key is None:
                continue
            spread = alloc.expand(activity, key, day, target.get("campaign_year"))
            warnings.update(spread["warnings"])
            if spread.get("deferred"):
                deferred[key.id][account_class(code) or "structure"] += amount * share
                placed += share
                continue
            for part in spread["parts"]:
                act = activities[part["activity_id"]]
                cls = account_class(code, act.workshop.family)
                if cls is None:
                    continue
                buckets[(act.id, part["campaign_year"])][cls] += amount * share * Decimal(part["share"])
            if spread["parts"]:
                placed += share
        rest = Decimal(1) - placed
        if rest > 0:
            cls = account_class(code)
            if cls is not None:
                unallocated[cls] += amount * rest


def _previous(fy: FiscalYear) -> FiscalYear | None:
    return FiscalYear.query.filter(FiscalYear.end_date == fy.start_date - timedelta(days=1)).first()


def _stock_side(line: StockLine) -> tuple[str, str]:
    """(sens, classe) d'une ligne d'inventaire : approvisionnements en charge, sinon production."""
    from app.services import stock_inventory as inv
    found = inv.classify(line.account.code)
    cat, rule = found if found else ({"group": None}, {})
    if cat.get("group") == "supplies":
        return "charge", account_class(rule.get("purchase") or rule.get("variation") or "60") or "structure"
    return "production", "stock_production"


def _stocks(fy: FiscalYear, buckets: dict, unallocated: dict, warnings: set) -> None:
    from app.services import stock_tax
    activities = {a.id: a for a in Activity.query.all()}
    values: dict[tuple, Decimal] = defaultdict(Decimal)
    for year, sign in ((fy, 1), (_previous(fy), -1)):
        if year is None:
            continue
        for line in StockLine.query.filter_by(fiscal_year_id=year.id):
            _unit, value = stock_tax._accounting(line, year)  # noqa: SLF001
            if value is None:
                warnings.add(f"Inventaire {year.label} : ligne « {line.label} » sans valeur.")
                continue
            side, cls = _stock_side(line)
            delta = Decimal(value) * sign * (1 if side == "production" else -1)
            values[(line.activity_id, cls)] += delta
    for (activity_id, cls), delta in values.items():
        if not delta:
            continue
        activity = activities.get(activity_id)
        if activity is None:
            unallocated[cls] += delta
        else:
            buckets[(activity.id, analytic.campaign_year(activity, fy.end_date))][cls] += delta


def _depreciation(fy: FiscalYear, buckets: dict, unallocated: dict) -> None:
    from app.models import Asset
    from app.services.assets import leaves, schedule
    activities = {a.id: a for a in Activity.query.all()}
    for asset in Asset.query.filter(Asset.parent_id.is_(None)):
        for leaf in leaves(asset):
            row = next((r for r in schedule(leaf) if r.fiscal_year_id == fy.id), None)
            if row is None or not row.amount_cents:
                continue
            activity = activities.get(leaf.activity_id or asset.activity_id)
            if activity is None:
                unallocated["depreciation"] += Decimal(row.amount_cents)
            else:
                buckets[(activity.id, analytic.campaign_year(activity, fy.end_date))]["depreciation"] += Decimal(row.amount_cents)


# ------------------------------------------------------------------ clé « marge brute » et auxiliaires (AG8.e)

def _gross_margins(buckets: dict) -> dict[int, Decimal]:
    out: dict[int, Decimal] = defaultdict(Decimal)
    for (activity_id, _year), values in buckets.items():
        s = _summary(values)
        out[activity_id] += Decimal(s["gross_margin_cents"])
    return out


def _weights(key: AnalyticKey, fy: FiscalYear, margins: dict, activities: dict) -> tuple[list[tuple], list[str]]:
    """[(activité, campagne, part)] d'une clé à la clôture ; base « marge brute » : marges brutes positives."""
    if key.basis == "gross_margin":
        raw = [(m.activity, max(margins.get(m.activity_id, Decimal(0)), Decimal(0))) for m in key.members]
        total = sum(w for _a, w in raw)
        if not total:
            return [], [f"Clé « {key.name} » : aucune marge brute positive pour répartir."]
        return [(a, analytic.campaign_year(a, fy.end_date), w / total) for a, w in raw if w], []
    spread = alloc.expand(None, key, fy.end_date)
    return [(activities[p["activity_id"]], p["campaign_year"], Decimal(p["share"])) for p in spread["parts"]], spread["warnings"]


def _resolve_deferred(fy, deferred, buckets, unallocated, activities, warnings) -> None:
    """Lignes affectées à une clé « marge brute » : au prorata des marges brutes positives des membres."""
    if not deferred:
        return
    margins = _gross_margins(buckets)
    for key_id, values in deferred.items():
        key = db.session.get(AnalyticKey, key_id)
        parts, notes = _weights(key, fy, margins, activities)
        warnings.update(notes)
        for cls, amount in values.items():
            if not parts:
                unallocated[cls] += amount
                continue
            for activity, year, share in parts:
                buckets[(activity.id, year)][cls] += amount * share


def _auxiliaries(fy, buckets, activities, warnings) -> dict:
    """Résultat des activités auxiliaires réparti sur les principales par la clé de chaque auxiliaire."""
    received: dict[tuple, Decimal] = defaultdict(Decimal)
    margins = _gross_margins(buckets)
    for (activity_id, year), values in list(buckets.items()):
        activity = activities[activity_id]
        if activity.nature != "auxiliary":
            continue
        result = Decimal(_summary(values)["result_cents"])
        if not result:
            continue
        if activity.distribution_key is None:
            warnings.add(f"Activité auxiliaire « {activity.name} » sans clé de répartition : son résultat reste sur elle.")
            continue
        parts, notes = _weights(activity.distribution_key, fy, margins, activities)
        warnings.update(notes)
        parts = [(a, y, w) for a, y, w in parts if a.nature == "main"]
        total = sum(w for *_x, w in parts)
        if not total:
            warnings.add(f"Activité auxiliaire « {activity.name} » : clé sans activité principale à servir.")
            continue
        received[(activity_id, year)] -= result
        for target, target_year, weight in parts:
            received[(target.id, target_year)] += result * weight / total
    for (activity_id, year) in received:                      # bénéficiaires sans ligne propre
        buckets[(activity_id, year)]
    return {"received": received}


# ------------------------------------------------------------------ rapprochement (AG8.e)

def reconciliation(fy: FiscalYear, rows: list[dict], unalloc: dict) -> dict:
    """Résultat comptable = activités + non affecté + hors analytique + écarts de méthode (stocks, amortissements)."""
    from app.models import Account, JournalEntry, JournalLine
    from app.services import closing
    accounting = closing.result(fy)["result_cents"]
    activities = sum(r["result_after_cents"] for r in rows)
    excluded = stock_lines = depreciation_lines = 0
    query = (db.session.query(JournalLine, JournalEntry.source, Account.code)
             .join(JournalEntry, JournalEntry.id == JournalLine.entry_id).join(Account, Account.id == JournalLine.account_id)
             .filter(JournalEntry.fiscal_year_id == fy.id, db.or_(Account.code.like("6%"), Account.code.like("7%"))))
    for line, source, code in query:
        value = line.credit_cents - line.debit_cents                       # contribution au résultat
        if code.startswith(("603", "713")):
            stock_lines += value
        elif source == SOURCE_DEPRECIATION:
            depreciation_lines += value
        elif not alloc.eligible_code(code) or source in alloc.EXCLUDED_SOURCES:
            excluded += value
    computed_stock = sum(r["classes"].get("stock_production", 0) for r in rows) \
        + unalloc["classes"].get("stock_production", 0)
    analytic_total = activities + unalloc["result_cents"]
    gap = accounting - analytic_total - excluded
    return {"accounting_result_cents": accounting, "activities_cents": activities, "unallocated_cents": unalloc["result_cents"],
            "excluded_cents": excluded, "stock_lines_cents": stock_lines, "depreciation_lines_cents": depreciation_lines,
            "computed_stock_cents": computed_stock, "method_gap_cents": gap,
            "note": "Écart de méthode : variations de stock prises sur l'inventaire de chaque activité (et non sur les "
                    "comptes 603 / 713), amortissements pris sur les fiches (et non sur l'écriture de dotation), "
                    "arrondis des clés."}


# ------------------------------------------------------------------ état

def _summary(values: dict) -> dict:
    get = lambda k: _cents(values.get(k, Decimal(0)))  # noqa: E731
    production = get("sales") + get("other_products") + get("aids") + get("stock_production") - get("animal_purchases")
    operational = get("plant_specific") + get("animal_specific")
    structure = get("structure") + get("depreciation")
    return {"classes": {k: get(k) for k in classes()}, "production_cents": production, "operational_cents": operational,
            "gross_margin_cents": production - operational, "structure_cents": structure,
            "result_cents": production - operational - structure}


def _measure(activity_id: int, year: int) -> Decimal | None:
    row = (ActivityProduction.query.join(Campaign)
           .filter(ActivityProduction.activity_id == activity_id, Campaign.year == year).first())
    return Decimal(row.measure) if row is not None and row.measure is not None else None


def _per_unit(cents: int, measure: Decimal | None) -> int | None:
    return _cents(Decimal(cents) / measure) if measure else None


def compute(fy: FiscalYear, campaign: int | None = None) -> dict:
    buckets: dict = defaultdict(_bucket)
    unallocated, deferred, warnings = _bucket(), defaultdict(_bucket), set()
    _lines(fy, buckets, unallocated, deferred, warnings)
    _stocks(fy, buckets, unallocated, warnings)
    _depreciation(fy, buckets, unallocated)
    activities = {a.id: a for a in Activity.query.all()}
    _resolve_deferred(fy, deferred, buckets, unallocated, activities, warnings)
    aux = _auxiliaries(fy, buckets, activities, warnings)
    rows = []
    for (activity_id, year), values in buckets.items():
        if campaign is not None and year != campaign:
            continue
        activity = activities[activity_id]
        summary = _summary(values)
        measure = _measure(activity_id, year)
        if measure is None and activity.nature == "main":
            warnings.add(f"{activity.name} : mesure de la campagne {year} à saisir (marge par unité).")
        received = _cents(aux["received"].get((activity_id, year), Decimal(0)))
        summary["auxiliary_cents"] = received
        summary["result_after_cents"] = summary["result_cents"] + received
        rows.append({"activity_id": activity_id, "activity": activity.name, "nature": activity.nature,
                     "distribution_key": activity.distribution_key.name if activity.distribution_key else None,
                     "workshop_id": activity.workshop_id, "workshop": activity.workshop.name,
                     "family": activity.workshop.family, "campaign_year": year, "unit": activity.unit,
                     "unit_label": ACTIVITY_UNITS.get(activity.unit, activity.unit),
                     "measure": format(measure.normalize(), "f") if measure is not None else None, **summary,
                     "gross_margin_per_unit_cents": _per_unit(summary["gross_margin_cents"], measure),
                     "production_per_unit_cents": _per_unit(summary["production_cents"], measure)})
    rows.sort(key=lambda r: (r["workshop"], r["activity"], r["campaign_year"]))
    workshops = {}
    for row in rows:
        w = workshops.setdefault(row["workshop_id"], {"workshop_id": row["workshop_id"], "workshop": row["workshop"],
                                                      "family": row["family"], "units": set(), "measure": Decimal(0),
                                                      **{k: 0 for k in SUMMED}})
        for k in SUMMED:
            w[k] += row[k]
        w["units"].add(row["unit"])
        if row["measure"] is not None and row["nature"] == "main":
            w["measure"] += Decimal(row["measure"])
    for w in workshops.values():
        single = len(w["units"]) == 1 and w["measure"] > 0
        w["unit_label"] = ACTIVITY_UNITS.get(next(iter(w["units"])), "") if single else None
        w["gross_margin_per_unit_cents"] = _per_unit(w["gross_margin_cents"], w["measure"]) if single else None
        w["measure"] = format(w["measure"].normalize(), "f") if single else None
        del w["units"]
    unalloc = _summary(unallocated)
    unalloc["auxiliary_cents"] = 0
    unalloc["result_after_cents"] = unalloc["result_cents"]
    return {"fiscal_year": {"id": fy.id, "label": fy.label, "start_date": fy.start_date.isoformat(),
                            "end_date": fy.end_date.isoformat(), "status": fy.status},
            "campaign": campaign, "campaigns": sorted({y for (_a, y) in buckets}), "productions": rows,
            "workshops": sorted(workshops.values(), key=lambda w: w["workshop"]), "unallocated": unalloc,
            "deferred_cents": 0,
            "reconciliation": reconciliation(fy, rows, unalloc) if campaign is None else None,
            "classes": [{"key": k, **v} for k, v in classes().items()], "warnings": sorted(warnings),
            "totals": _summary({k: sum((b.get(k, Decimal(0)) for b in buckets.values()), Decimal(0)) for k in classes()})}


# ------------------------------------------------------------------ figement et contrôles (AG8.e)

def view(fy: FiscalYear, campaign: int | None = None) -> dict:
    """État des marges : figé au premier calcul après la clôture définitive (vue complète), recalculé sinon."""
    import json
    from datetime import datetime

    from app.models import AnalyticSnapshot
    row = AnalyticSnapshot.query.filter_by(fiscal_year_id=fy.id).first()
    if fy.status == "closed" and campaign is None:
        if row is not None:
            return json.loads(row.snapshot_json)
        data = compute(fy)
        data.update(frozen=True, frozen_at=datetime.utcnow().isoformat(timespec="seconds"))
        db.session.add(AnalyticSnapshot(fiscal_year_id=fy.id, snapshot_json=json.dumps(data)))
        db.session.commit()
        return data
    if row is not None and fy.status != "closed":                  # exercice rouvert : recalcul
        db.session.delete(row)
        db.session.commit()
    data = compute(fy, campaign)
    data.update(frozen=False, frozen_at=None)
    return data


def checks(fy: FiscalYear) -> list[tuple[str, str, int, str]]:
    """Contrôles de clôture de l'analytique, seulement si des activités existent."""
    if not analytic.enabled() or Activity.query.filter(Activity.archived.is_(False)).first() is None:
        return []
    found = []
    cover = alloc.coverage(alloc.resolve_all(fy))
    for side, label in (("charges", "charges"), ("products", "produits")):
        ratio = cover[side]["ratio_bp"]
        if ratio is not None and ratio < 8000:
            found.append((f"analytic_coverage_{side}", f"Analytique : {ratio / 100:.0f} % des {label} affectés (moins de 80 %)"
                          .replace(".", ","), 1, "info"))
    missing = []
    for activity in Activity.query.filter(Activity.archived.is_(False), Activity.nature == "main"):
        year = analytic.campaign_year(activity, fy.end_date)
        row = (ActivityProduction.query.join(Campaign)
               .filter(ActivityProduction.activity_id == activity.id, Campaign.year == year).first())
        if row is None or row.measure is None:
            missing.append(activity.name)
    if missing:
        found.append(("analytic_measures", f"Activités sans surface ni effectif sur leur campagne : {', '.join(missing[:5])}"
                      + ("…" if len(missing) > 5 else ""), len(missing), "info"))
    keys = [k.name for k in AnalyticKey.query.filter(AnalyticKey.archived.is_(False)) if alloc.key_payload(k)["warnings"]]
    if keys:
        found.append(("analytic_keys", f"Clés de répartition incomplètes : {', '.join(keys)}", len(keys), "info"))
    orphans = [a.name for a in Activity.query.filter(Activity.archived.is_(False), Activity.nature == "auxiliary",
                                                     Activity.distribution_key_id.is_(None))]
    if orphans:
        found.append(("analytic_auxiliaries", f"Activités auxiliaires sans clé de répartition : {', '.join(orphans)}",
                      len(orphans), "info"))
    return found
