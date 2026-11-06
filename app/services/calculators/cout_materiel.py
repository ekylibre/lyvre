"""Calculette 22 : coût de revient d'un matériel (lot AG12.b), à l'heure et à l'hectare. Amortissement prérempli par
le registre des immobilisations (`assets.schedule`) ; les autres frais se saisissent."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.services.calculators import CalculatorError, Context, Input, Result, Spec, euros

SPEC = Spec(
    code="cout-materiel", number="22", title="Coût de revient d'un matériel", category="management",
    summary="Charges fixes et variables d'un matériel ramenées à l'heure d'utilisation et à l'hectare.",
    inputs=[
        Input("depreciation", "Amortissement annuel", "money", "€"),
        Input("financial", "Frais financiers annuels", "money", "€", required=False, help="Intérêts de l'emprunt"),
        Input("insurance", "Assurance et remisage annuels", "money", "€", required=False),
        Input("maintenance", "Entretien et réparations annuels", "money", "€", required=False),
        Input("hours", "Heures d'utilisation par an", "number", "h"),
        Input("fuel_per_hour", "Consommation de carburant", "number", "l/h", required=False),
        Input("fuel_price", "Prix du carburant", "number", "€/l", required=False, help="Prix saisi : date et source à noter"),
        Input("hectares", "Hectares travaillés par an", "number", "ha", required=False),
        Input("driver_per_hour", "Coût du chauffeur", "number", "€/h", required=False),
    ],
    example={"depreciation": "9600", "financial": "1100", "insurance": "650", "maintenance": "2400", "hours": "480",
             "fuel_per_hour": "14", "fuel_price": "1.15", "hectares": "320", "driver_per_hour": ""},
    method="Charges fixes (amortissement, frais financiers, assurance et remisage) divisées par les heures d'utilisation "
           "de l'année ; charges variables par heure : entretien et réparations ÷ heures, carburant (consommation × "
           "prix), chauffeur si indiqué. Coût à l'hectare = coût annuel total ÷ hectares travaillés. Limites : prix du "
           "carburant saisi (pas de cours en direct) ; l'amortissement comptable n'est pas forcément la durée réelle "
           "d'usage ; pas de valeur de revente ni de coût d'opportunité du capital.",
    prefill_label="Bien du registre",
)


def prefill_options(ctx: Context) -> list[dict]:
    from app.models import Asset
    rows = Asset.query.filter(Asset.method != "none", Asset.status == "in_use").order_by(Asset.label)
    return [{"value": str(a.id), "label": a.label} for a in rows]


def prefill(ctx: Context) -> dict:
    from app.extensions import db
    from app.models import Asset
    from app.services import assets
    asset = db.session.get(Asset, int(ctx.choice)) if (ctx.choice or "").isdigit() else None
    if asset is None:
        return {}
    today = date.today()
    row = next((r for r in assets.schedule(asset) if r.start <= today <= r.stop), None) or next(iter(assets.schedule(asset)), None)
    if row is None:
        return {}
    return {"depreciation": {"value": f"{row.amount_cents / 100:.2f}",
                             "origin": f"dotation {row.label} de « {asset.label} » (registre)"}}


def compute(values: dict, on: date) -> Result:
    hours = values["hours"]
    if hours <= 0:
        raise CalculatorError("Heures d'utilisation positives attendues.", "hours")
    fixed = values["depreciation"] + (values["financial"] or 0) + (values["insurance"] or 0)
    maintenance = values["maintenance"] or 0
    fuel_hour = (values["fuel_per_hour"] or Decimal(0)) * (values["fuel_price"] or Decimal(0)) * 100
    driver_hour = (values["driver_per_hour"] or Decimal(0)) * 100
    cents = lambda v: int(Decimal(v).quantize(Decimal(1)))  # noqa: E731
    fixed_hour = cents(Decimal(fixed) / hours)
    variable_hour = cents(Decimal(maintenance) / hours + fuel_hour + driver_hour)
    per_hour = fixed_hour + variable_hour
    annual = fixed + maintenance + cents((fuel_hour + driver_hour) * hours)
    headline = [("Coût par heure", euros(per_hour))]
    details = [("Charges fixes annuelles", euros(fixed)), ("Charges fixes par heure", euros(fixed_hour)),
               ("Charges variables par heure", euros(variable_hour)), ("Coût annuel total", euros(annual))]
    if values["hectares"]:
        if values["hectares"] <= 0:
            raise CalculatorError("Hectares positifs attendus.", "hectares")
        headline.append(("Coût par hectare", euros(cents(Decimal(annual) / values["hectares"]))))
    warnings = []
    if values["fuel_per_hour"] and not values["fuel_price"]:
        warnings.append("Consommation sans prix du carburant : carburant non compté.")
    return Result(headline=headline, details=details, warnings=warnings,
                  actions=[("Registre des immobilisations", "/assets/")])
