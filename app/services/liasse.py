"""Aide à la liasse BA 2139 / 2143 (lot AG6.f, claudedocs/design_fiscalite_ba.md § 8, AGD23 Q-F6).

- **Correspondance datée** cases → comptes dans `data/liasse/<formulaire>_<millésime>.json`, cases lues sur les
  formulaires officiels fournis (hors git), correspondance proposée par Lyvre d'après le plan agricole et **à valider**
  par l'expert-comptable (fiabilité I).
- **Formulaire** selon le régime BA à la clôture : réel simplifié → 2139, réel normal → 2143 ; rien au micro-BA ni à
  l'IS (liasse société). Millésime : le plus récent qui n'est pas postérieur à l'année de clôture.
- **Règles d'une case** : soldes de comptes (`accounts` + `mode`, comme les états de Lyvre), totaux de cases
  (`sum` / `minus`), éléments du résultat fiscal (`tax`, depuis le tableau de passage), ou saisie (case laissée vide).
- **Pas d'EDI-TDFC** : un état case → montant à recopier, à l'écran, en XLSX et en PDF.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.models import FiscalYear
from app.services import reports

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "liasse"
FORMS = {"simplified": "2139", "normal": "2143"}
MOVEMENT_MODES = {"debit_movements": "debit", "credit_movements": "credit"}


class LiasseError(Exception):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.message, self.status = message, status


def available(form: str) -> list[int]:
    years = []
    for path in DATA_DIR.glob(f"{form}_*.json"):
        match = re.fullmatch(rf"{form}_(\d{{4}})\.json", path.name)
        if match:
            years.append(int(match.group(1)))
    return sorted(years)


def load(form: str, year: int) -> tuple[dict, list[str]]:
    years = available(form)
    if not years:
        raise LiasseError(f"Correspondance de la liasse {form} absente.", 404)
    chosen = max([y for y in years if y <= year], default=years[0])
    warnings = []
    if chosen != year:
        warnings.append(f"Millésime {chosen} utilisé pour un exercice clos en {year} : cases à vérifier sur le formulaire de l'année.")
    with open(DATA_DIR / f"{form}_{chosen}.json", encoding="utf-8") as fh:
        return json.load(fh), warnings


def form_for(fy: FiscalYear) -> tuple[str | None, str | None]:
    from app.services import tax_profile
    if (tax_profile.current_value("income_tax", fy.end_date) or "").upper() == "IS":
        return None, "Société à l'IS : liasse 2033 ou 2050 du référentiel société."
    regime = tax_profile.current_value("ba_regime", fy.end_date)
    if regime == "micro":
        return None, "Micro-BA : pas de liasse, recettes à déclarer sur la 2042 C PRO."
    if regime not in FORMS:
        return "2139", "Régime BA non renseigné (Structure › Fiscalité) : liasse du réel simplifié (2139) présentée."
    return FORMS[regime], None


# ------------------------------------------------------------------ valeurs

def _tax_values(fy: FiscalYear) -> dict:
    from app.services import tax_result
    data = tax_result.view(fy)
    accounting = data["accounting_result_cents"]
    reintegrations = deductions = ja = dep = 0
    for line in data["lines"]:
        amount, source = line["amount_cents"], line.get("source")
        if source == "young_farmer":
            ja -= amount
        elif source == "dep" and amount < 0:
            dep -= amount
        elif amount > 0:
            reintegrations += amount
        else:
            deductions -= amount
    before = accounting + reintegrations - deductions
    final = data["fiscal_result_cents"]
    return {"accounting_profit": max(accounting, 0), "accounting_loss": max(-accounting, 0),
            "reintegrations": reintegrations, "deductions": deductions,
            "fiscal_profit_before_ja": max(before, 0), "fiscal_loss_before_ja": max(-before, 0),
            "ja": ja, "dep": dep, "fiscal_profit": max(final, 0), "fiscal_loss": max(-final, 0)}


def _account_value(fy: FiscalYear, row: dict) -> int:
    mode = row.get("mode", "debit")
    if mode in MOVEMENT_MODES:
        return reports._sum_accounts(row["accounts"], fy.id, MOVEMENT_MODES[mode], row.get("exclude"))  # noqa: SLF001
    return reports._amount(mode, row["accounts"], fy.id, row.get("exclude"))  # noqa: SLF001


def compute(fy: FiscalYear) -> dict:
    form, notice = form_for(fy)
    if form is None:
        return {"form": None, "reason": notice, "tables": []}
    spec, warnings = load(form, fy.end_date.year)
    if notice:
        warnings.insert(0, notice)
    taxes = None
    values: dict[str, dict[str, int | None]] = {}
    tables = []
    for table in spec["tables"]:
        own: dict[str, int | None] = {}
        rows = []
        for row in table["rows"]:
            if "accounts" in row:
                kind, amount = "accounts", _account_value(fy, row)
            elif "tax" in row:
                if taxes is None:
                    taxes = _tax_values(fy)
                kind, amount = "tax", taxes[row["tax"]]
            elif "sum" in row:
                kind = "total"
                amount = (sum(own.get(c) or 0 for c in row["sum"]) - sum(own.get(c) or 0 for c in row.get("minus", [])))
            else:
                kind, amount = "manual", None
            own[row["case"]] = amount
            rows.append({"case": row["case"], "label": row["label"], "kind": kind, "amount_cents": amount,
                         "detail": bool(row.get("detail")), "note": row.get("note"), "unit": row.get("unit"),
                         "accounts": row.get("accounts"), "exclude": row.get("exclude")})
        values[table["code"]] = own
        tables.append({"code": table["code"], "title": table["title"], "rows": rows, "checks": table.get("checks", [])})
    flat: dict[str, int | None] = {}
    for own in values.values():
        for case, amount in own.items():
            flat.setdefault(case, amount)
    for table in tables:
        own = values[table["code"]]
        results = []
        for check in table.pop("checks"):
            left_case, right_case = check["equal"]
            pick = lambda c: own[c] if c in own else flat.get(c)  # noqa: E731
            left = (pick(left_case) or 0) - sum(pick(c) or 0 for c in check.get("minus", []))
            right = pick(right_case) or 0
            results.append({"label": check["label"], "ok": left == right, "difference_cents": left - right})
            if left != right:
                warnings.append(f"{table['code']} : {check['label']} — écart de {(left - right) / 100:,.2f} €."
                                .replace(",", " ").replace(".", ","))
        table["checks"] = results
    return {"form": form, "millesime": spec["millesime"], "title": spec["title"], "reliability": spec.get("reliability"),
            "sources": spec.get("sources", []), "read_on": spec.get("read_on"), "not_covered": spec.get("not_covered", []),
            "fiscal_year": {"id": fy.id, "label": fy.label, "end_date": fy.end_date.isoformat()},
            "warnings": warnings, "tables": tables}
