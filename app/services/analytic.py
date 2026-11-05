"""Analytique agricole par activité (lot AG8.a, claudedocs/design_analytique_agricole.md §§ 2 et 3, AGD25).

- **Atelier** → **activité** (production Lexicon facultative, nature, cycle, unité, dates théoriques de cycle) →
  **production** (activité × campagne, mesure : surface ou effectif).
- **Campagne d'une date** pour une activité : année de fin du cycle qui contient la date, ou du cycle suivant si la date
  tombe entre deux cycles (blé d'hiver du 01/10 au 31/08 : une ligne du 15/10/2025 va sur la campagne 2026).
- Productions de Lexicon : `data/analytic/lexicon_productions.json` (CC-BY-SA 4.0, Ekylibre SAS), régénéré par
  `scripts/build_lexicon_productions.py`.
- Instances agricoles, tous modes de tenue (partie double, simplifiée, micro-BA).
"""
from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path

from app.extensions import db
from app.models import Activity, ActivityProduction, Campaign, Workshop
from app.models.analytic import ACTIVITY_CYCLES, ACTIVITY_FAMILIES, ACTIVITY_NATURES, ACTIVITY_UNITS

LEXICON_FILE = Path(__file__).resolve().parents[2] / "data" / "analytic" / "lexicon_productions.json"
MMDD = re.compile(r"^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")


class AnalyticError(Exception):
    def __init__(self, message, field=None, status=422):
        super().__init__(message)
        self.message, self.field, self.status = message, field, status


def enabled() -> bool:
    from app.tenant import is_agri
    return is_agri()


# ------------------------------------------------------------------ Lexicon

@lru_cache(maxsize=1)
def _lexicon() -> dict:
    return json.loads(LEXICON_FILE.read_text(encoding="utf-8"))


def lexicon_source() -> dict:
    return _lexicon()["_source"]


def lexicon_production(reference: str | None) -> dict | None:
    if not reference:
        return None
    return next((p for p in _lexicon()["productions"] if p["reference"] == reference), None)


def lexicon_search(query: str = "", family: str | None = None, limit: int = 50) -> list[dict]:
    words = [w for w in re.split(r"\s+", (query or "").strip().lower()) if w]
    out = []
    for p in _lexicon()["productions"]:
        if family and p["family"] != family:
            continue
        text = f"{p['name']} {p['reference']}".lower()
        if all(w in text for w in words):
            out.append(p)
            if len(out) >= limit:
                break
    return out


# ------------------------------------------------------------------ campagnes

def _day(year: int, mmdd: str) -> date:
    month, day = int(mmdd[:2]), int(mmdd[3:])
    while True:
        try:
            return date(year, month, day)
        except ValueError:                     # 29/02 hors année bissextile, 31 d'un mois de 30 jours
            day -= 1


def cycle_bounds(activity: Activity, year: int) -> tuple[date, date]:
    """Début et fin du cycle de la campagne `year`."""
    return _day(year - activity.year_offset, activity.cycle_start), _day(year, activity.cycle_stop)


def campaign_year(activity: Activity, day: date) -> int:
    """Campagne d'une date : la première campagne dont le cycle se termine à cette date ou après."""
    year = day.year
    while cycle_bounds(activity, year)[1] < day:
        year += 1
    return year


def ensure_campaign(year: int) -> Campaign:
    campaign = Campaign.query.filter_by(year=year).first()
    if campaign is None:
        campaign = Campaign(year=year)
        db.session.add(campaign)
        db.session.flush()
    return campaign


# ------------------------------------------------------------------ vues

def _measure(value) -> str | None:
    if value is None:
        return None
    return format(Decimal(value).normalize(), "f")


def activity_payload(activity: Activity, campaign_year_: int | None = None) -> dict:
    lex = lexicon_production(activity.lexicon_reference)
    out = {"id": activity.id, "workshop_id": activity.workshop_id, "name": activity.name,
           "lexicon_reference": activity.lexicon_reference, "lexicon_name": lex["name"] if lex else None,
           "nature": activity.nature, "nature_label": ACTIVITY_NATURES.get(activity.nature, activity.nature),
           "cycle": activity.cycle, "unit": activity.unit, "unit_label": ACTIVITY_UNITS.get(activity.unit, activity.unit),
           "cycle_start": activity.cycle_start, "cycle_stop": activity.cycle_stop, "year_offset": activity.year_offset,
           "isacompta_code": activity.isacompta_code, "archived": activity.archived,
           "distribution_key_id": activity.distribution_key_id,
           "distribution_key": activity.distribution_key.name if activity.distribution_key else None}
    if campaign_year_ is not None:
        start, stop = cycle_bounds(activity, campaign_year_)
        production = (ActivityProduction.query.join(Campaign)
                      .filter(ActivityProduction.activity_id == activity.id, Campaign.year == campaign_year_).first())
        out["campaign"] = {"year": campaign_year_, "start": start.isoformat(), "stop": stop.isoformat(),
                           "measure": _measure(production.measure) if production else None,
                           "production_id": production.id if production else None}
    return out


