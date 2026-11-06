"""Calculette 06 : calculatrice agricole, 34 outils (lot AG12.c, claudedocs/design_calculettes_agricoles.md § 9).

Calculs simples, sans paramètre réglementaire. Toute valeur de référence (densité, PMG, teneur, durée de gestation,
coefficient UGB, prix) est **saisie**, jamais fixée ici. Chaque outil est une calculette du registre (`TOOLS`).
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from decimal import Decimal

from app.services.calculators import CalculatorError, Input, Result, Spec, Tool, euros, number, positive

D = Decimal
METHOD_COMMON = " Calcul arithmétique simple : vérifiez les valeurs saisies (unités, références)."


def _spec(number_, code, title, category, summary, inputs, example, method) -> Spec:
    return Spec(code=f"calc-{code}", number=f"06.{number_}", title=title, category=category, summary=summary,
                inputs=inputs, example=example, method=method + METHOD_COMMON)


def _n(value, digits=2) -> str:
    return number(value, digits)


def _hours(value: Decimal) -> str:
    minutes = int((value * 60).to_integral_value())
    return f"{minutes // 60} h {minutes % 60:02d}"


# ------------------------------------------------------------------ surfaces et mesures

SURFACE = {"ha": D(10000), "a": D(100), "m2": D(1), "km2": D(1_000_000)}
SURFACE_LABELS = [("ha", "hectare"), ("a", "are"), ("m2", "m²"), ("km2", "km²")]
MASS_VOLUME = {"t": ("masse", D(1000)), "q": ("masse", D(100)), "kg": ("masse", D(1)),
               "m3": ("volume", D(1000)), "hl": ("volume", D(100)), "l": ("volume", D(1))}
MASS_VOLUME_LABELS = [("t", "tonne"), ("q", "quintal"), ("kg", "kg"), ("m3", "m³"), ("hl", "hectolitre"), ("l", "litre")]


def surfaces(v, on):
    m2 = positive(v, "value", "Valeur", True) * SURFACE[v["unit"]]
    rows = [[label, _n(m2 / SURFACE[key], 4)] for key, label in SURFACE_LABELS]
    return Result(headline=[("En hectares", _n(m2 / SURFACE["ha"], 4) + " ha")], table={"columns": ["Unité", "Valeur"], "rows": rows})


def parcel(v, on):
    a, b = positive(v, "a", "Côté a"), positive(v, "b", "Côté b ou hauteur")
    if v["shape"] == "rectangle":
        m2 = a * b
    elif v["shape"] == "triangle":
        m2 = a * b / 2
    else:
        m2 = (a + positive(v, "c", "Côté c (base opposée)")) / 2 * b
    return Result(headline=[("Surface", _n(m2, 1) + " m²"), ("En hectares", _n(m2 / 10000, 4) + " ha")])


def mass_volume(v, on):
    dim, factor = MASS_VOLUME[v["unit"]]
    base = positive(v, "value", "Valeur", True) * factor
    rows = [[label, _n(base / MASS_VOLUME[key][1], 4)] for key, label in MASS_VOLUME_LABELS if MASS_VOLUME[key][0] == dim]
    return Result(headline=[("Conversion", dim)], table={"columns": ["Unité", "Valeur"], "rows": rows})


def rule_of_three(v, on):
    a = positive(v, "a", "Première quantité")
    x = v["b"] * v["c"] / a
    return Result(headline=[("Résultat", _n(x, 4))], details=[("Calcul", f"{_n(v['b'], 4)} × {_n(v['c'], 4)} ÷ {_n(a, 4)}")])


def percentage(v, on):
    start = v["start"]
    if start == 0:
        raise CalculatorError("Valeur de départ non nulle attendue.", "start")
    change = (v["end"] - start) / abs(start) * 100
    return Result(headline=[("Variation", f"{'+' if change >= 0 else ''}{_n(change, 2)} %")],
                  details=[("Écart", _n(v["end"] - start, 2)), ("Arrivée en % du départ", _n(v["end"] / start * 100, 2) + " %")])


# ------------------------------------------------------------------ chantiers et matériel

def work_rate(v, on):
    rate = positive(v, "width", "Largeur") * positive(v, "speed", "Vitesse") * positive(v, "efficiency", "Rendement") / 1000
    return Result(headline=[("Débit de chantier", _n(rate, 2) + " ha/h")],
                  details=[("Débit théorique (100 %)", _n(v["width"] * v["speed"] / 10, 2) + " ha/h")])


def work_time(v, on):
    hours = positive(v, "surface", "Surface") / positive(v, "rate", "Débit")
    return Result(headline=[("Temps de chantier", _hours(hours))], details=[("En heures décimales", _n(hours, 2) + " h")])


def fuel_per_ha(v, on):
    per_ha = positive(v, "consumption", "Consommation") / positive(v, "rate", "Débit")
    headline = [("Carburant par hectare", _n(per_ha, 2) + " l/ha")]
    if v["price"] is not None:
        headline.append(("Coût par hectare", _n(per_ha * v["price"], 2) + " €/ha"))
    return Result(headline=headline)


def speed(v, on):
    kmh = positive(v, "distance", "Distance") / positive(v, "seconds", "Temps") * D("3.6")
    return Result(headline=[("Vitesse", _n(kmh, 2) + " km/h")])


# ------------------------------------------------------------------ semis et plantation

def seed_rate(v, on):
    rate = positive(v, "grains", "Grains par m²") * positive(v, "tgw", "PMG") / positive(v, "emergence", "Taux de levée")
    return Result(headline=[("Dose de semis", _n(rate, 1) + " kg/ha")],
                  details=[("Grains à semer par m²", _n(v["grains"] * 100 / v["emergence"], 0))])


def plant_density(v, on):
    density = D(10000) / (positive(v, "row", "Inter-rang") * positive(v, "spacing", "Espacement"))
    return Result(headline=[("Densité", _n(density, 0) + " plants/ha")])


def seed_order(v, on):
    total = positive(v, "rate", "Dose") * positive(v, "surface", "Surface")
    bags = math.ceil(total / positive(v, "bag", "Conditionnement"))
    return Result(headline=[("Quantité totale", _n(total, 1)), ("Conditionnements", str(bags))],
                  details=[("Reste après semis", _n(bags * v["bag"] - total, 1))])


# ------------------------------------------------------------------ fertilisation

def unit_price(v, on):
    price = positive(v, "price", "Prix") / (positive(v, "content", "Teneur") * 10)
    return Result(headline=[("Prix de l'unité", _n(price, 3) + " €/unité")])


def dose_for_target(v, on):
    dose = positive(v, "units", "Unités visées") * 100 / positive(v, "content", "Teneur")
    headline = [("Dose de produit", _n(dose, 1) + " kg/ha")]
    if v["surface"]:
        headline.append(("Quantité totale", _n(dose * v["surface"] / 1000, 3) + " t"))
    return Result(headline=headline)


def units_from_dose(v, on):
    units = positive(v, "dose", "Dose") * positive(v, "content", "Teneur") / 100
    return Result(headline=[("Unités apportées", _n(units, 1) + " u/ha")])


def manure(v, on):
    quantity = positive(v, "quantity", "Quantité épandue")
    rows = [[name, _n(quantity * (v[key] or 0), 1)] for key, name in (("n", "N"), ("p", "P₂O₅"), ("k", "K₂O"))]
    return Result(headline=[("Azote apporté", rows[0][1] + " u/ha")],
                  table={"columns": ["Élément", "Unités par ha"], "rows": rows})


# ------------------------------------------------------------------ pulvérisation

def tank_mix(v, on):
    volume, tank = positive(v, "volume", "Volume de bouillie"), positive(v, "tank", "Volume de cuve")
    product = positive(v, "dose", "Dose de produit") * tank / volume
    return Result(headline=[("Produit par cuve", _n(product, 2)), ("Surface par cuve", _n(tank / volume, 2) + " ha")])


def tanks(v, on):
    needed = positive(v, "volume", "Volume de bouillie") * positive(v, "surface", "Surface")
    count = math.ceil(needed / positive(v, "tank", "Volume de cuve"))
    return Result(headline=[("Nombre de cuves", str(count))], details=[("Bouillie totale", _n(needed, 0) + " l")])


def nozzle(v, on):
    flow = positive(v, "volume", "Volume") * positive(v, "speed", "Vitesse") * positive(v, "spacing", "Écartement") / 600
    return Result(headline=[("Débit par buse", _n(flow, 3) + " l/min")])


# ------------------------------------------------------------------ irrigation et eau

def rainfall(v, on):
    m3 = positive(v, "mm", "Hauteur d'eau", True) * 10
    headline = [("Volume par hectare", _n(m3, 1) + " m³/ha")]
    if v["surface"]:
        headline.append(("Volume total", _n(m3 * v["surface"], 1) + " m³"))
    return Result(headline=headline)


def reel(v, on):
    mm = positive(v, "flow", "Débit") * 1000 / (positive(v, "width", "Largeur arrosée") * positive(v, "speed", "Vitesse"))
    return Result(headline=[("Dose apportée", _n(mm, 1) + " mm")])


def irrigation_time(v, on):
    hours = positive(v, "mm", "Dose") * 10 * positive(v, "surface", "Surface") / positive(v, "flow", "Débit")
    return Result(headline=[("Durée d'irrigation", _hours(hours))], details=[("Volume", _n(v["mm"] * 10 * v["surface"], 0) + " m³")])


# ------------------------------------------------------------------ récolte et stockage

def crop_yield(v, on):
    t_ha = positive(v, "weight", "Poids récolté") / positive(v, "surface", "Surface")
    return Result(headline=[("Rendement", _n(t_ha * 10, 1) + " q/ha")], details=[("En tonnes", _n(t_ha, 2) + " t/ha")])


def storage(v, on):
    if v["shape"] == "cylinder":
        radius = positive(v, "a", "Diamètre") / 2
        volume = D(str(math.pi)) * radius * radius * positive(v, "height", "Hauteur")
    else:
        volume = positive(v, "a", "Longueur") * positive(v, "b", "Largeur") * positive(v, "height", "Hauteur")
    mass = volume * positive(v, "density", "Densité")
    return Result(headline=[("Volume", _n(volume, 1) + " m³"), ("Capacité", _n(mass, 1) + " t")])


def bales(v, on):
    count = math.ceil(positive(v, "need", "Besoin") * 1000 / positive(v, "bale", "Poids d'une balle"))
    return Result(headline=[("Nombre de balles", str(count))])


# ------------------------------------------------------------------ élevage

def forage(v, on):
    need = positive(v, "heads", "Effectif") * positive(v, "intake", "Ration") * positive(v, "days", "Durée") / 1000
    headline = [("Besoin", _n(need, 1) + " t MS")]
    if v["stock"] is not None:
        gap = v["stock"] - need
        headline.append(("Solde du stock", f"{'+' if gap >= 0 else ''}{_n(gap, 1)} t MS"))
    return Result(headline=headline)


def daily_gain(v, on):
    gain = (v["end"] - positive(v, "start", "Poids initial")) * 1000 / positive(v, "days", "Durée")
    return Result(headline=[("Gain moyen quotidien", _n(gain, 0) + " g/j")])


def milk(v, on):
    quantity, density = positive(v, "quantity", "Quantité", True), positive(v, "density", "Densité")
    if v["unit"] == "l":
        return Result(headline=[("En kilogrammes", _n(quantity * density, 2) + " kg")])
    return Result(headline=[("En litres", _n(quantity / density, 2) + " l")])


def calving(v, on):
    days = positive(v, "gestation", "Durée de gestation")
    expected = v["service"] + timedelta(days=int(days))
    return Result(headline=[("Mise bas prévue", f"{expected:%d/%m/%Y}")])


def stocking(v, on):
    ugb = sum((v[f"n{i}"] or 0) * (v[f"c{i}"] or 0) for i in (1, 2, 3))
    rate = ugb / positive(v, "surface", "Surface")
    return Result(headline=[("Chargement", _n(rate, 2) + " UGB/ha")], details=[("UGB totales", _n(ugb, 2))])


# ------------------------------------------------------------------ économie simple

def unit_cost(v, on):
    cost = D(v["costs"]) / 100 / positive(v, "quantity", "Quantité produite")
    unit = v["unit"] or "unité"
    return Result(headline=[("Prix de revient", f"{_n(cost, 2)} € par {unit}")])


def vat(v, on):
    rate = positive(v, "rate", "Taux", True) / 100
    if v["kind"] == "ht":
        ht = v["amount"]
        tax = int((D(ht) * rate).quantize(D(1)))
        ttc = ht + tax
    else:
        ttc = v["amount"]
        ht = int((D(ttc) / (1 + rate)).quantize(D(1)))
        tax = ttc - ht
    return Result(headline=[("HT", euros(ht)), ("TVA", euros(tax)), ("TTC", euros(ttc))])


def margin(v, on):
    price, cost = v["price"], v["cost"]
    if cost <= 0 or price <= 0:
        raise CalculatorError("Prix et coût positifs attendus.", "cost")
    m = price - cost
    return Result(headline=[("Marge", euros(m))],
                  details=[("Taux de marge (sur le coût)", _n(D(m) * 100 / cost, 2) + " %"),
                           ("Taux de marque (sur le prix)", _n(D(m) * 100 / price, 2) + " %")])


def loan(v, on):
    capital, months = v["capital"], int(positive(v, "months", "Durée"))
    if capital <= 0:
        raise CalculatorError("Capital positif attendu.", "capital")
    t = positive(v, "rate", "Taux", True) / 100 / 12
    payment = D(capital) / months if t == 0 else D(capital) * t / (1 - (1 + t) ** -months)
    payment = int(payment.quantize(D(1)))
    rows, remaining, year_interest, year_principal = [], D(capital), D(0), D(0)
    for month in range(1, months + 1):
        interest = remaining * t
        principal = min(D(payment) - interest, remaining)
        remaining -= principal
        year_interest += interest
        year_principal += principal
        if month % 12 == 0 or month == months:
            rows.append([f"Année {math.ceil(month / 12)}", euros(int(year_principal)), euros(int(year_interest)),
                         euros(max(int(remaining), 0))])
            year_interest = year_principal = D(0)
    total = payment * months
    return Result(headline=[("Mensualité", euros(payment)), ("Coût du crédit", euros(total - capital))],
                  table={"columns": ["Période", "Capital remboursé", "Intérêts", "Capital restant"], "rows": rows})


# ------------------------------------------------------------------ déclarations

def I(key, label, kind="number", unit=None, required=True, **kw):  # noqa: E743 — raccourci de déclaration
    return Input(key, label, kind, unit, required, **kw)


TOOLS = [
    Tool(_spec("01", "surfaces", "Conversion de surfaces", "measures", "Hectares, ares, m² et km².",
               [I("value", "Valeur"), I("unit", "Unité", "choice", choices=SURFACE_LABELS, default="ha")],
               {"value": "2.35", "unit": "ha"}, "1 ha = 100 a = 10 000 m² ; 1 km² = 100 ha."), surfaces),
    Tool(_spec("02", "parcelle", "Surface d'une parcelle", "measures",
               "Surface d'un rectangle, d'un triangle ou d'un trapèze à partir de ses côtés.",
               [I("shape", "Forme", "choice", choices=[("rectangle", "Rectangle"), ("triangle", "Triangle"),
                                                       ("trapeze", "Trapèze")], default="rectangle"),
                I("a", "Côté a (base)", unit="m"), I("b", "Côté b ou hauteur", unit="m"),
                I("c", "Côté c (base opposée du trapèze)", unit="m", required=False)],
               {"shape": "trapeze", "a": "210", "b": "95", "c": "180"},
               "Rectangle : a × b ; triangle : base × hauteur ÷ 2 ; trapèze : (a + c) ÷ 2 × hauteur. Une parcelle "
               "irrégulière se découpe en formes simples ; la surface cadastrale ou PAC fait foi."), parcel),
    Tool(_spec("03", "masses-volumes", "Conversion de masses et de volumes", "measures", "Tonnes, quintaux, kg ; m³, hl, litres.",
               [I("value", "Valeur"), I("unit", "Unité", "choice", choices=MASS_VOLUME_LABELS, default="t")],
               {"value": "12.6", "unit": "t"}, "1 t = 10 q = 1 000 kg ; 1 m³ = 10 hl = 1 000 l. Masse et volume ne se "
                                                "convertissent pas l'un dans l'autre sans densité."), mass_volume),
    Tool(_spec("04", "regle-de-trois", "Règle de trois", "measures", "Si a donne b, combien donne c ?",
               [I("a", "Si (a)"), I("b", "donne (b)"), I("c", "alors (c)")], {"a": "12", "b": "540", "c": "17"},
               "x = b × c ÷ a (proportionnalité)."), rule_of_three),
    Tool(_spec("05", "pourcentage", "Pourcentage et variation", "measures", "Variation en % entre deux valeurs.",
               [I("start", "Valeur de départ"), I("end", "Valeur d'arrivée")], {"start": "185", "end": "212"},
               "Variation = (arrivée − départ) ÷ |départ| × 100."), percentage),
    Tool(_spec("06", "debit-chantier", "Débit de chantier", "equipment", "Hectares travaillés par heure.",
               [I("width", "Largeur de travail", unit="m"), I("speed", "Vitesse", unit="km/h"),
                I("efficiency", "Rendement du chantier", unit="%", help="Part du temps réellement travaillée (demi-tours, remplissages)")],
               {"width": "6", "speed": "8", "efficiency": "75"},
               "Débit (ha/h) = largeur (m) × vitesse (km/h) × rendement (%) ÷ 1 000 ; à 100 % : largeur × vitesse ÷ 10."), work_rate),
    Tool(_spec("07", "temps-chantier", "Temps de chantier", "equipment", "Durée d'un chantier selon la surface et le débit.",
               [I("surface", "Surface", unit="ha"), I("rate", "Débit de chantier", unit="ha/h")], {"surface": "48", "rate": "3.6"},
               "Temps = surface ÷ débit (hors déplacements)."), work_time),
    Tool(_spec("08", "carburant-ha", "Carburant par hectare", "equipment", "Consommation et coût de carburant à l'hectare.",
               [I("consumption", "Consommation", unit="l/h"), I("rate", "Débit de chantier", unit="ha/h"),
                I("price", "Prix du carburant", unit="€/l", required=False, help="Prix saisi : notez sa date et sa source")],
               {"consumption": "16", "rate": "2.4", "price": "1.15"}, "Carburant (l/ha) = consommation (l/h) ÷ débit (ha/h)."), fuel_per_ha),
    Tool(_spec("09", "vitesse", "Vitesse d'avancement", "equipment", "Vitesse réelle à partir d'une distance chronométrée.",
               [I("distance", "Distance parcourue", unit="m"), I("seconds", "Temps", unit="s")], {"distance": "100", "seconds": "45"},
               "Vitesse (km/h) = distance (m) ÷ temps (s) × 3,6."), speed),
    Tool(_spec("10", "dose-semis", "Dose de semis", "sowing", "Kilogrammes de semences par hectare.",
               [I("grains", "Objectif de grains par m²"), I("tgw", "Poids de mille grains (PMG)", unit="g"),
                I("emergence", "Taux de levée attendu", unit="%")], {"grains": "300", "tgw": "45", "emergence": "90"},
               "Dose (kg/ha) = grains/m² × PMG (g) ÷ taux de levée (%) ; le PMG figure sur l'étiquette du lot."), seed_rate),
    Tool(_spec("11", "densite-plantation", "Densité de plantation", "sowing", "Nombre de plants par hectare.",
               [I("row", "Inter-rang", unit="m"), I("spacing", "Espacement sur le rang", unit="m")],
               {"row": "2.2", "spacing": "1"}, "Plants/ha = 10 000 ÷ (inter-rang × espacement)."), plant_density),
    Tool(_spec("12", "semences-commande", "Semences à commander", "sowing", "Quantité et nombre de doses ou de sacs.",
               [I("rate", "Dose par hectare", help="kg/ha ou doses/ha"), I("surface", "Surface", unit="ha"),
                I("bag", "Conditionnement", help="kg par sac ou graines par dose, même unité que la dose")],
               {"rate": "150", "surface": "24", "bag": "500"}, "Total = dose × surface ; conditionnements = total ÷ "
                                                               "contenance, arrondi au-dessus."), seed_order),
    Tool(_spec("13", "prix-unite", "Prix de l'unité fertilisante", "fertilization", "Coût d'une unité d'azote, de phosphore ou de potasse.",
               [I("price", "Prix de l'engrais", unit="€/t"), I("content", "Teneur", unit="%")], {"price": "420", "content": "27"},
               "€/unité = prix (€/t) ÷ (teneur (%) × 10) ; une tonne à 27 % apporte 270 unités."), unit_price),
    Tool(_spec("14", "dose-apport", "Dose pour un apport visé", "fertilization", "Kilogrammes de produit pour apporter des unités.",
               [I("units", "Unités visées", unit="u/ha"), I("content", "Teneur", unit="%"),
                I("surface", "Surface", unit="ha", required=False)], {"units": "60", "content": "27", "surface": "18"},
               "Dose (kg/ha) = unités × 100 ÷ teneur (%)."), dose_for_target),
    Tool(_spec("15", "unites-dose", "Unités apportées par une dose", "fertilization", "Unités par hectare d'une dose de produit.",
               [I("dose", "Dose de produit", unit="kg/ha"), I("content", "Teneur", unit="%")], {"dose": "200", "content": "33.5"},
               "Unités = dose (kg/ha) × teneur (%) ÷ 100."), units_from_dose),
    Tool(_spec("16", "effluent", "Apport d'un effluent", "fertilization", "Unités N, P, K apportées par un fumier ou un lisier.",
               [I("quantity", "Quantité épandue", unit="t ou m³/ha"), I("n", "Teneur en azote", unit="kg/t", required=False),
                I("p", "Teneur en P₂O₅", unit="kg/t", required=False), I("k", "Teneur en K₂O", unit="kg/t", required=False)],
               {"quantity": "25", "n": "5.5", "p": "2.3", "k": "8"},
               "Unités = quantité × teneur ; teneurs de l'analyse de l'effluent ou d'une référence saisie. Seule une "
               "partie de l'azote est disponible la première année."), manure),
    Tool(_spec("17", "cuve", "Préparation de la cuve", "spraying", "Quantité de produit par cuve et surface traitée.",
               [I("dose", "Dose de produit", help="l/ha ou kg/ha"), I("volume", "Volume de bouillie", unit="l/ha"),
                I("tank", "Volume de cuve", unit="l")], {"dose": "1.2", "volume": "150", "tank": "3000"},
               "Produit par cuve = dose × cuve ÷ volume par hectare ; respecter l'étiquette (dose homologuée)."), tank_mix),
    Tool(_spec("18", "nombre-cuves", "Nombre de cuves", "spraying", "Cuves nécessaires pour une surface.",
               [I("volume", "Volume de bouillie", unit="l/ha"), I("surface", "Surface", unit="ha"), I("tank", "Volume de cuve", unit="l")],
               {"volume": "150", "surface": "64", "tank": "3000"}, "Cuves = volume/ha × surface ÷ cuve, arrondi au-dessus."), tanks),
    Tool(_spec("19", "debit-buse", "Débit de buse", "spraying", "Débit par buse pour un volume et une vitesse.",
               [I("volume", "Volume de bouillie", unit="l/ha"), I("speed", "Vitesse", unit="km/h"),
                I("spacing", "Écartement des buses", unit="m")], {"volume": "150", "speed": "8", "spacing": "0.5"},
               "Débit (l/min) = volume (l/ha) × vitesse (km/h) × écartement (m) ÷ 600."), nozzle),
    Tool(_spec("20", "pluviometrie", "Pluviométrie", "irrigation", "Millimètres d'eau en m³ par hectare.",
               [I("mm", "Hauteur d'eau", unit="mm"), I("surface", "Surface", unit="ha", required=False)], {"mm": "25", "surface": "12"},
               "1 mm = 1 l/m² = 10 m³/ha."), rainfall),
    Tool(_spec("21", "enrouleur", "Dose d'un enrouleur", "irrigation", "Millimètres apportés par un enrouleur.",
               [I("flow", "Débit", unit="m³/h"), I("width", "Largeur arrosée", unit="m"), I("speed", "Vitesse d'avancement", unit="m/h")],
               {"flow": "40", "width": "72", "speed": "25"}, "Dose (mm) = débit (m³/h) × 1 000 ÷ (largeur (m) × vitesse (m/h))."), reel),
    Tool(_spec("22", "duree-irrigation", "Durée d'irrigation", "irrigation", "Temps pour apporter une dose sur une surface.",
               [I("mm", "Dose visée", unit="mm"), I("surface", "Surface", unit="ha"), I("flow", "Débit", unit="m³/h")],
               {"mm": "30", "surface": "4", "flow": "60"}, "Durée (h) = dose (mm) × 10 × surface (ha) ÷ débit (m³/h)."), irrigation_time),
    Tool(_spec("23", "rendement", "Rendement", "harvest", "Rendement en quintaux par hectare.",
               [I("weight", "Poids récolté", unit="t"), I("surface", "Surface", unit="ha")], {"weight": "182.4", "surface": "24"},
               "Rendement (q/ha) = poids (t) × 10 ÷ surface (ha) ; poids aux normes : voir la réfaction humidité."), crop_yield),
    Tool(_spec("24", "capacite-stockage", "Capacité d'un silo ou d'un tas", "harvest", "Volume et masse stockable.",
               [I("shape", "Forme", "choice", choices=[("cylinder", "Cylindre (silo)"), ("box", "Parallélépipède (cellule, tas)")],
                  default="cylinder"),
                I("a", "Diamètre ou longueur", unit="m"), I("b", "Largeur", unit="m", required=False), I("height", "Hauteur", unit="m"),
                I("density", "Densité du produit", unit="t/m³", help="Saisie : par exemple poids spécifique du grain")],
               {"shape": "cylinder", "a": "8", "b": "", "height": "12", "density": "0.75"},
               "Cylindre : π × (diamètre ÷ 2)² × hauteur ; parallélépipède : longueur × largeur × hauteur ; masse = volume "
               "× densité. Ne tient pas compte du cône ni du tassement."), storage),
    Tool(_spec("25", "balles", "Besoin en balles", "harvest", "Nombre de balles pour un besoin en fourrage.",
               [I("need", "Besoin", unit="t"), I("bale", "Poids d'une balle", unit="kg")], {"need": "95", "bale": "320"},
               "Balles = besoin (t) × 1 000 ÷ poids d'une balle (kg), arrondi au-dessus."), bales),
    Tool(_spec("26", "besoin-fourrage", "Besoin en fourrage", "livestock", "Matière sèche nécessaire sur une période.",
               [I("heads", "Effectif", unit="têtes"), I("intake", "Ration", unit="kg MS/jour"), I("days", "Durée", unit="jours"),
                I("stock", "Stock disponible", unit="t MS", required=False)],
               {"heads": "60", "intake": "15", "days": "150", "stock": "120"},
               "Besoin (t MS) = effectif × ration × jours ÷ 1 000 ; prévoir les pertes au stockage et à l'auge."), forage),
    Tool(_spec("27", "gmq", "Gain moyen quotidien", "livestock", "Croissance en grammes par jour.",
               [I("start", "Poids initial", unit="kg"), I("end", "Poids final", unit="kg"), I("days", "Durée", unit="jours")],
               {"start": "280", "end": "395", "days": "120"}, "GMQ (g/j) = (poids final − poids initial) × 1 000 ÷ jours."), daily_gain),
    Tool(_spec("28", "lait", "Conversion du lait", "livestock", "Litres et kilogrammes de lait.",
               [I("quantity", "Quantité"), I("unit", "Unité saisie", "choice", choices=[("l", "litres"), ("kg", "kg")], default="l"),
                I("density", "Densité", unit="kg/l", help="Valeur de votre laiterie (saisie)")],
               {"quantity": "1000", "unit": "l", "density": "1.032"}, "kg = litres × densité."), milk),
    Tool(_spec("29", "mise-bas", "Date prévisionnelle de mise bas", "livestock", "Date attendue d'après la saillie.",
               [I("service", "Date de saillie ou d'insémination", "date"), I("gestation", "Durée de gestation", unit="jours",
                                                                                help="Selon l'espèce et la race (saisie)")],
               {"service": "2026-11-10", "gestation": "283"}, "Date = saillie + durée de gestation saisie."), calving),
    Tool(_spec("30", "chargement", "Chargement", "livestock", "UGB par hectare de surface fourragère.",
               [I("n1", "Effectif 1"), I("c1", "Coefficient UGB 1"), I("n2", "Effectif 2", required=False),
                I("c2", "Coefficient UGB 2", required=False), I("n3", "Effectif 3", required=False),
                I("c3", "Coefficient UGB 3", required=False), I("surface", "Surface fourragère", unit="ha")],
               {"n1": "55", "c1": "1", "n2": "30", "c2": "0.6", "n3": "", "c3": "", "surface": "70"},
               "Chargement = Σ (effectif × coefficient) ÷ surface ; coefficients saisis (les coefficients PAC "
               "officiels viendront avec la calculette des aides)."), stocking),
    Tool(_spec("31", "prix-revient", "Prix de revient unitaire", "economics", "Coût par unité produite.",
               [I("costs", "Charges", "money", "€"), I("quantity", "Quantité produite"), I("unit", "Unité", "text", required=False)],
               {"costs": "52000", "quantity": "410", "unit": "tonne"}, "Prix de revient = charges ÷ quantité produite."), unit_cost),
    Tool(_spec("32", "tva", "HT, TVA et TTC", "economics", "Passer du HT au TTC et inversement.",
               [I("amount", "Montant", "money", "€"), I("kind", "Montant saisi", "choice", choices=[("ht", "HT"), ("ttc", "TTC")],
                                                         default="ht"), I("rate", "Taux de TVA", unit="%")],
               {"amount": "1250", "kind": "ht", "rate": "5.5"}, "TTC = HT × (1 + taux) ; HT = TTC ÷ (1 + taux), au centime."), vat),
    Tool(_spec("33", "marge", "Marge et taux de marque", "economics", "Marge d'une vente, taux de marge et taux de marque.",
               [I("price", "Prix de vente HT", "money", "€"), I("cost", "Coût de revient HT", "money", "€")],
               {"price": "18.50", "cost": "11.20"}, "Marge = prix − coût ; taux de marge = marge ÷ coût ; taux de marque = "
                                                     "marge ÷ prix."), margin),
    Tool(_spec("34", "emprunt", "Mensualité d'un emprunt", "economics", "Mensualité constante et tableau d'amortissement.",
               [I("capital", "Capital emprunté", "money", "€"), I("rate", "Taux annuel", unit="%"), I("months", "Durée", unit="mois")],
               {"capital": "100000", "rate": "3", "months": "120"},
               "Mensualité = capital × t ÷ (1 − (1 + t)^−n), t = taux annuel ÷ 12, n = mois ; hors assurance et frais de "
               "dossier ; le tableau de la banque fait foi."), loan),
]
