"""Calculettes du groupe B (lot AG12.c, claudedocs/design_calculettes_agricoles.md § 3) : 11 réfaction humidité,
12 prix d'équilibre, 14 coût d'un chantier d'entraide, 09 solaire sur hangar, 05 gazole et GNR (sans le
remboursement de TICPE, qui attend son paramètre sourcé, AG12.d).

Normes, barèmes, tarifs et prix se **saisissent** (AGD15) : aucune valeur de référence dans le code."""
from __future__ import annotations

import math
from datetime import date
from decimal import Decimal

from app.services.calculators import CalculatorError, Input, Result, Spec, Tool, euros, number, positive

D = Decimal


def _n(value, digits=2) -> str:
    return number(value, digits)


def _cents(value: Decimal) -> int:
    return int((value * 100).quantize(D(1)))


def refaction(v, on):
    gross = positive(v, "gross", "Poids brut")
    measured, base = positive(v, "measured", "Humidité mesurée", True), positive(v, "base", "Humidité de base")
    if measured >= 100 or base >= 100:
        raise CalculatorError("Humidité inférieure à 100 % attendue.", "measured")
    standard = gross * (100 - measured) / (100 - base) if measured > base else gross
    points = max(measured - base, D(0))
    details = [("Points au-dessus de la norme", _n(points, 1)), ("Réfaction", _n(gross - standard, 3) + " t")]
    headline = [("Poids aux normes", _n(standard, 3) + " t")]
    if v["drying"] is not None and points:
        cost = v["drying"] * points * gross
        headline.append(("Frais de séchage", euros(_cents(cost))))
    warnings = [] if measured > base else ["Humidité sous la norme : pas de réfaction (pas de bonification comptée)."]
    return Result(headline=headline, details=details, warnings=warnings)


def break_even(v, on):
    yield_t = positive(v, "yield", "Rendement")
    costs = D(positive(v, "costs", "Charges par hectare", True)) / 100
    aids = D(v["aids"] or 0) / 100
    other = D(v["other"] or 0) / 100
    price = (costs - aids - other) / yield_t
    headline = [("Prix d'équilibre", _n(price, 2) + " €/t")]
    details = [("Charges à couvrir par la vente", _n(costs - aids - other, 2) + " €/ha")]
    if v["market"] is not None:
        result = v["market"] * yield_t + aids + other - costs
        headline.append(("Résultat au cours saisi", _n(result, 2) + " €/ha"))
        details.append(("Écart au cours", _n(v["market"] - price, 2) + " €/t"))
    return Result(headline=headline, details=details, actions=[("Marges par activité", "/activities/margins")])


def mutual_aid(v, on):
    rate = positive(v, "rate", "Débit de chantier")
    per_ha = (positive(v, "tool", "Tarif de l'outil", True) + positive(v, "tractor", "Tarif du tracteur", True)
              + positive(v, "driver", "Coût du chauffeur", True)) / rate
    headline = [("Coût par hectare", _n(per_ha, 2) + " €/ha")]
    if v["surface"]:
        headline.append(("Coût du chantier", euros(_cents(per_ha * v["surface"]))))
    return Result(headline=headline, details=[("Coût horaire total", _n(v["tool"] + v["tractor"] + v["driver"], 2) + " €/h")],
                  actions=[("Écritures d'entraide (472)", "/entries/")])


def solar(v, on):
    production = positive(v, "power", "Puissance") * positive(v, "yield", "Productible")
    share = positive(v, "self_use", "Autoconsommation", True) / 100 if v["self_use"] is not None else D(0)
    if share > 1:
        raise CalculatorError("Autoconsommation de 100 % au plus.", "self_use")
    sold = production * (1 - share)
    revenue = sold * positive(v, "tariff", "Tarif d'achat", True)
    headline = [("Production annuelle", _n(production, 0) + " kWh"), ("Vente annuelle", euros(_cents(revenue)))]
    details = [("Électricité vendue", _n(sold, 0) + " kWh")]
    if share and v["power_price"] is not None:
        saving = production * share * v["power_price"]
        headline.append(("Économie d'achat d'électricité", euros(_cents(saving))))
    return Result(headline=headline, details=details,
                  warnings=["Recette accessoire au bénéfice agricole dans certaines limites (CGI art. 75 et 75 A) : "
                            "voir Fiscalité › Revenus accessoires."])


def fuel(v, on):
    litres = positive(v, "litres", "Consommation annuelle")
    road, gnr = positive(v, "road_price", "Prix du gazole", True), positive(v, "gnr_price", "Prix du GNR", True)
    gap = (road - gnr) * litres
    return Result(headline=[("Coût annuel au GNR", euros(_cents(gnr * litres))),
                            ("Écart avec le gazole routier", euros(_cents(gap)))],
                  details=[("Écart par litre", _n(road - gnr, 3) + " €/l")],
                  warnings=["Remboursement partiel de TICPE non compté : il attend son taux sourcé (lot AG12.d)."])


