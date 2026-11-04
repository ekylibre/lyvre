"""Profil fiscal de la structure (lot AG1.a, claudedocs/design_compta_agricole.md § 3) : forme juridique
codée, régimes datés (`tax_profiles`), options datées (`tax_options`) et contrôles de cohérence (AG0.5).

Les contrôles bloquants renvoient ``TaxProfileError`` (422, rattachée à un champ) ; les autres sont des
alertes (``warnings()``), affichées sans refus : les associés, par exemple, se saisissent après.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.extensions import db
from app.models import TaxOption, TaxProfile
from app.services import reg_params

LEGAL_FORMS = {
    "EI": "Entreprise individuelle",
    "EARL": "EARL",
    "EARL_U": "EARL unipersonnelle (associé unique exploitant)",
    "GAEC": "GAEC",
    "SCEA": "SCEA",
    "GFA": "Groupement foncier agricole",
    "SARL": "SARL",
    "SAS": "SAS / SASU",
    "SA": "SA",
    "SCI": "SCI",
    "ASSO": "Association",
}
# Formes sociétaires (module Associés proposé, micro-BA soumis à l'art. 69 D).
COMPANY_FORMS = {"EARL", "EARL_U", "GAEC", "SCEA", "GFA", "SARL", "SAS", "SA", "SCI"}
# Nombre d'associés admis (CRPM L.323-1, L.324-1) : (minimum, maximum).
ASSOCIATE_LIMITS = {"GAEC": (2, 10), "EARL": (1, 10), "EARL_U": (1, 1)}

# Catégorie juridique INSEE (niveau III, data/insee/categories_juridiques.json) → forme : code exact,
# sinon préfixe à deux chiffres. L'EARL unipersonnelle ne se distingue pas dans Sirene.
INSEE_EXACT = {"1000": "EI", "6533": "GAEC", "6534": "GFA", "6597": "SCEA", "6598": "EARL", "6540": "SCI"}
INSEE_PREFIX = {"54": "SARL", "55": "SA", "56": "SA", "57": "SAS", "92": "ASSO"}

KINDS = {
    "income_tax": {"label": "Impôt sur les bénéfices", "values": {"IR": "Impôt sur le revenu", "IS": "Impôt sur les sociétés"}},
    "ba_regime": {"label": "Régime des bénéfices agricoles", "values": {
        "micro": "Micro-BA", "simplified": "Réel simplifié", "normal": "Réel normal"}},
    "vat_regime": {"label": "Régime de TVA", "values": {
        "none": "Non assujetti", "rfa": "Remboursement forfaitaire agricole", "rsa_installments": "RSA : acomptes et CA12A",
        "rsa_quarterly": "RSA : CA3 trimestrielle", "rsa_monthly": "RSA : CA3 mensuelle", "normal": "Réel normal (CA3)"}},
}
ORIGINS = {"law": "De plein droit", "option": "Sur option"}
OPTIONS = {
    "ba_simplified_option": "Option pour le réel simplifié (BA)",
    "ba_normal_option": "Option pour le réel normal (BA)",
    "is_option": "Option pour l'impôt sur les sociétés",
    "averaging_75_0_b": "Moyenne triennale (art. 75-0 B)",
    "stock_freeze_72_b_bis": "Blocage des stocks à rotation lente (art. 72 B bis)",
    "flat_stock_method": "Méthode forfaitaire des stocks (art. 74 b)",
    "rsa_option": "Option pour le régime simplifié agricole (TVA)",
    "vat_quarterly": "Option CA3 trimestrielle (RSA)",
    "vat_monthly": "Option CA3 mensuelle (RSA)",
}


class TaxProfileError(Exception):
    def __init__(self, message, field=None, status=422):
        super().__init__(message)
        self.message, self.field, self.status = message, field, status


# ------------------------------------------------------------------ forme juridique

def legal_form_from_insee(category: str | None) -> str | None:
    category = (category or "").strip()
    if not category:
        return None
    return INSEE_EXACT.get(category) or INSEE_PREFIX.get(category[:2])


def is_company(code: str | None) -> bool:
    return code in COMPANY_FORMS


# ------------------------------------------------------------------ régimes datés

def _parse_date(value, field, required=True) -> date | None:
    text = str(value or "").strip()
    if not text:
        if required:
            raise TaxProfileError("Date obligatoire (AAAA-MM-JJ).", field)
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise TaxProfileError("Date attendue (AAAA-MM-JJ).", field) from None


def periods(kind: str | None = None) -> list[TaxProfile]:
    query = TaxProfile.query
    if kind:
        query = query.filter_by(kind=kind)
    return query.order_by(TaxProfile.kind, TaxProfile.start_date).all()


def current(kind: str, on: date | None = None) -> TaxProfile | None:
    on = on or date.today()
    return (TaxProfile.query.filter(TaxProfile.kind == kind, TaxProfile.start_date <= on,
                                    (TaxProfile.end_date.is_(None)) | (TaxProfile.end_date >= on))
            .order_by(TaxProfile.start_date.desc()).first())


def current_value(kind: str, on: date | None = None) -> str | None:
    period = current(kind, on)
    return period.value if period else None


def _overlaps(kind, start, end, exclude_id=None) -> TaxProfile | None:
    for other in periods(kind):
        if other.id == exclude_id:
            continue
        other_end = other.end_date or date.max
        if start <= other_end and other.start_date <= (end or date.max):
            return other
    return None


def _check_regime(kind: str, value: str, start: date, exclude_id=None) -> None:
    """Contrôles bloquants (AG0.5) d'une période de régime."""
    from app.services import organization

    org = organization.get()
    form = org.legal_form_code
    if kind == "ba_regime":
        if current_value("income_tax", start) == "IS":
            raise TaxProfileError("Une structure à l'IS n'a pas de régime des bénéfices agricoles.", "value")
        if value == "micro" and is_company(form) and form != "EARL_U":
            cutoff = reg_params.value("ba.micro.company_cutoff_date", start, default=None)
            if org.created_on is None:
                raise TaxProfileError("Micro-BA d'une société : renseignez sa date de création "
                                      "(onglet Fiscalité), le micro-BA est interdit aux sociétés créées depuis "
                                      "le 01/01/1997, sauf l'EARL unipersonnelle (CGI art. 69 D).", "value")
            if cutoff and org.created_on >= date.fromisoformat(cutoff):
                raise TaxProfileError("Micro-BA interdit : société créée depuis le 01/01/1997 (CGI art. 69 D), "
                                      "sauf EARL dont l'associé unique dirige l'exploitation.", "value")
    if kind == "income_tax" and value == "IS":
        ba = current("ba_regime", start)
        if ba is not None and ba.id != exclude_id:
            raise TaxProfileError("Terminez d'abord la période de régime BA : une structure à l'IS n'en a pas.",
                                  "value")