def workshop_payload(workshop: Workshop, campaign_year_: int | None = None) -> dict:
    return {"id": workshop.id, "name": workshop.name, "family": workshop.family,
            "family_label": ACTIVITY_FAMILIES.get(workshop.family, workshop.family),
            "isacompta_code": workshop.isacompta_code, "position": workshop.position, "archived": workshop.archived,
            "activities": [activity_payload(a, campaign_year_) for a in workshop.activities]}


def listing(campaign_year_: int | None = None, include_archived: bool = False) -> dict:
    query = Workshop.query.order_by(Workshop.position, Workshop.name)
    if not include_archived:
        query = query.filter(Workshop.archived.is_(False))
    workshops = [workshop_payload(w, campaign_year_) for w in query]
    if not include_archived:
        for w in workshops:
            w["activities"] = [a for a in w["activities"] if not a["archived"]]
    totals: dict[str, Decimal] = {}
    for w in workshops:
        for a in w["activities"]:
            m = (a.get("campaign") or {}).get("measure")
            if m is not None:
                totals[a["unit"]] = totals.get(a["unit"], Decimal(0)) + Decimal(m)
    return {"campaign": campaign_year_, "workshops": workshops,
            "totals": [{"unit": u, "unit_label": ACTIVITY_UNITS.get(u, u), "measure": _measure(v)} for u, v in totals.items()],
            "campaigns": [c.year for c in Campaign.query.order_by(Campaign.year.desc())]}


def meta() -> dict:
    options = lambda d: [{"value": k, "label": v} for k, v in d.items()]  # noqa: E731
    return {"families": options(ACTIVITY_FAMILIES), "natures": options(ACTIVITY_NATURES), "cycles": options(ACTIVITY_CYCLES),
            "units": options(ACTIVITY_UNITS), "lexicon": lexicon_source()}


# ------------------------------------------------------------------ saisie

def _text(value, field: str, limit: int, required: bool = False) -> str | None:
    text = str(value or "").strip()[:limit]
    if required and not text:
        raise AnalyticError("Champ obligatoire.", field)
    return text or None


def save_workshop(workshop: Workshop | None, data: dict) -> Workshop:
    creating = workshop is None
    workshop = workshop or Workshop()
    if creating or "name" in data:
        name = _text(data.get("name"), "name", 120, required=True)
        other = Workshop.query.filter(Workshop.name == name, Workshop.id != (workshop.id or 0)).first()
        if other is not None:
            raise AnalyticError("Un atelier porte déjà ce nom.", "name", 409)
        workshop.name = name
    if creating or "family" in data:
        if data.get("family") not in ACTIVITY_FAMILIES:
            raise AnalyticError("Famille d'activités inconnue.", "family")
        workshop.family = data["family"]
    if "isacompta_code" in data:
        workshop.isacompta_code = _text(data.get("isacompta_code"), "isacompta_code", 20)
    if "position" in data:
        if isinstance(data["position"], bool) or not isinstance(data["position"], int):
            raise AnalyticError("Rang entier attendu.", "position")
        workshop.position = data["position"]
    if "archived" in data:
        workshop.archived = bool(data["archived"])
    if creating:
        db.session.add(workshop)
    db.session.flush()
    return workshop


def delete_workshop(workshop: Workshop) -> None:
    if workshop.activities:
        raise AnalyticError("Atelier avec des activités : supprimez-les ou archivez l'atelier.", status=409)
    db.session.delete(workshop)