def I(key, label, kind="number", unit=None, required=True, **kw):  # noqa: E743
    return Input(key, label, kind, unit, required, **kw)


TOOLS = [
    Tool(Spec(code="refaction-humidite", number="11", title="Réfaction humidité", category="harvest",
              summary="Poids aux normes d'une livraison de grain trop humide, réfaction et frais de séchage.",
              inputs=[I("gross", "Poids brut livré", unit="t"), I("measured", "Humidité mesurée", unit="%"),
                      I("base", "Humidité de base (norme)", unit="%", help="Norme de votre organisme stockeur (saisie)"),
                      I("drying", "Frais de séchage", unit="€/t/point", required=False)],
              example={"gross": "28.4", "measured": "18.5", "base": "15", "drying": "1.9"},
              method="Poids aux normes = poids brut × (100 − humidité mesurée) ÷ (100 − humidité de base) ; frais de "
                     "séchage = points d'humidité au-dessus de la norme × tarif × poids brut. Normes, impuretés et tarifs "
                     "dépendent du contrat de l'organisme stockeur : saisissez les siens."), refaction),
    Tool(Spec(code="prix-equilibre", number="12", title="Prix d'équilibre", category="management",
              summary="Prix de vente minimum (€/t) pour couvrir les charges d'une culture, comparé à un cours saisi.",
              inputs=[I("costs", "Charges par hectare", "money", "€/ha", help="Charges opérationnelles et de structure à couvrir"),
                      I("aids", "Aides par hectare", "money", "€/ha", required=False),
                      I("other", "Autres produits par hectare", "money", "€/ha", required=False, help="Paille, sous-produits"),
                      I("yield", "Rendement", unit="t/ha"), I("market", "Cours saisi", unit="€/t", required=False,
                                                                 help="Date et source à noter (pas de cours en direct)")],
              example={"costs": "1450", "aids": "180", "other": "60", "yield": "7.2", "market": "195"},
              method="Prix d'équilibre = (charges − aides − autres produits) ÷ rendement. Le résultat dépend des charges "
                     "retenues : opérationnelles seules (seuil de marge brute) ou complètes (seuil de rentabilité). Les "
                     "charges de l'activité se lisent dans Marges par activité."), break_even),
    Tool(Spec(code="entraide", number="14", title="Coût d'un chantier d'entraide", category="equipment",
              summary="Coût par hectare d'un chantier d'entraide ou de prestation, d'après un barème départemental saisi.",
              inputs=[I("tool", "Tarif de l'outil", unit="€/h"), I("tractor", "Tarif du tracteur", unit="€/h"),
                      I("driver", "Coût du chauffeur", unit="€/h"), I("rate", "Débit de chantier", unit="ha/h"),
                      I("surface", "Surface", unit="ha", required=False)],
              example={"tool": "28", "tractor": "35", "driver": "22", "rate": "2.5", "surface": "40"},
              method="Coût (€/ha) = (outil + tracteur) ÷ débit + chauffeur ÷ débit, tarifs horaires du barème d'entraide "
                     "de votre département (saisis). En comptabilité, l'entraide se suit en 472 (conventions)."), mutual_aid),
    Tool(Spec(code="solaire", number="09", title="Solaire sur hangar", category="energy",
              summary="Production et recette annuelles d'une installation photovoltaïque, au tarif d'achat saisi.",
              inputs=[I("power", "Puissance", unit="kWc"), I("yield", "Productible", unit="kWh/kWc/an",
                                                                help="Selon le lieu et l'orientation (étude ou simulateur)"),
                      I("tariff", "Tarif d'achat", unit="€/kWh", help="Tarif de votre contrat (saisi)"),
                      I("self_use", "Autoconsommation", unit="%", required=False),
                      I("power_price", "Prix d'achat de l'électricité", unit="€/kWh", required=False)],
              example={"power": "100", "yield": "1150", "tariff": "0.105", "self_use": "", "power_price": ""},
              method="Production = puissance × productible ; vente = production non autoconsommée × tarif d'achat ; "
                     "économie = production autoconsommée × prix de l'électricité. Limites : pas de baisse de rendement "
                     "dans le temps, ni de coût d'installation, d'entretien ou de raccordement."), solar),
    Tool(Spec(code="gnr", number="05", title="Gazole et GNR", category="equipment",
              summary="Coût annuel du gazole non routier et écart avec le gazole routier, aux prix saisis.",
              inputs=[I("litres", "Consommation annuelle", unit="l"), I("gnr_price", "Prix du GNR", unit="€/l"),
                      I("road_price", "Prix du gazole routier", unit="€/l")],
              example={"litres": "12000", "gnr_price": "1.12", "road_price": "1.62"},
              method="Coût = litres × prix ; écart = (prix routier − prix GNR) × litres. Prix saisis avec leur date et "
                     "leur source (pas de prix en direct). Le remboursement partiel de TICPE viendra avec son taux sourcé."),
         fuel),
]