def add_period(data: dict) -> TaxProfile:
    kind = str(data.get("kind") or "")
    if kind not in KINDS:
        raise TaxProfileError("Type de régime inconnu.", "kind")
    value = str(data.get("value") or "")
    if value not in KINDS[kind]["values"]:
        raise TaxProfileError("Valeur de régime inconnue.", "value")
    origin = str(data.get("origin") or "law")
    if origin not in ORIGINS:
        raise TaxProfileError("Origine : de plein droit ou sur option.", "origin")
    start = _parse_date(data.get("start_date"), "start_date")
    end = _parse_date(data.get("end_date"), "end_date", required=False)
    if end and end < start:
        raise TaxProfileError("La fin précède le début.", "end_date")
    # Nouvelle période après une période ouverte : celle-ci se termine la veille (sauf close_previous=false).
    previous = current(kind, start)
    closing = (previous is not None and previous.start_date < start and previous.end_date is None
               and bool(data.get("close_previous", True)))
    other = _overlaps(kind, start, end, exclude_id=previous.id if closing else None)
    if other is not None:
        raise TaxProfileError(f"Chevauchement avec la période « {label(other)} » commencée le "
                              f"{other.start_date.strftime('%d/%m/%Y')}.", "start_date")
    _check_regime(kind, value, start, exclude_id=previous.id if closing else None)
    if closing:
        previous.end_date = start - timedelta(days=1)
    period = TaxProfile(kind=kind, value=value, start_date=start, end_date=end, origin=origin,
                        note=(str(data.get("note") or "").strip()[:300] or None))
    db.session.add(period)
    db.session.commit()
    return period


