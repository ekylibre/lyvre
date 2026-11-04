"""Base d'échéances de l'exploitation (lot AG9a.a, claudedocs/design_echeancier_agricole.md § 4) : fiches YAML de
`data/deadlines/`, schéma, conditions d'applicabilité sur le profil, calcul des dates.

Aucune expression n'est évaluée : une condition est un nom connu (forme, régimes, options, clôture, drapeaux du
profil des démarches), une règle de date un type connu :

- `fixed` : jours MM-JJ de chaque année, reportés au jour ouvré (`shift: none` pour ne pas reporter) ;
- `nth_working_day_after` : n-ième jour ouvré après un jour MM-JJ (2e jour ouvré après le 1er mai) ;
- `after_close` : `months` mois après la clôture C, au jour `day` (`end` : dernier jour du mois) ; `civil` remplace
  la règle pour une clôture au 31/12 ; `edi_days` : délai supplémentaire de la télédéclaration ;
- `in_fiscal_year` : jour `day` des mois `months` de l'exercice (1 = premier mois) ;
- `monthly` : jour `day` de chaque mois ;
- `once` : une date ;
- `annual_param` : dates du paramètre réglementaire de l'année (`{champ}` remplacé par le profil), sinon `fallback`,
  marqué « date à confirmer » ;
- `profile` : date du profil des démarches, décalée de `offset_months` ;
- `leases` : échéances des baux du profil, chaque année ;
- `lyvre` : occurrences calculées par le moteur de TVA (échéancier, lot AG9a.b).
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import yaml

from app.services import agri_profile, fr_calendar

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "deadlines"
DOMAINS = {"tva": "TVA", "fiscal": "Fiscal", "social": "Social (MSA)", "pac": "PAC et aides",
           "filieres": "Filières et environnement", "divers": "Divers"}
RELIABILITIES = ("V", "R", "A", "I")
RULE_TYPES = ("fixed", "nth_working_day_after", "after_close", "in_fiscal_year", "monthly", "once", "annual_param",
              "profile", "leases", "lyvre")
LYVRE_SOURCES = ("vat_returns", "vat_installments", "rfa")
TAX_CONDITIONS = ("income_tax", "ba_regime", "vat_regime")
CONDITIONS = ("legal_form", *TAX_CONDITIONS, "option", "close", "flags", "production", "company", "commercial",
              "bookkeeping")
COMMERCIAL_FORMS = {"SARL", "SAS", "SA"}
DEFAULT_REMINDERS = (15, 5)
FICHE_KEYS = {"id", "title", "domain", "organism", "summary", "applies", "events", "prepare", "lyvre_data", "penalties",
              "links", "reliability", "reminder_only"}
EVENT_KEYS = {"label", "rule", "reminders", "action", "applies", "quiet", "reliability", "payment"}


class SchemaError(Exception):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


# ------------------------------------------------------------------ chargement et schéma

def _check_month_day(text, where, problems):
    try:
        month, day = (int(p) for p in str(text).split("-"))
        date(2024, month, day)  # année bissextile : le 29/02 est accepté
    except (TypeError, ValueError):
        problems.append(f"{where} : jour MM-JJ invalide ({text!r}).")


def _check_rule(rule, where, problems, nested=False):
    if not isinstance(rule, dict) or rule.get("type") not in RULE_TYPES:
        problems.append(f"{where} : règle de date inconnue.")
        return
    kind = rule["type"]
    if rule.get("shift", "next_working_day") not in ("next_working_day", "none"):
        problems.append(f"{where} : report inconnu.")
    if kind == "fixed":
        if not rule.get("days"):
            problems.append(f"{where} : jours manquants.")
        for text in rule.get("days") or []:
            _check_month_day(text, where, problems)
    elif kind == "nth_working_day_after":
        _check_month_day(rule.get("day"), where, problems)
        if not isinstance(rule.get("n"), int) or rule["n"] < 1:
            problems.append(f"{where} : n entier attendu.")
    elif kind == "after_close":
        if not isinstance(rule.get("months"), int) or not 0 <= rule["months"] <= 24:
            problems.append(f"{where} : nombre de mois invalide.")
        if rule.get("day") != "end" and not (isinstance(rule.get("day"), int) and 1 <= rule["day"] <= 31):
            problems.append(f"{where} : jour « end » ou 1 à 31.")
        if "civil" in rule:
            _check_rule(rule["civil"], f"{where} (civil)", problems, nested=True)
    elif kind == "in_fiscal_year":
        if not rule.get("months") or any(not isinstance(m, int) or not 1 <= m <= 24 for m in rule["months"]):
            problems.append(f"{where} : mois de l'exercice invalides.")
        if not isinstance(rule.get("day"), int) or not 1 <= rule["day"] <= 31:
            problems.append(f"{where} : jour invalide.")
    elif kind == "monthly":
        if not isinstance(rule.get("day"), int) or not 1 <= rule["day"] <= 28:
            problems.append(f"{where} : jour du mois de 1 à 28.")
    elif kind == "once":
        try:
            date.fromisoformat(str(rule.get("date")))
        except ValueError:
            problems.append(f"{where} : date AAAA-MM-JJ attendue.")
    elif kind == "annual_param":
        if not str(rule.get("key") or "").startswith("agenda."):
            problems.append(f"{where} : clé de paramètre « agenda.… » attendue.")
        if nested or "fallback" not in rule:
            problems.append(f"{where} : date de repli obligatoire (et pas de paramètre imbriqué).")
        else:
            _check_rule(rule["fallback"], f"{where} (repli)", problems, nested=True)
    elif kind == "profile":
        if rule.get("field") not in agri_profile.DATES:
            problems.append(f"{where} : champ de date du profil inconnu.")
    elif kind == "lyvre":
        if rule.get("source") not in LYVRE_SOURCES:
            problems.append(f"{where} : source Lyvre inconnue.")


def _check_applies(applies, where, problems):
    if applies is None:
        return
    if not isinstance(applies, dict):
        problems.append(f"{where} : conditions attendues.")
        return
    for key, value in applies.items():
        if key not in CONDITIONS:
            problems.append(f"{where} : condition inconnue « {key} ».")
        elif key == "flags" and any(f not in agri_profile.FLAGS for f in value or []):
            problems.append(f"{where} : drapeau inconnu.")
        elif key == "production" and any(p not in agri_profile.PRODUCTIONS for p in value or []):
            problems.append(f"{where} : production inconnue.")
        elif key == "close" and value not in ("civil", "offset"):
            problems.append(f"{where} : clôture « civil » ou « offset ».")
        elif key in ("company", "commercial") and not isinstance(value, bool):
            problems.append(f"{where} : oui ou non attendu.")


def validate(fiches: list[dict]) -> list[str]:
    problems, ids = [], set()
    for fiche in fiches:
        where = fiche.get("id", "?")
        missing = {"id", "title", "domain", "organism", "summary", "events", "reliability"} - set(fiche)
        if missing:
            problems.append(f"{where} : champs manquants {sorted(missing)}.")
        if set(fiche) - FICHE_KEYS:
            problems.append(f"{where} : champs inconnus {sorted(set(fiche) - FICHE_KEYS)}.")
        if where in ids:
            problems.append(f"{where} : identifiant en double.")
        ids.add(where)
        if fiche.get("domain") not in DOMAINS:
            problems.append(f"{where} : domaine inconnu.")
        if fiche.get("reliability") not in RELIABILITIES:
            problems.append(f"{where} : fiabilité inconnue.")
        if any(not str(link).startswith("https://") for link in fiche.get("links") or []):
            problems.append(f"{where} : lien https attendu.")
        _check_applies(fiche.get("applies"), where, problems)
        for n, event in enumerate(fiche.get("events") or [], start=1):
            at = f"{where} événement {n}"
            if set(event) - EVENT_KEYS:
                problems.append(f"{at} : champs inconnus {sorted(set(event) - EVENT_KEYS)}.")
            if not event.get("label"):
                problems.append(f"{at} : libellé manquant.")
            if event.get("reliability") not in (None, *RELIABILITIES):
                problems.append(f"{at} : fiabilité inconnue.")
            if any(not isinstance(d, int) or d < 0 for d in event.get("reminders") or []):
                problems.append(f"{at} : rappels en jours positifs.")
            if event.get("payment") not in (None, True, False):
                problems.append(f"{at} : `payment` vaut true ou false.")
            _check_applies(event.get("applies"), at, problems)
            _check_rule(event.get("rule"), at, problems)
    return problems


@lru_cache(maxsize=1)
def fiches() -> tuple[dict, ...]:
    """Toutes les fiches, dans l'ordre des domaines ; SchemaError si la base est invalide."""
    loaded = []
    for domain in DOMAINS:
        path = DATA_DIR / f"{domain}.yml"
        if path.is_file():
            loaded.extend(yaml.safe_load(path.read_text(encoding="utf-8")) or [])
    problems = validate(loaded)
    if problems:
        raise SchemaError(problems)
    return tuple(loaded)


