"""Calculette 13 : plafond de la DEP (lot AG12.b). Règle unique `dep.ceiling_for` (lot AG6.c) : barème daté, associés
exploitants, durée de l'exercice, plafond global des déductions non rapportées."""
from __future__ import annotations

from datetime import date

from app.services import dep
from app.services.calculators import CalculatorError, Context, Input, Result, Spec, euros

SPEC = Spec(
    code="dep", number="13", title="Plafond de la DEP", category="fiscal",
    summary="Montant maximum de la déduction pour épargne de précaution d'un exercice, selon le bénéfice et le "
            "nombre d'associés exploitants.",
    inputs=[
        Input("closing", "Date de clôture de l'exercice", "date"),
        Input("profit", "Bénéfice imposable avant DEP", "money", "€", help="Après l'abattement jeune agriculteur"),
        Input("operators", "Associés exploitants", "integer", help="1 pour une exploitation individuelle", default="1"),
        Input("months", "Durée de l'exercice", "integer", "mois", default="12"),
        Input("pending", "Déductions non encore rapportées", "money", "€", required=False,
              help="DEP (et anciennes DPI / DPA) des exercices précédents non utilisées ni réintégrées"),
    ],
    example={"closing": "2026-12-31", "profit": "62000", "operators": "1", "months": "12", "pending": "15000"},
    method="Barème réglementaire appliqué au bénéfice (après l'abattement JA) : 100 % jusqu'au premier seuil, puis "
           "le montant fixe publié par le BOFiP au début de chaque tranche majoré de 30, 20 ou 10 % de l'excédent, dans la limite d'un plafond par exploitant ; multiplié par le nombre "
           "d'associés exploitants (4 au plus), sans dépasser le bénéfice ; au prorata d'un exercice de durée "
           "différente de 12 mois ; puis limité par le plafond global des déductions non rapportées (CGI art. 73). "
           "Limites : la DEP suppose une épargne bancaire d'au moins la moitié des déductions ; l'utilisation et la "
           "réintégration se suivent sur la page DEP.",
    params=("ba.dep.band1_cents", "ba.dep.band2_cents", "ba.dep.band3_cents", "ba.dep.band4_cents", "ba.dep.rate2_bp",
            "ba.dep.rate3_bp", "ba.dep.rate4_bp", "ba.dep.cap_cents", "ba.dep.fixed3_cents", "ba.dep.fixed4_cents",
            "ba.dep.global_cap_cents"),
)


def on_date(values: dict) -> date:
    return values["closing"]


def prefill(ctx: Context) -> dict:
    from app.models import FiscalYear
    from app.services import tax_result
    from app.services.ledger import open_fiscal_year_for
    fy = open_fiscal_year_for(date.today()) or FiscalYear.query.order_by(FiscalYear.end_date.desc()).first()
    if fy is None:
        return {}
    origin = f"exercice {fy.label}"
    out = {"closing": {"value": fy.end_date.isoformat(), "origin": origin},
           "operators": {"value": str(dep.operators(fy)), "origin": "associés exploitants (Structure › Associés)"},
           "months": {"value": str(dep._months(fy)), "origin": origin},  # noqa: SLF001
           "pending": {"value": f"{dep.outstanding(fy, exclude_fy=fy) / 100:.2f}", "origin": "registre de la DEP"}}
    try:
        data = tax_result.view(fy)
        base = data.get("fiscal_result_before_dep_cents", data["fiscal_result_cents"])
        out["profit"] = {"value": f"{base / 100:.2f}", "origin": f"résultat fiscal {fy.label} avant DEP"}
    except Exception:  # noqa: BLE001 — préremplissage facultatif
        pass
    return out


def compute(values: dict, on: date) -> Result:
    if not 1 <= values["operators"] <= 50:
        raise CalculatorError("Nombre d'associés exploitants entre 1 et 50.", "operators")
    if not 1 <= values["months"] <= 24:
        raise CalculatorError("Durée de l'exercice entre 1 et 24 mois.", "months")
    data = dep.ceiling_for(values["profit"], on, values["operators"], values["months"], values["pending"] or 0)
    if data.get("error"):
        raise CalculatorError(data["error"], status=409)
    details = [("Plafond par exploitant", euros(data.get("per_operator_cents", 0))),
               ("Associés exploitants retenus", str(data.get("operators")))]
    if "global_cap_cents" in data:
        details += [("Plafond global des déductions", euros(data["global_cap_cents"])),
                    ("Déductions non rapportées", euros(data["pending_cents"]))]
    warnings = []
    if values["profit"] <= 0:
        warnings.append("Pas de bénéfice : pas de DEP.")
    return Result(headline=[("Plafond de la DEP", euros(data["ceiling_cents"]))], details=details, warnings=warnings,
                  actions=[("Résultat fiscal et DEP", "/tax-result/")])