def update_period(period: TaxProfile, data: dict) -> TaxProfile:
    start = _parse_date(data.get("start_date", period.start_date.isoformat()), "start_date")
    end_raw = data.get("end_date", period.end_date.isoformat() if period.end_date else None)
    end = _parse_date(end_raw, "end_date", required=False)
    value = str(data.get("value", period.value))
    if value not in KINDS[period.kind]["values"]:
        raise TaxProfileError("Valeur de régime inconnue.", "value")
    if end and end < start:
        raise TaxProfileError("La fin précède le début.", "end_date")
    other = _overlaps(period.kind, start, end, exclude_id=period.id)
    if other is not None:
        raise TaxProfileError(f"Chevauchement avec la période « {label(other)} » commencée le "
                              f"{other.start_date.strftime('%d/%m/%Y')}.", "start_date")
    _check_regime(period.kind, value, start, exclude_id=period.id)
    period.start_date, period.end_date, period.value = start, end, value
    if "origin" in data:
        if data["origin"] not in ORIGINS:
            raise TaxProfileError("Origine : de plein droit ou sur option.", "origin")
        period.origin = data["origin"]
    if "note" in data:
        period.note = str(data.get("note") or "").strip()[:300] or None
    db.session.commit()
    return period


def delete_period(period: TaxProfile) -> None:
    db.session.delete(period)
    db.session.commit()


def label(period: TaxProfile) -> str:
    return KINDS[period.kind]["values"].get(period.value, period.value)


def period_payload(period: TaxProfile) -> dict:
    return {"id": period.id, "kind": period.kind, "kind_label": KINDS[period.kind]["label"], "value": period.value,
            "value_label": label(period), "start_date": period.start_date.isoformat(),
            "end_date": period.end_date.isoformat() if period.end_date else None, "origin": period.origin,
            "origin_label": ORIGINS.get(period.origin, period.origin), "note": period.note}


# ------------------------------------------------------------------ options datées

