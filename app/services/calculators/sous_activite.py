"""Calculette 26 : charges de sous-activité (lot CG5.e, claudedocs/design_fiabilisation_cegara.md § 8.5).

Règle (relue le 07/11/2026) :
- PCG art. 213-32 et 618-13, 2° : les frais généraux fixes de production s'affectent au coût des stocks d'après la
  capacité normale, « production moyenne que l'on s'attend à réaliser sur un certain nombre d'exercices ou de saisons » ;
  la part non affectée est une charge de l'exercice ;
- fiscal : ann. III art. 38 nonies, BOI-BIC-PDSTK-20-20-10-10 § 240 (charges de sous-activité exclues du coût de
  production), applicable au BA par BOI-BA-BASE-20-20-20-10 § 90.
Aucun texte ne fixe la formule de la capacité normale ni ne qualifie expressément une baisse de rendement agricole de
sous-activité : moyenne simple par défaut, variante « 3 valeurs médianes sur 5 » signalée comme une pratique à valider.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.services.calculators import CalculatorError, Input, Result, Spec, euros, number

D = Decimal
YEARS = ("y1", "y2", "y3", "y4", "y5")

SPEC = Spec(
    code="sous-activite", number="26", title="Charges de sous-activité", category="management",
    summary="Part des charges fixes de production à écarter du coût des stocks quand la production de l'année est "
            "inférieure à la production normale.",
    inputs=[
        *[Input(k, f"Production de l'année N-{i}", "number", "t ou unités", required=i <= 3,
                help="Même unité pour toutes les années" if i == 1 else None) for i, k in enumerate(YEARS, start=1)],
        Input("current", "Production de l'année", "number", "t ou unités"),
        Input("fixed", "Frais généraux fixes de production", "money", "€",
              help="Amortissements et entretien du matériel et des bâtiments de production, imputés à ce produit"),
        Input("method", "Production normale", "choice", required=False, default="average",
              choices=[("average", "Moyenne des années saisies"),
                       ("median3", "Moyenne des 3 valeurs médianes (5 années, extrêmes écartés)")]),
    ],
    example={"y1": "62", "y2": "71", "y3": "48", "y4": "69", "y5": "66", "current": "41", "fixed": "18000",
             "method": "average"},
    method="Production normale = moyenne des productions des années passées (ou des 3 valeurs médianes sur 5 ans, "
           "pratique à valider) ; taux d'activité = production de l'année ÷ production normale ; frais fixes imputables "
           "au stock = frais fixes × taux d'activité (au plus 100 %) ; le reste est la charge de sous-activité, laissée en "
           "charge de l'exercice (PCG art. 213-32 et 618-13 ; ann. III art. 38 nonies). Limites : aucun texte ne fixe la "
           "formule de la production normale ni ne qualifie expressément une baisse de rendement agricole (aléa "
           "climatique) de sous-activité ; à valider avec l'expert-comptable. Les frais variables ne sont pas concernés.",
    sources=(("PCG 2026, art. 213-32 et 618-13", "https://www.anc.gouv.fr/reglement-ndeg-2020-03-du-3-juillet-2020"),
             ("BOI-BIC-PDSTK-20-20-10-10 § 240", "https://bofip.impots.gouv.fr/doctrine/pgp/1497-PGP")),
)


def compute(values: dict, on: date) -> Result:
    history = [D(values[k]) for k in YEARS if values.get(k) is not None]
    if len(history) < 3:
        raise CalculatorError("Au moins 3 années de production attendues.", "y3")
    if any(v < 0 for v in history):
        raise CalculatorError("Productions positives attendues.", "y1")
    current = values.get("current")
    if current is None or current < 0:
        raise CalculatorError("Production de l'année positive attendue.", "current")
    fixed = values.get("fixed")
    if fixed is None or fixed < 0:
        raise CalculatorError("Frais fixes positifs attendus.", "fixed")
    method = values.get("method") or "average"
    warnings = []
    if method == "median3":
        if len(history) != 5:
            raise CalculatorError("La variante « 3 valeurs médianes » demande les 5 années.", "y5")
        kept = sorted(history)[1:4]
        warnings.append("Variante « 3 valeurs médianes sur 5 ans » : pratique de centres de gestion, non fixée par les "
                        "textes ; à valider avec l'expert-comptable.")
    else:
        kept = history
    normal = sum(kept) / len(kept)
    if normal <= 0:
        raise CalculatorError("Production normale nulle : saisissez les productions passées.", "y1")
    rate = min(D(current) / normal, D(1))
    imputable = int((D(fixed) * rate).quantize(D(1)))
    under = fixed - imputable
    headline = [("Charge de sous-activité", euros(under)), ("Frais fixes imputables au stock", euros(imputable))]
    details = [("Production normale", number(normal, 2)), ("Taux d'activité", number(rate * 100, 1) + " %"),
               ("Années retenues", ", ".join(number(v, 2) for v in kept))]
    if D(current) >= normal:
        warnings.append("Production de l'année au moins égale à la production normale : pas de sous-activité.")
    warnings.append("Baisse de rendement agricole (aléa climatique) traitée en sous-activité : non prévu expressément "
                    "par les textes, à valider.")
    return Result(headline=headline, details=details, warnings=warnings,
                  actions=[("Inventaire de clôture", "/inventory/")])
