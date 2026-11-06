"""Calculette 08 : micro-BA ou réel (lot AG12.a). Bénéfice micro-BA par `ba_regimes.micro_profit` (règle unique,
partagée avec Fiscalité › Régime), moyenne triennale des recettes, seuil ; comparaison au bénéfice réel estimé."""
from __future__ import annotations

from datetime import date

from app.services import ba_regimes
from app.services.calculators import Context, Input, Result, Spec, euros, pct

SPEC = Spec(
    code="micro-ba", number="08", title="Micro-BA ou réel", category="fiscal",
    summary="Moyenne triennale des recettes, bénéfice forfaitaire du micro-BA et comparaison avec le bénéfice réel.",
    inputs=[
        Input("year", "Année d'imposition", "integer"),
        Input("receipts_n2", "Recettes N-2", "money", "€"),
        Input("receipts_n1", "Recettes N-1", "money", "€"),
        Input("receipts_n", "Recettes N", "money", "€", help="Encaissements HT de l'année civile"),
        Input("real_result", "Bénéfice au réel estimé", "money", "€", required=False,
              help="Résultat fiscal de l'année au réel, pour comparer les assiettes"),
    ],
    example={"year": "2026", "receipts_n2": "61000", "receipts_n1": "68000", "receipts_n": "72000",
             "real_result": "21000"},
    method="Moyenne des recettes des trois dernières années civiles, diminuée de l'abattement réglementaire, sans "
           "descendre sous le minimum : c'est le bénéfice imposable au micro-BA de l'année (CGI art. 64 bis). Au-delà du "
           "seuil, le réel s'applique de plein droit à partir de l'année suivante (art. 69). Limites : seuil d'une "
           "exploitation individuelle (un GAEC multiplie les seuils par associé, voir Fiscalité › Régime) ; les "
           "sociétés créées depuis 1997 relèvent du réel (art. 69 D) ; le micro-BA ne donne droit ni à l'abattement "
           "JA ni à la DEP. Option pour le réel : dans le délai de déclaration des revenus de l'année précédente.",
    params=("ba.micro.threshold_cents", "ba.micro.allowance_bp", "ba.micro.minimum_cents"),
)


def on_date(values: dict) -> date:
    return date(values["year"], 12, 31)


def prefill(ctx: Context) -> dict:
    from app.models import FiscalYear
    from app.services.ledger import open_fiscal_year_for
    fy = open_fiscal_year_for(date.today()) or FiscalYear.query.order_by(FiscalYear.end_date.desc()).first()
    if fy is None:
        return {}
    try:
        data = ba_regimes.simulation(fy)
    except Exception:  # noqa: BLE001 — préremplissage facultatif : la saisie reste possible
        return {"year": {"value": str(fy.end_date.year), "origin": f"exercice {fy.label}"}}
    out = {"year": {"value": str(fy.end_date.year), "origin": f"exercice {fy.label}"}}
    for key, row in zip(("receipts_n2", "receipts_n1", "receipts_n"), data["receipts"]):
        if row["receipts_cents"] is not None:
            out[key] = {"value": f"{row['receipts_cents'] / 100:.2f}", "origin": f"recettes {row['year']} (comptabilité)"}
    if data.get("real_result_cents") is not None:
        out["real_result"] = {"value": f"{data['real_result_cents'] / 100:.2f}", "origin": data["real_basis"]}
    return out


def compute(values: dict, on: date) -> Result:
    from app.services import reg_params
    receipts = [values["receipts_n2"], values["receipts_n1"], values["receipts_n"]]
    average = round(sum(receipts) / 3)
    profit = ba_regimes.micro_profit(average, on)
    threshold = reg_params.value("ba.micro.threshold_cents", on)
    allowance = reg_params.value("ba.micro.allowance_bp", on)
    minimum = reg_params.value("ba.micro.minimum_cents", on)
    headline = [("Moyenne triennale", euros(average)), ("Bénéfice micro-BA", euros(profit))]
    details = [("Abattement", pct(allowance)), ("Minimum", euros(minimum)), ("Seuil du micro-BA", euros(threshold))]
    warnings = []
    if average > threshold:
        warnings.append(f"Moyenne au-dessus du seuil : réel de plein droit à partir du 1er janvier {values['year'] + 1}.")
    real = values["real_result"]
    if real is not None:
        lower = "micro-BA" if profit <= real else "réel"
        headline.append(("Assiette la plus basse", f"{lower} (écart {euros(abs(real - profit))})"))
        details.append(("Bénéfice au réel", euros(real)))
        warnings.append("Comparaison d'assiettes seulement : charges sociales (MSA), DEP, abattement JA et plus-values "
                        "changent aussi le choix.")
    return Result(headline=headline, details=details, warnings=warnings,
                  actions=[("Fiscalité › Régime", "/tax-result/")])