def period_bounds(option: TaxOption, on: date | None = None) -> tuple[int, int] | None:
    """(première année, dernière année) de la période en cours de l'option, ou None sans durée.
    Une option reconduite tacitement repart pour la même durée à la fin de chaque période."""
    if not option.duration_years:
        return None
    on = on or date.today()
    first = option.start_date.year
    if option.tacit_renewal and on.year > first:
        first += ((on.year - first) // option.duration_years) * option.duration_years
    return first, first + option.duration_years - 1


def renounce_by(option: TaxOption, on: date | None = None) -> dict | None:
    """Date limite de renonciation de la période en cours (paramètre ``option.<code>.renounce``) avec sa
    fiabilité ; None si l'option est déjà dénoncée ou si la règle ne donne pas de date."""
    if option.renounced_on is not None:
        return None
    on = on or date.today()
    param = reg_params.get(f"option.{option.code}.renounce", option.start_date, default=None)
    rule = param.value if param else None
    if not rule:
        return {"date": None, "reliability": param.reliability if param else "I",
                "note": param.note if param else "Règle de renonciation non renseignée."}
    month, day = (int(part) for part in rule["month_day"].split("-"))
    if rule.get("year") == "fifth":
        year = option.start_date.year + 5
    else:
        bounds = period_bounds(option, on)
        if bounds is None:
            return {"date": None, "reliability": param.reliability, "note": param.note}
        year = bounds[1] + (1 if rule.get("year") == "after_end" else 0)
    return {"date": date(year, month, day).isoformat(), "reliability": param.reliability, "note": param.note}


def _option_values(data: dict, option: TaxOption | None = None) -> dict:
    code = str(data.get("code", option.code if option else "") or "")
    if code not in OPTIONS:
        raise TaxProfileError("Option inconnue.", "code")
    start = _parse_date(data.get("start_date", option.start_date.isoformat() if option else None), "start_date")
    if "duration_years" in data:
        text = str(data.get("duration_years") or "").strip()
        if text and not text.isdigit():
            raise TaxProfileError("Durée en années (nombre entier).", "duration_years")
        duration = int(text) if text else None
    elif option is not None:
        duration = option.duration_years
    else:  # durée par défaut : celle des paramètres réglementaires
        duration = reg_params.value(f"option.{code}.duration_years", start, default=None)
    renounced = _parse_date(data.get("renounced_on", option.renounced_on.isoformat()
                                     if option and option.renounced_on else None), "renounced_on", required=False)
    if renounced and renounced < start:
        raise TaxProfileError("La renonciation précède l'option.", "renounced_on")
    tacit = data.get("tacit_renewal", option.tacit_renewal if option else duration is not None)
    return {"code": code, "start_date": start, "duration_years": duration, "tacit_renewal": bool(tacit),
            "renounced_on": renounced,
            "note": str(data.get("note", option.note if option else "") or "").strip()[:300] or None}


def add_option(data: dict) -> TaxOption:
    option = TaxOption(**_option_values(data))
    db.session.add(option)
    db.session.commit()
    return option


def update_option(option: TaxOption, data: dict) -> TaxOption:
    for key, value in _option_values(data, option).items():
        setattr(option, key, value)
    db.session.commit()
    return option


def delete_option(option: TaxOption) -> None:
    db.session.delete(option)
    db.session.commit()


def option_payload(option: TaxOption, on: date | None = None) -> dict:
    bounds = period_bounds(option, on)
    return {"id": option.id, "code": option.code, "label": OPTIONS.get(option.code, option.code),
            "start_date": option.start_date.isoformat(), "duration_years": option.duration_years,
            "tacit_renewal": option.tacit_renewal,
            "renounced_on": option.renounced_on.isoformat() if option.renounced_on else None,
            "current_period": {"first_year": bounds[0], "last_year": bounds[1]} if bounds else None,
            "renounce_by": renounce_by(option, on), "note": option.note}


# ------------------------------------------------------------------ alertes (non bloquantes)

# Formes qui relèvent des bénéfices agricoles à l'IR (régime BA attendu).
BA_FORMS = {"EI", "EARL", "EARL_U", "GAEC", "SCEA", "GFA"}


def warnings(on: date | None = None) -> list[str]:
    from app.services import associates, organization

    on = on or date.today()
    form = organization.get().legal_form_code
    items = []
    if form in ASSOCIATE_LIMITS and associates.enabled():
        low, high = ASSOCIATE_LIMITS[form]
        count = sum(1 for a in associates.listing(on)["items"] if not a["is_out"])
        if count and not low <= count <= high:
            items.append(f"{LEGAL_FORMS[form]} : {low} à {high} associé(s) attendu(s), {count} enregistré(s).")
    income_tax = current_value("income_tax", on)
    if form and form != "ASSO" and income_tax is None:
        items.append("Impôt sur les bénéfices (IR ou IS) non renseigné pour la période en cours.")
    if form in BA_FORMS and income_tax == "IR" and current_value("ba_regime", on) is None:
        items.append("Régime des bénéfices agricoles non renseigné pour la période en cours.")
    return items


def payload(on: date | None = None) -> dict:
    from app.services import organization

    org = organization.get()
    return {"legal_form_code": org.legal_form_code, "created_on": org.created_on.isoformat() if org.created_on else None,
            "periods": [period_payload(p) for p in periods()],
            "options": [option_payload(o, on) for o in TaxOption.query.order_by(TaxOption.start_date).all()],
            "current": {kind: current_value(kind, on) for kind in KINDS}, "warnings": warnings(on)}


def meta() -> dict:
    return {"legal_forms": [{"value": k, "label": v} for k, v in LEGAL_FORMS.items()],
            "kinds": [{"value": k, "label": v["label"],
                       "values": [{"value": a, "label": b} for a, b in v["values"].items()]} for k, v in KINDS.items()],
            "origins": [{"value": k, "label": v} for k, v in ORIGINS.items()],
            "options": [{"value": k, "label": v} for k, v in OPTIONS.items()]}