@lru_cache(maxsize=1)
def payees() -> dict[str, tuple[str, ...]]:
    """Motifs de libellé bancaire par organisme (`data/deadlines/payees.yml`), déjà normalisés."""
    raw = yaml.safe_load((DATA_DIR / "payees.yml").read_text(encoding="utf-8")) or []
    out: dict[str, tuple[str, ...]] = {}
    for entry in raw:
        patterns = tuple(normalize(p) for p in entry["patterns"])
        for organism in entry["organisms"]:
            out[organism] = out.get(organism, ()) + patterns
    return out


def normalize(text: str | None) -> str:
    """Majuscules sans accents ; ponctuation retirée entre lettres (D.G.F.I.P → DGFIP), sinon remplacée par une
    espace ; espaces réduites."""
    import re
    import unicodedata

    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().upper()
    text = re.sub(r"(?<=[A-Z])\.(?=[A-Z])", "", text)
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", text).split())


def fiche(deadline_id: str) -> dict | None:
    return next((f for f in fiches() if f["id"] == deadline_id), None)


# ------------------------------------------------------------------ contexte et applicabilité

@dataclass
class Context:
    """Ce que les conditions et les règles lisent : profil fiscal daté, options, profil des démarches, exercices."""
    legal_form: str | None = None
    bookkeeping: str = "double"
    profile: dict = field(default_factory=dict)
    tax: dict = field(default_factory=dict)          # {(kind, année): valeur}, ou une fonction (kind, jour) → valeur
    options: dict = field(default_factory=dict)      # code → [(début, fin ou None)]
    fiscal_years: list = field(default_factory=list)  # [(début, fin)], triés
    tax_lookup: object = None

    def tax_value(self, kind: str, on: date):
        if self.tax_lookup is not None:
            return self.tax_lookup(kind, on)
        return self.tax.get(kind)

    def option_active(self, code: str, on: date) -> bool:
        return any(start <= on and (end is None or on < end) for start, end in self.options.get(code, []))


