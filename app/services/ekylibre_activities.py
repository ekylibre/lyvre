"""Connecteur Ekylibre, lot AG11.b (claudedocs/design_connecteur_ekylibre.md § 3) : activités et surfaces.

Lu dans l'instantané local (`ekylibre_sync.snapshot("productions")`), jamais dans l'API :
- chaque culture Ekylibre porte son activité (`activity_id`, `activity_name`), sa surface et sa période ;
- une activité Ekylibre est **rapprochée** d'une activité Lyvre par `activities.ekylibre_id`, sinon par son nom
  (mêmes mots, accents et pluriels ignorés), sinon par sa production Lexicon ; à défaut, elle est **proposée**
  à la création (atelier de sa famille, production Lexicon reconnue) ;
- **campagne** d'une culture : celle de sa date de fin de production (récolte), sinon de début, par la règle de
  l'activité Lyvre (`analytic.campaign_year`) ;
- **surface** : somme des cultures de l'activité par campagne, reportée comme mesure (`measure_source = ekylibre`).
  Une mesure **saisie** n'est jamais écrasée : l'écart est signalé.
- **contrôle** : surface des cultures d'une campagne comparée à la surface des parcelles (dérobées et cultures
  associées expliquent un dépassement : simple avertissement).
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from app.extensions import db
from app.models import Activity, ActivityProduction, Campaign
from app.models.analytic import ACTIVITY_FAMILIES
from app.services import analytic, ekylibre_sync
from app.services.import_activities import _existing_activity, _words, _workshop, match_production


class EkylibreActivityError(ValueError):
    def __init__(self, message, field=None, status=422):
        super().__init__(message)
        self.message, self.field, self.status = message, field, status


def _match(eky_id: int, name: str) -> tuple[Activity | None, str | None]:
    found = Activity.query.filter_by(ekylibre_id=eky_id, archived=False).first()
    if found is not None:
        return found, "ekylibre"
    words = _words(name)
    found = next((a for a in Activity.query.filter_by(archived=False) if _words(a.name) == words), None)
    if found is not None:
        return found, "name"
    production = match_production(name)
    if production is not None:
        found = _existing_activity(production["name"], production["reference"])
        if found is not None:
            return found, "lexicon"
    return None, None


def _campaign(production, activity: Activity | None) -> int | None:
    day = production.stopped_on or production.started_on
    if day is None:
        return None
    return analytic.campaign_year(activity, day) if activity is not None else day.year


def _grouped():
    productions, synced_at = ekylibre_sync.snapshot("productions")
    groups: dict[int, dict] = {}
    for p in productions:
        if p.activity_id is None or not p.surface_ha:
            continue
        group = groups.setdefault(p.activity_id, {"name": p.activity_name or f"Activité {p.activity_id}", "items": []})
        group["items"].append(p)
    return groups, synced_at


def _surfaces(items, activity: Activity | None) -> dict[int, Decimal]:
    out: dict[int, Decimal] = defaultdict(Decimal)
    for p in items:
        year = _campaign(p, activity)
        if year is not None:
            out[year] += p.surface_ha
    return dict(out)


def _measure(activity: Activity, year: int) -> ActivityProduction | None:
    campaign = Campaign.query.filter_by(year=year).first()
    return ActivityProduction.query.filter_by(activity_id=activity.id, campaign_id=campaign.id).first() if campaign else None


def rows() -> dict:
    groups, synced_at = _grouped()
    out = []
    for eky_id, group in sorted(groups.items(), key=lambda g: g[1]["name"].lower()):
        activity, how = _match(eky_id, group["name"])
        production = match_production(group["name"]) if activity is None else None
        campaigns = []
        for year, surface in sorted(_surfaces(group["items"], activity).items()):
            known = _measure(activity, year) if activity is not None and activity.unit == "hectare" else None
            state = "new"
            if known is not None and known.measure is not None:
                same = abs(Decimal(known.measure) - surface) < Decimal("0.001")
                state = "same" if same else ("update" if known.measure_source == "ekylibre" else "conflict")
            campaigns.append({"year": year, "surface_ha": str(surface.quantize(Decimal("0.01"))),
                              "lyvre_ha": str(known.measure) if known is not None and known.measure is not None else None,
                              "state": state})
        out.append({"ekylibre_id": eky_id, "name": group["name"], "productions": len(group["items"]),
                    "activity": {"id": activity.id, "name": activity.name, "how": how,
                                 "unit": activity.unit} if activity else None,
                    "proposal": None if activity else {"name": production["name"] if production else group["name"],
                                                       "lexicon_reference": production["reference"] if production else None},
                    "campaigns": campaigns})
    return {"synced_at": synced_at.isoformat() if synced_at else None, "items": out, "warnings": checks(groups)}


def checks(groups) -> list[str]:
    parcels, _ = ekylibre_sync.snapshot("parcels")
    total = sum((p.surface_ha or Decimal(0) for p in parcels if p.dead_at is None), Decimal(0))
    by_year: dict[int, Decimal] = defaultdict(Decimal)
    for group in groups.values():
        for p in group["items"]:
            day = p.stopped_on or p.started_on
            if day is not None:
                by_year[day.year] += p.surface_ha
    out = []
    for year, surface in sorted(by_year.items()):
        if total and surface > total * Decimal("1.01"):
            out.append(f"Campagne {year} : {surface:.2f} ha de cultures pour {total:.2f} ha de parcelles "
                       "(dérobées ou cultures associées ? à vérifier dans Ekylibre).")
    return out


def apply(items: list) -> dict:
    """`items` : `{ekylibre_id, activity_id?}` (rattacher à une activité existante) ou `{ekylibre_id, create: true,
    name?}` ; puis surfaces de chaque campagne (sauf mesure saisie)."""
    if not isinstance(items, list) or not items:
        raise EkylibreActivityError("Aucune activité choisie.", "items")
    groups, _ = _grouped()
    stats = {"linked": 0, "created": 0, "measures": 0, "conflicts": 0}
    for item in items:
        eky_id = item.get("ekylibre_id") if isinstance(item, dict) else None
        group = groups.get(eky_id)
        if group is None:
            raise EkylibreActivityError("Activité Ekylibre absente de la dernière lecture.", "items", 409)
        activity = None
        if isinstance(item.get("activity_id"), int):
            activity = db.session.get(Activity, item["activity_id"])
            if activity is None:
                raise EkylibreActivityError("Activité Lyvre introuvable.", "items", 404)
        elif item.get("create"):
            production = match_production(group["name"])
            name = str(item.get("name") or (production["name"] if production else group["name"])).strip()[:120]
            activity = _existing_activity(name, production["reference"] if production else None)
            if activity is None:
                family = production["family"] if production and production.get("family") in ACTIVITY_FAMILIES \
                    else "plant_farming"
                data = {"workshop_id": _workshop(family).id, "name": name}
                if production:
                    data["lexicon_reference"] = production["reference"]
                activity = analytic.save_activity(None, data)
                stats["created"] += 1
        else:
            activity, _ = _match(eky_id, group["name"])
            if activity is None:
                raise EkylibreActivityError(f"« {group['name']} » : choisissez une activité ou créez-la.", "items")
        other = Activity.query.filter(Activity.ekylibre_id == eky_id, Activity.id != activity.id).first()
        if other is not None:
            other.ekylibre_id = None
        if activity.ekylibre_id != eky_id:
            activity.ekylibre_id = eky_id
            stats["linked"] += 1
        if activity.unit != "hectare":
            continue
        for year, surface in _surfaces(group["items"], activity).items():
            known = _measure(activity, year)
            if known is not None and known.measure is not None and known.measure_source != "ekylibre":
                if abs(Decimal(known.measure) - surface) >= Decimal("0.001"):
                    stats["conflicts"] += 1
                continue
            analytic.set_measure(activity.id, year, {"measure": str(surface), "source": "ekylibre",
                                                     "note": "Surface des cultures Ekylibre"})
            stats["measures"] += 1
    db.session.commit()
    return stats
