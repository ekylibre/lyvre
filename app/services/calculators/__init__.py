"""Calculettes (lot AG12, claudedocs/design_calculettes_agricoles.md, AGD29) : registre, entrées typées, gabarit.

Chaque calculette est un module de ce paquet qui déclare :
- `SPEC` (`Spec`) : code, numéro, titre, catégorie, types de structure (`charts`), entrées, exemple, méthode et limites,
  paramètres réglementaires utilisés, sources ;
- `prefill(ctx)` (facultatif) : valeurs lues dans l'instance, chacune avec son origine ; `ctx.choice` est le choix
  de préremplissage (un bien, une année) quand la calculette en propose (`prefill_options(ctx)`) ;
- `compute(values, on)` : `Result` (chiffres principaux, détail, tableau, avertissements, actions).

Règles communes (C1 à C7) :
- les **paramètres** viennent uniquement de `data/regulatory/` (`reg_params`), à la date de calcul (`on_date`) ;
  un paramètre absent bloque la calculette (`CalculatorError`, 409) ;
- **aucune écriture** : une action n'est qu'un lien vers l'écran qui agit ;
- le résultat se **copie en texte** (`as_text`), méthode et sources comprises.
"""
from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

CATEGORIES = {"fiscal": "Fiscal", "social": "Social", "vat": "TVA", "management": "Gestion", "economics": "Économie",
              "measures": "Mesures et conversions", "equipment": "Chantiers et matériel", "sowing": "Semis et plantation",
              "fertilization": "Fertilisation", "spraying": "Pulvérisation", "irrigation": "Irrigation et eau",
              "harvest": "Récolte et stockage", "crops": "Cultures", "livestock": "Élevage", "energy": "Énergie",
              "regulatory": "Réglementaire"}
CHART_LABELS = {"agri": "Agricole", "asso": "Association", "societe": "Société", "sci": "SCI"}
KINDS = ("money", "number", "integer", "percent", "date", "choice", "text")


class CalculatorError(ValueError):
    def __init__(self, message, field=None, status=422):
        super().__init__(message)
        self.message, self.field, self.status = message, field, status


@dataclass
class Input:
    key: str
    label: str
    kind: str = "number"
    unit: str | None = None
    required: bool = True
    choices: list[tuple[str, str]] | None = None
    help: str | None = None
    default: object = None

    def payload(self) -> dict:
        return {"key": self.key, "label": self.label, "kind": self.kind, "unit": self.unit, "required": self.required,
                "choices": [{"value": v, "label": l} for v, l in self.choices] if self.choices else None,
                "help": self.help, "default": self.default}


@dataclass
class Spec:
    code: str
    number: str
    title: str
    category: str
    summary: str
    inputs: list[Input]
    example: dict
    method: str
    charts: tuple[str, ...] = ("agri",)
    params: tuple[str, ...] = ()
    sources: tuple[tuple[str, str], ...] = ()          # (libellé, URL)
    prefill_label: str | None = None                    # « Bien », « Année » : choix du préremplissage


@dataclass
class Result:
    headline: list[tuple[str, str]]                     # (libellé, valeur formatée)
    details: list[tuple[str, str]] = field(default_factory=list)
    table: dict | None = None                           # {columns: [...], rows: [[...]]}
    warnings: list[str] = field(default_factory=list)
    actions: list[tuple[str, str]] = field(default_factory=list)   # (libellé, route de l'application)


class Tool:
    """Calculette déclarée dans une liste (`TOOLS` d'un module) plutôt que par un module entier : mêmes attributs."""

    def __init__(self, spec: "Spec", compute, on_date=None):
        self.SPEC, self.compute = spec, compute
        if on_date is not None:
            self.on_date = on_date


@dataclass
class Context:
    chart: str | None
    choice: str | None = None


# ------------------------------------------------------------------ registre

_REGISTRY: dict[str, object] = {}


def registry() -> dict[str, object]:
    if not _REGISTRY:
        for info in pkgutil.iter_modules(__path__):
            module = importlib.import_module(f"{__name__}.{info.name}")
            spec = getattr(module, "SPEC", None)
            if isinstance(spec, Spec):
                _REGISTRY[spec.code] = module
            for tool in getattr(module, "TOOLS", ()):
                _REGISTRY[tool.SPEC.code] = tool
    return _REGISTRY


def get(code: str):
    module = registry().get(code)
    if module is None:
        raise CalculatorError("Calculette inconnue.", status=404)
    return module


# ------------------------------------------------------------------ formats

def euros(cents: int | None) -> str:
    if cents is None:
        return "—"
    sign = "-" if cents < 0 else ""
    whole, rest = divmod(abs(cents), 100)
    return f"{sign}{whole:,}".replace(",", " ") + f",{rest:02d} €"


def number(value, digits: int = 2) -> str:
    text = f"{Decimal(value):,.{digits}f}".replace(",", " ").replace(".", ",")
    return text


def positive(values: dict, key: str, label: str, allow_zero: bool = False):
    """Valeur strictement positive (ou nulle si `allow_zero`), sinon erreur sur le champ."""
    value = values.get(key)
    if value is None or value < 0 or (value == 0 and not allow_zero):
        raise CalculatorError(f"{label} : valeur {'positive ou nulle' if allow_zero else 'positive'} attendue.", key)
    return value


def pct(bp: int) -> str:
    return f"{Decimal(bp) / 100:g}".replace(".", ",") + " %"


# ------------------------------------------------------------------ entrées

def _decimal(raw, label: str, key: str) -> Decimal:
    text = str(raw).replace(" ", "").replace("\xa0", "").replace(" ", "").replace("€", "").replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        raise CalculatorError(f"{label} : nombre attendu.", key) from None