def context() -> Context:
    """Contexte de l'instance courante."""
    from app.models import FiscalYear, TaxOption
    from app.services import organization, tax_profile
    from app.tenant import current_instance

    org = organization.get()
    inst = current_instance()
    options: dict = {}
    for option in TaxOption.query.all():
        options.setdefault(option.code, []).append((option.start_date, option.renounced_on))
    years = [(fy.start_date, fy.end_date) for fy in FiscalYear.query.order_by(FiscalYear.start_date)]
    return Context(legal_form=org.legal_form_code, bookkeeping=inst.bookkeeping if inst is not None else "double",
                   profile=agri_profile.get(), options=options, fiscal_years=years,
                   tax_lookup=lambda kind, on: tax_profile.current_value(kind, on))


def applies(conditions: dict | None, ctx: Context, on: date) -> bool | None:
    """True, False, ou None quand une donnée du profil manque pour trancher."""
    if not conditions:
        return True
    unknown = False
    for key, value in conditions.items():
        if key == "legal_form":
            result = None if ctx.legal_form is None else ctx.legal_form in value
        elif key in TAX_CONDITIONS:
            current = ctx.tax_value(key, on)
            result = None if current is None else current in value
        elif key == "option":
            result = ctx.option_active(value, on)
        elif key == "close":
            close = _close_on(ctx, on)
            result = ((close.month, close.day) == (12, 31)) == (value == "civil")
        elif key == "flags":
            values = [agri_profile.flag(ctx.profile, name) for name in value]
            result = None if None in values and False not in values else all(v is True for v in values)
        elif key == "production":
            productions = ctx.profile.get("productions")
            result = None if productions is None else bool(set(productions) & set(value))
        elif key == "company":
            from app.services.tax_profile import COMPANY_FORMS
            result = None if ctx.legal_form is None else (ctx.legal_form in COMPANY_FORMS) == value
        elif key == "commercial":
            result = None if ctx.legal_form is None else (ctx.legal_form in COMMERCIAL_FORMS) == value
        elif key == "bookkeeping":
            result = ctx.bookkeeping in value
        else:  # pragma: no cover - refusé par le schéma
            result = False
        if result is False:
            return False
        if result is None:
            unknown = True
    return None if unknown else True


# ------------------------------------------------------------------ dates

@dataclass
class Occurrence:
    date: date
    period: str
    to_confirm: bool = False
    note: str | None = None
    edi_date: date | None = None


def _shift(day: date, rule: dict) -> date:
    return day if rule.get("shift", "next_working_day") == "none" else fr_calendar.next_working_day(day)


def _month_day(text: str, year: int) -> date:
    month, day = (int(p) for p in text.split("-"))
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def _add_months(day: date, months: int) -> tuple[int, int]:
    index = day.month - 1 + months
    return day.year + index // 12, index % 12 + 1


