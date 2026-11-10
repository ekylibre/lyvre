"""Calculette 21 : marge brute d'un atelier ou d'une activité (lot AG12.b). Même définition que l'état des marges
(`analytic_margins._summary`, AG8) : produit brut − charges opérationnelles, par unité de mesure."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.services.calculators import CalculatorError, Context, Input, Result, Spec, euros

SPEC = Spec(
    code="marge-brute", number="21", title="Marge brute d'une activité", category="management",
    summary="Produit brut, charges opérationnelles et marge brute d'une activité, au total et par hectare ou par tête.",
    inputs=[
        Input("sales", "Ventes", "money", "€"),
        Input("aids", "Aides couplées et aides de l'activité", "money", "€", required=False),
        Input("other", "Autres produits et variation de stock", "money", "€", required=False,
              help="Production stockée, autoconsommation ; moins les achats d'animaux"),
        Input("operational", "Charges opérationnelles", "money", "€",
              help="Semences, engrais, produits de défense, aliments, frais vétérinaires, travaux spécifiques"),
        Input("measure", "Surface ou effectif", "number", required=False),
        Input("unit", "Unité", "choice", required=False, choices=[("ha", "hectare"), ("head", "tête")], default="ha"),
    ],
    example={"sales": "86000", "aids": "4200", "other": "-1500", "operational": "38500", "measure": "62", "unit": "ha"},
    method="Produit brut = ventes + aides de l'activité + autres produits (production stockée, autoconsommation, moins "
           "les achats d'animaux) ; marge brute = produit brut − charges opérationnelles (charges propres à l'activité). "
           "Même définition que l'état des marges de Lyvre. Limites : les charges de structure (matériel, bâtiments, "
           "main-d'œuvre permanente) ne sont pas déduites ; la marge par unité suppose une mesure de la campagne.",
    prefill_label="Activité et campagne",
)


def _fy():
    from app.models import FiscalYear
    from app.services.ledger import open_fiscal_year_for
    return open_fiscal_year_for(date.today()) or FiscalYear.query.order_by(FiscalYear.end_date.desc()).first()


# Essai de l'interface (10/11/2026) : affiché quand rien n'est à reprendre du dossier.
PREFILL_EMPTY = "aucune activité (Gestion › Activités)"

def prefill_options(ctx: Context) -> list[dict]:
    from app.services import analytic_margins
    fy = _fy()
    if fy is None:
        return []
    rows = analytic_margins.compute(fy)["productions"]
    return [{"value": f"{r['activity_id']}:{r['campaign_year']}", "label": f"{r['activity']} — campagne {r['campaign_year']}"}
            for r in rows]


def prefill(ctx: Context) -> dict:
    from app.services import analytic_margins
    fy = _fy()
    if fy is None or ":" not in (ctx.choice or ""):
        return {}
    activity_id, year = ctx.choice.split(":", 1)
    row = next((r for r in analytic_margins.compute(fy)["productions"]
                if str(r["activity_id"]) == activity_id and str(r["campaign_year"]) == year), None)
    if row is None:
        return {}
    c = row["classes"]
    origin = f"état des marges {fy.label}, {row['activity']} {row['campaign_year']}"
    other = c.get("other_products", 0) + c.get("stock_production", 0) - c.get("animal_purchases", 0)
    out = {"sales": c.get("sales", 0), "aids": c.get("aids", 0), "other": other, "operational": row["operational_cents"]}
    values = {k: {"value": f"{v / 100:.2f}", "origin": origin} for k, v in out.items()}
    if row["measure"] is not None:
        values["measure"] = {"value": row["measure"], "origin": "mesure de la campagne"}
        values["unit"] = {"value": "head" if row["unit"] == "head" else "ha", "origin": "unité de l'activité"}
    return values


def compute(values: dict, on: date) -> Result:
    production = values["sales"] + (values["aids"] or 0) + (values["other"] or 0)
    margin = production - values["operational"]
    headline = [("Marge brute", euros(margin))]
    details = [("Produit brut", euros(production)), ("Charges opérationnelles", euros(values["operational"]))]
    measure = values["measure"]
    if measure is not None:
        if measure <= 0:
            raise CalculatorError("Surface ou effectif positif attendu.", "measure")
        unit = "ha" if values["unit"] != "head" else "tête"
        per = lambda cents: int((Decimal(cents) / measure).quantize(Decimal(1)))  # noqa: E731
        headline.append((f"Marge brute par {unit}", euros(per(margin))))
        details += [(f"Produit brut par {unit}", euros(per(production))),
                    (f"Charges opérationnelles par {unit}", euros(per(values["operational"])))]
    if production:
        details.append(("Marge sur produit brut", f"{Decimal(margin) * 100 / production:.1f} %".replace(".", ",")))
    return Result(headline=headline, details=details, actions=[("Marges par activité", "/activities/margins")])