def parse(spec: Spec, raw: dict) -> dict:
    """Valeurs typées : montant en centimes, nombre en Decimal, entier, pourcentage en Decimal, date, choix, texte."""
    if not isinstance(raw, dict):
        raise CalculatorError("Valeurs attendues.")
    values = {}
    for item in spec.inputs:
        value = raw.get(item.key)
        if value in (None, ""):
            if item.required:
                raise CalculatorError(f"{item.label} : valeur obligatoire.", item.key)
            values[item.key] = None
            continue
        if item.kind == "money":
            values[item.key] = int((_decimal(value, item.label, item.key) * 100).quantize(Decimal(1)))
        elif item.kind in ("number", "percent"):
            values[item.key] = _decimal(value, item.label, item.key)
        elif item.kind == "integer":
            number_ = _decimal(value, item.label, item.key)
            if number_ != number_.to_integral_value():
                raise CalculatorError(f"{item.label} : nombre entier attendu.", item.key)
            values[item.key] = int(number_)
        elif item.kind == "date":
            try:
                values[item.key] = date.fromisoformat(str(value)[:10])
            except ValueError:
                raise CalculatorError(f"{item.label} : date attendue (AAAA-MM-JJ).", item.key) from None
        elif item.kind == "choice":
            if str(value) not in {v for v, _ in item.choices or ()}:
                raise CalculatorError(f"{item.label} : choix inconnu.", item.key)
            values[item.key] = str(value)
        else:
            values[item.key] = str(value).strip()[:300]
    return values


# ------------------------------------------------------------------ paramètres

def params(spec: Spec, on: date) -> list[dict]:
    from app.services import reg_params
    out = []
    for key in spec.params:
        param = reg_params.get(key, on, default=None)
        out.append({"key": key, "value": param.value if param else None, "missing": param is None,
                    "valid_from": param.valid_from.isoformat() if param else None,
                    "valid_to": param.valid_to.isoformat() if param and param.valid_to else None,
                    "source": param.source if param else None, "source_label": param.source_label if param else None,
                    "verified_on": param.verified_on.isoformat() if param and param.verified_on else None,
                    "reliability": param.reliability if param else None})
    return out


def require_params(spec: Spec, on: date) -> list[dict]:
    found = params(spec, on)
    missing = [p["key"] for p in found if p["missing"]]
    if missing:
        raise CalculatorError(f"Paramètre réglementaire absent au {on:%d/%m/%Y} : {', '.join(missing)} "
                              "(Administration › Paramètres réglementaires).", status=409)
    return found


# ------------------------------------------------------------------ calcul et texte

def spec_payload(module, chart: str | None) -> dict:
    spec: Spec = module.SPEC
    return {"code": spec.code, "number": spec.number, "title": spec.title, "category": spec.category,
            "category_label": CATEGORIES[spec.category], "summary": spec.summary, "charts": list(spec.charts),
            "prefillable": hasattr(module, "prefill") and (chart in spec.charts),
            "inputs": [i.payload() for i in spec.inputs], "example": spec.example, "method": spec.method,
            "sources": [{"label": l, "url": u} for l, u in spec.sources], "prefill_label": spec.prefill_label}


def run(module, raw: dict, origins: dict | None = None) -> dict:
    spec: Spec = module.SPEC
    values = parse(spec, raw)
    on = module.on_date(values) if hasattr(module, "on_date") else date.today()
    used = require_params(spec, on)
    result: Result = module.compute(values, on)
    payload = {"headline": [{"label": l, "value": v} for l, v in result.headline],
               "details": [{"label": l, "value": v} for l, v in result.details], "table": result.table,
               "warnings": result.warnings, "actions": [{"label": l, "route": r} for l, r in result.actions],
               "params": used, "on": on.isoformat()}
    payload["text"] = as_text(spec, raw, origins or {}, payload)
    return payload


def as_text(spec: Spec, raw: dict, origins: dict, payload: dict) -> str:
    """Résultat copiable : chiffres, détail, entrées et leur origine, méthode, paramètres et sources (C4)."""
    lines = [f"{spec.title} — calcul du {date.today():%d/%m/%Y} (Lyvre)", ""]
    lines += [f"{h['label']} : {h['value']}" for h in payload["headline"]]
    if payload["details"]:
        lines += ["", "Détail :"] + [f"- {d['label']} : {d['value']}" for d in payload["details"]]
    if payload["table"]:
        lines += ["", " | ".join(payload["table"]["columns"])] + [" | ".join(map(str, r)) for r in payload["table"]["rows"]]
    lines += ["", "Entrées :"]
    for item in spec.inputs:
        value = raw.get(item.key)
        if value in (None, ""):
            continue
        shown = dict(item.choices or ()).get(str(value), value) if item.kind == "choice" else value
        origin = origins.get(item.key)
        lines.append(f"- {item.label} : {shown}{' ' + item.unit if item.unit else ''}" + (f" ({origin})" if origin else ""))
    if payload["warnings"]:
        lines += ["", "Avertissements :"] + [f"- {w}" for w in payload["warnings"]]
    lines += ["", "Méthode et limites :", spec.method]
    if payload["params"]:
        lines += ["", "Paramètres réglementaires :"]
        for p in payload["params"]:
            lines.append(f"- {p['key']} = {p['value']} (depuis le {p['valid_from']}, {p['source_label'] or ''} "
                         f"{p['source'] or ''}, fiabilité {p['reliability']})".replace("  ", " "))
    if spec.sources:
        lines += ["", "Sources :"] + [f"- {l} : {u}" for l, u in spec.sources]
    return "\n".join(lines)