def _day_in(year: int, month: int, day) -> date:
    last = calendar.monthrange(year, month)[1]
    return date(year, month, last if day == "end" else min(day, last))


def fiscal_years(ctx: Context, until: date) -> list[tuple[date, date]]:
    """Exercices de l'instance, prolongés d'année en année jusqu'à `until` (année civile sans exercice)."""
    years = list(ctx.fiscal_years) or [(date(until.year - 2, 1, 1), date(until.year - 2, 12, 31))]
    while years[-1][1] < until:
        start, end = years[-1]
        next_start = end + timedelta(days=1)
        year, month = _add_months(next_start, 12)
        years.append((next_start, date(year, month, 1) - timedelta(days=1)))
    return years


def _close_on(ctx: Context, on: date) -> date:
    for start, end in fiscal_years(ctx, on):
        if start <= on <= end:
            return end
    return date(on.year, 12, 31)


def _year_dates(rule: dict, year: int, ctx: Context) -> list[Occurrence]:
    """Dates d'une règle annuelle pour l'année `year` (fixed, nth_working_day_after, annual_param, leases)."""
    kind = rule["type"]
    if kind == "fixed":
        return [Occurrence(_shift(_month_day(text, year), rule), str(year)) for text in rule["days"]]
    if kind == "nth_working_day_after":
        return [Occurrence(fr_calendar.nth_working_day_after(_month_day(rule["day"], year), rule["n"]), str(year))]
    if kind == "annual_param":
        from app.services import reg_params
        key = rule["key"]
        param = None
        if "{" in key:
            field_name = key[key.index("{") + 1:key.index("}")]
            value = ctx.profile.get(field_name)
            key = key.replace("{" + field_name + "}", value) if value else None
        if key:
            param = reg_params.get(key, date(year, 7, 1), default=None)
        if param is not None and param.valid_from and param.valid_from.year == year and param.value:
            values = param.value if isinstance(param.value, list) else [param.value]
            return [Occurrence(date.fromisoformat(v), str(year), to_confirm=param.reliability == "I") for v in values]
        return [Occurrence(o.date, o.period, True, "Date à confirmer", o.edi_date)
                for o in _year_dates(rule["fallback"], year, ctx)]
    if kind == "leases":
        return [Occurrence(_month_day(lease["due"], year), str(year), note=lease["label"])
                for lease in ctx.profile.get("leases") or []]
    return []


def dates(rule: dict, start: date, end: date, ctx: Context) -> list[Occurrence]:
    """Occurrences d'une règle entre `start` et `end` (inclus), triées."""
    kind = rule["type"]
    out: list[Occurrence] = []
    if kind in ("fixed", "nth_working_day_after", "annual_param", "leases"):
        for year in range(start.year - 1, end.year + 2):
            out.extend(_year_dates(rule, year, ctx))
    elif kind == "monthly":
        year, month = start.year, start.month
        while date(year, month, 1) <= end:
            out.append(Occurrence(_shift(date(year, month, rule["day"]), rule), f"{year}-{month:02d}"))
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    elif kind == "once":
        out.append(Occurrence(date.fromisoformat(str(rule["date"])), str(rule["date"])[:4]))
    elif kind == "after_close":
        for fy_start, close in fiscal_years(ctx, end):
            label = str(close.year) if fy_start.year == close.year else f"{fy_start.year}-{close.year}"
            if "civil" in rule and (close.month, close.day) == (12, 31):
                occurrences = _year_dates(rule["civil"], close.year + 1, ctx)
            else:
                year, month = _add_months(close, rule["months"])
                occurrences = [Occurrence(_shift(_day_in(year, month, rule["day"]), rule), label)]
            for occ in occurrences:
                occ.period = f"exercice {label}"
                if rule.get("edi_days"):
                    occ.edi_date = occ.date + timedelta(days=rule["edi_days"])
                out.append(occ)
    elif kind == "in_fiscal_year":
        for fy_start, close in fiscal_years(ctx, end):
            label = str(close.year) if fy_start.year == close.year else f"{fy_start.year}-{close.year}"
            for month_index in rule["months"]:
                year, month = _add_months(fy_start, month_index - 1)
                day = _shift(_day_in(year, month, rule["day"]), rule)
                if day <= close + timedelta(days=31):
                    out.append(Occurrence(day, f"exercice {label}"))
    elif kind == "profile":
        text = ctx.profile.get(rule["field"])
        if text:
            base = date.fromisoformat(text)
            year, month = _add_months(base, rule.get("offset_months") or 0)
            out.append(Occurrence(_day_in(year, month, base.day), str(year)))
    return sorted((o for o in out if start <= o.date <= end), key=lambda o: o.date)
