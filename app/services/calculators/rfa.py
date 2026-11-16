"""Calculette 24 : remboursement forfaitaire agricole (lot AG12.b). Forfait par `rfa.flat_amount` (règle unique de la
demande, lot AG2.e) et contrôle du seuil sur deux années ; préremplissage par la demande de l'année."""
from __future__ import annotations

from datetime import date

from app.services import rfa
from app.services.calculators import CalculatorError, Context, Input, Result, Spec, euros, pct

SPEC = Spec(
    code="rfa", number="24", title="Remboursement forfaitaire agricole", category="vat",
    summary="Forfait sur les ventes de l'année à des clients assujettis, par classe de taux, et contrôle du seuil "
            "au-delà duquel le régime simplifié devient obligatoire.",
    inputs=[
        Input("year", "Année des ventes", "integer"),
        Input("high_base", "Ventes au taux majoré", "money", "€",
              help="Lait, animaux de basse-cour, œufs, animaux de boucherie et de charcuterie, céréales, oléo-protéagineux"),
        Input("low_base", "Ventes au taux réduit", "money", "€", help="Autres produits"),
        Input("receipts_previous", "Recettes de l'année précédente", "money", "€", required=False),
        Input("receipts_year", "Recettes de l'année", "money", "€", required=False),
        Input("factor", "Associés (GAEC)", "integer", default="1", help="Le seuil se multiplie par associé en GAEC"),
    ],
    example={"year": "2026", "high_base": "38000", "low_base": "6500", "receipts_previous": "41000",
             "receipts_year": "44500", "factor": "1"},
    method="Forfait = ventes au taux majoré × taux majoré + ventes au taux réduit × taux réduit, arrondi à l'euro (CGI "
           "art. 298 quater). Seules comptent les ventes à des assujettis (professionnels, clients de l'UE, export), "
           "pas aux particuliers. Seuil : moyenne des recettes de deux années civiles consécutives ; au-delà, régime "
           "simplifié agricole obligatoire au 1er janvier suivant (art. 298 bis). Limites : la demande se fait sur "
           "la page Remboursement forfaitaire avec les attestations d'achats des clients.",
    params=("vat.rfa.rate_high_bp", "vat.rfa.rate_low_bp", "vat.rfa.threshold_cents"),
)


def on_date(values: dict) -> date:
    return date(values["year"], 12, 31)


def prefill(ctx: Context) -> dict:
    year = date.today().year - 1
    try:
        data = rfa.compute(year)
    except Exception:  # noqa: BLE001 — préremplissage facultatif
        return {"year": {"value": str(year), "origin": "année précédente"}}
    origin = f"ventes {year} (Remboursement forfaitaire)"
    t = data["threshold"]
    out = {"year": {"value": str(year), "origin": "année précédente"},
           "high_base": {"value": f"{data['high_base_cents'] / 100:.2f}", "origin": origin},
           "low_base": {"value": f"{data['low_base_cents'] / 100:.2f}", "origin": origin},
           "factor": {"value": str(t["factor"]), "origin": "associés exploitants"}}
    for key, row in zip(("receipts_previous", "receipts_year"), t["years"]):
        if row["receipts_cents"]:
            out[key] = {"value": f"{row['receipts_cents'] / 100:.2f}", "origin": f"recettes {row['year']} (comptabilité)"}
    return out


def compute(values: dict, on: date) -> Result:
    from app.services import reg_params
    if values["factor"] < 1:
        raise CalculatorError("Au moins 1 associé.", "factor")
    high_bp, low_bp = reg_params.value("vat.rfa.rate_high_bp", on), reg_params.value("vat.rfa.rate_low_bp", on)
    threshold = reg_params.value("vat.rfa.threshold_cents", on)
    amount = rfa.flat_amount(values["high_base"], values["low_base"], high_bp, low_bp)
    details = [("Taux majoré", pct(high_bp)), ("Taux réduit", pct(low_bp)),
               ("Seuil (× associés)", euros(threshold * values["factor"]))]
    warnings = []
    known = [v for v in (values["receipts_previous"], values["receipts_year"]) if v]
    if known:
        average = round(sum(known) / len(known))
        details.append(("Moyenne des recettes", euros(average)))
        if average > threshold * values["factor"]:
            warnings.append(f"Moyenne au-dessus du seuil : régime simplifié agricole obligatoire au 1er janvier "
                            f"{values['year'] + 1}.")
    return Result(headline=[("Remboursement forfaitaire", euros(amount))], details=details, warnings=warnings,
                  actions=[("Remboursement forfaitaire", f"/rfa/?year={values['year']}")])