def save_activity(activity: Activity | None, data: dict) -> Activity:
    creating = activity is None
    activity = activity or Activity()
    if creating or "workshop_id" in data:
        workshop = db.session.get(Workshop, data.get("workshop_id")) if isinstance(data.get("workshop_id"), int) else None
        if workshop is None:
            raise AnalyticError("Atelier introuvable.", "workshop_id")
        activity.workshop_id = workshop.id
    lex = None
    if "lexicon_reference" in data:
        reference = _text(data.get("lexicon_reference"), "lexicon_reference", 80)
        lex = lexicon_production(reference)
        if reference and lex is None:
            raise AnalyticError("Production Lexicon inconnue.", "lexicon_reference")
        activity.lexicon_reference = reference
    if creating or "name" in data:
        name = _text(data.get("name") or (lex or {}).get("name"), "name", 120, required=True)
        other = Activity.query.filter(Activity.workshop_id == activity.workshop_id, Activity.name == name,
                                      Activity.id != (activity.id or 0)).first()
        if other is not None:
            raise AnalyticError("Une activité de cet atelier porte déjà ce nom.", "name", 409)
        activity.name = name
    if lex is not None and not data.get("keep_cycle"):           # dates, unité et cycle repris de Lexicon
        activity.cycle_start, activity.cycle_stop, activity.year_offset = lex["start"], lex["stop"], lex["year_offset"]
        if lex["unit"] in ACTIVITY_UNITS:
            activity.unit = lex["unit"]
        activity.cycle = "perennial" if lex.get("life_duration") else "annual"
    for field, choices in (("nature", ACTIVITY_NATURES), ("cycle", ACTIVITY_CYCLES), ("unit", ACTIVITY_UNITS)):
        if field in data:
            if data[field] not in choices:
                raise AnalyticError("Valeur inconnue.", field)
            setattr(activity, field, data[field])
    for field in ("cycle_start", "cycle_stop"):
        if field in data:
            value = str(data[field] or "")
            if not MMDD.match(value):
                raise AnalyticError("Jour et mois attendus (MM-JJ).", field)
            setattr(activity, field, value)
    if "year_offset" in data:
        if data["year_offset"] not in (0, 1):
            raise AnalyticError("Le cycle commence l'année de la campagne (0) ou l'année précédente (1).", "year_offset")
        activity.year_offset = data["year_offset"]
    if activity.year_offset == 0 and (activity.cycle_start or "01-01") > (activity.cycle_stop or "12-31"):
        raise AnalyticError("Cycle à cheval sur deux années : il commence l'année précédente (décalage 1).", "year_offset")
    if "isacompta_code" in data:
        activity.isacompta_code = _text(data.get("isacompta_code"), "isacompta_code", 20)
    if "distribution_key_id" in data:                            # lot AG8.e : répartition d'une auxiliaire
        from app.models import AnalyticKey
        value = data.get("distribution_key_id")
        key = db.session.get(AnalyticKey, value) if isinstance(value, int) and not isinstance(value, bool) else None
        if value not in (None, "") and key is None:
            raise AnalyticError("Clé de répartition introuvable.", "distribution_key_id")
        activity.distribution_key_id = key.id if key else None
    if activity.nature != "auxiliary":
        activity.distribution_key_id = None
    if "archived" in data:
        activity.archived = bool(data["archived"])
    if creating:
        db.session.add(activity)
    db.session.flush()
    return activity


def delete_activity(activity: Activity) -> None:
    db.session.delete(activity)


def set_measure(activity_id, year, data: dict) -> ActivityProduction:
    activity = db.session.get(Activity, activity_id) if isinstance(activity_id, int) else None
    if activity is None:
        raise AnalyticError("Activité introuvable.", "activity_id", 404)
    if isinstance(year, bool) or not isinstance(year, int) or not 2000 <= year <= 2100:
        raise AnalyticError("Campagne attendue (année).", "year")
    raw = data.get("measure")
    measure = None
    if raw not in (None, ""):
        try:
            measure = Decimal(str(raw).replace(",", ".").replace(" ", ""))
        except InvalidOperation:
            raise AnalyticError("Mesure numérique attendue.", "measure") from None
        if measure < 0 or measure >= Decimal("1e11"):
            raise AnalyticError("Mesure positive attendue.", "measure")
    campaign = ensure_campaign(year)
    production = ActivityProduction.query.filter_by(activity_id=activity.id, campaign_id=campaign.id).first()
    if production is None:
        production = ActivityProduction(activity_id=activity.id, campaign_id=campaign.id)
        db.session.add(production)
    production.measure = measure.quantize(Decimal("0.001")) if measure is not None else None
    production.note = _text(data.get("note"), "note", 300) if "note" in data else production.note
    db.session.flush()
    return production


def copy_measures(from_year: int, to_year: int) -> int:
    """Reprend les mesures d'une campagne sur la suivante (activités non archivées, mesure absente seulement)."""
    source = Campaign.query.filter_by(year=from_year).first()
    if source is None:
        raise AnalyticError(f"Campagne {from_year} inconnue.", "from_year", 404)
    count = 0
    for production in ActivityProduction.query.filter_by(campaign_id=source.id):
        if production.measure is None or production.activity.archived:
            continue
        target = ensure_campaign(to_year)
        existing = ActivityProduction.query.filter_by(activity_id=production.activity_id, campaign_id=target.id).first()
        if existing is not None and existing.measure is not None:
            continue
        if existing is None:
            existing = ActivityProduction(activity_id=production.activity_id, campaign_id=target.id)
            db.session.add(existing)
        existing.measure = production.measure
        count += 1
    db.session.flush()
    return count


# ------------------------------------------------------------------ activité d'une fiche (lot AG8.c)

def apply_activity(obj, data: dict, error_cls) -> None:
    """Champ `activity_id` d'une ligne d'inventaire, d'un lot, d'une avance ou d'une immobilisation."""
    if "activity_id" not in data:
        return
    value = data.get("activity_id")
    if value in (None, ""):
        obj.activity_id = None
        return
    activity = db.session.get(Activity, value) if isinstance(value, int) and not isinstance(value, bool) else None
    if activity is None:
        raise error_cls("Activité introuvable.", "activity_id")
    obj.activity_id = activity.id


def activity_fields(activity_id) -> dict:
    activity = db.session.get(Activity, activity_id) if activity_id else None
    return {"activity_id": activity_id,
            "activity": f"{activity.workshop.name} › {activity.name}" if activity is not None else None}
