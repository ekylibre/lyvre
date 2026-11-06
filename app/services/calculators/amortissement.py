"""Calculette 23 : plan d'amortissement d'un bien (lot AG12.a). Calcul de `assets.schedule` (registre des
immobilisations, lot F5), sur un bien simulé : aucune écriture, aucun bien créé."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.models import Asset
from app.services import assets
from app.services.calculators import CalculatorError, Context, Input, Result, Spec, euros, number

SPEC = Spec(
    code="amortissement", number="23", title="Amortissement d'un bien", category="fiscal",
    summary="Plan d'amortissement linéaire ou dégressif d'un matériel, d'un bâtiment ou d'un bien vivant, "
            "exercice par exercice.",
    inputs=[
        Input("base", "Base amortissable", "money", "€", help="Coût d'acquisition HT moins la valeur résiduelle"),
        Input("acquired_on", "Date d'acquisition", "date"),
        Input("in_service_on", "Date de mise en service", "date", required=False,
              help="Linéaire : le plan part de la mise en service (à défaut, de l'acquisition)"),
        Input("duration_months", "Durée d'utilisation", "integer", "mois"),
        Input("method", "Méthode", "choice", choices=[("linear", "Linéaire"), ("regressive", "Dégressif")],
              default="linear"),
        Input("coefficient", "Coefficient dégressif", "number", required=False,
              help="Vide : coefficient usuel selon la durée (1,25, 1,75 ou 2,25)"),
    ],
    example={"base": "45000", "acquired_on": "2026-03-15", "in_service_on": "2026-04-01", "duration_months": "84",
             "method": "linear", "coefficient": ""},
    method="Méthode du registre des immobilisations de Lyvre (reprise d'Ekylibre) : jours comptés en base 360 (mois "
           "de 30 jours). Linéaire : à partir de la mise en service, dotation = reste à amortir × jours de l'exercice "
           "÷ jours restants du plan. Dégressif : à partir du 1er jour du mois d'acquisition, taux = coefficient ÷ "
           "années, bascule en linéaire quand il devient plus avantageux. Les périodes suivent les exercices de "
           "l'instance, sinon des années de même début. Limites : simulation sans dotations déjà passées ni sortie ; "
           "le choix de la durée et de la méthode relève des usages et du CGI (art. 39 A pour le dégressif).",
    prefill_label="Bien du registre",
)


def on_date(values: dict) -> date:
    return values["acquired_on"]


def prefill_options(ctx: Context) -> list[dict]:
    rows = Asset.query.filter(Asset.method != "none", Asset.status.in_(("in_use", "waiting"))).order_by(Asset.label)
    return [{"value": str(a.id), "label": f"{a.label} ({a.acquired_on:%d/%m/%Y})"} for a in rows]


def prefill(ctx: Context) -> dict:
    from app.extensions import db
    asset = db.session.get(Asset, int(ctx.choice)) if (ctx.choice or "").isdigit() else None
    if asset is None:
        return {}
    origin = f"registre des immobilisations : {asset.label}"
    values = {"base": (f"{asset.base_cents / 100:.2f}", origin), "acquired_on": (asset.acquired_on.isoformat(), origin),
              "duration_months": (str(asset.duration_months or ""), origin),
              "method": (asset.method if asset.method in ("linear", "regressive") else "linear", origin)}
    if asset.in_service_date:
        values["in_service_on"] = (asset.in_service_date.isoformat(), origin)
    if asset.fiscal_coefficient:
        values["coefficient"] = (str(asset.fiscal_coefficient), origin)
    return {k: {"value": v, "origin": o} for k, (v, o) in values.items()}


def compute(values: dict, on: date) -> Result:
    if values["base"] <= 0:
        raise CalculatorError("Base amortissable positive attendue.", "base")
    if values["duration_months"] <= 0 or values["duration_months"] > 1200:
        raise CalculatorError("Durée en mois entre 1 et 1 200.", "duration_months")
    regressive = values["method"] == "regressive"
    coefficient = values["coefficient"] if regressive and values["coefficient"] else (
        assets.default_coefficient(values["duration_months"]) if regressive else None)
    simulated = Asset(label="Simulation", acquired_on=values["acquired_on"],
                      in_service_date=values["in_service_on"] or values["acquired_on"],
                      acquisition_cents=values["base"], residual_cents=0, method=values["method"],
                      duration_months=values["duration_months"], fiscal_coefficient=coefficient, status="in_use",
                      prior_depreciation_cents=0)
    rows = assets.schedule(simulated)
    warnings = []
    if regressive and values["duration_months"] < 36:
        warnings.append("Dégressif : réservé aux biens d'une durée d'au moins 3 ans (CGI art. 39 A).")
    first = rows[0] if rows else None
    headline = [("Première dotation", f"{euros(first.amount_cents)} ({first.label})" if first else "—"),
                ("Nombre d'exercices", str(len(rows)))]
    details = [("Méthode", "Dégressif" if regressive else "Linéaire")]
    if regressive:
        details.append(("Coefficient", number(coefficient)))
        details.append(("Taux dégressif", number(Decimal(coefficient) * 1200 / values["duration_months"]) + " %"))
    else:
        details.append(("Taux linéaire", number(1200 / values["duration_months"]) + " %"))
    table = {"columns": ["Exercice", "Du", "Au", "Jours", "Dotation", "Cumul", "Valeur nette"],
             "rows": [[r.label, f"{r.start:%d/%m/%Y}", f"{r.stop:%d/%m/%Y}", r.days, euros(r.amount_cents),
                       euros(r.cumulative_cents), euros(r.net_cents)] for r in rows]}
    return Result(headline=headline, details=details, table=table, warnings=warnings,
                  actions=[("Registre des immobilisations", "/assets/")])
