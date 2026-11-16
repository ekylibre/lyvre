"""Calculettes du groupe C (lot AG12.d, claudedocs/design_calculettes_agricoles.md § 10) : 02 validité du Certiphyto,
20 mise à jour du DUER, 10 exonération TO-DE, 16 aides PAC. Paramètres sourcés et validés (`data/regulatory/tools.json`)."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.services import reg_params
from app.services.calculators import CalculatorError, Input, Result, Spec, Tool, euros, number, positive

D = Decimal


def _plus_years(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year + years)
    except ValueError:                                   # 29 février
        return day.replace(year=day.year + years, day=28)


def _minus_months(day: date, months: int) -> date:
    month = day.month - 1 - months
    year, month = day.year + month // 12, month % 12 + 1
    return date(year, month, min(day.day, 28))


# ------------------------------------------------------------------ 02 Certiphyto

CERTIPHYTO_CATEGORIES = [("dea", "Décideur en exploitation agricole (DEA)"),
                         ("densa", "Décideur en entreprise non soumise à agrément (DENSA)"),
                         ("other", "Autre catégorie (opérateur, conseil, vente…)")]


def certiphyto(v, on):
    expiry = v["expiry"]
    extensions = reg_params.value("phyto.certiphyto.extensions", on)
    window = reg_params.value("phyto.certiphyto.renewal_window_months", on)
    years = 0
    if v["category"] in extensions["categories"]:
        years = next((p["years"] for p in extensions["periods"]
                      if date.fromisoformat(p["from"]) <= expiry <= date.fromisoformat(p["to"])), 0)
    end = _plus_years(expiry, years) - timedelta(days=1) if years else expiry
    details = [("Échéance indiquée sur le certificat", f"{expiry:%d/%m/%Y}")]
    if years:
        details.append(("Prorogation automatique", f"{years} an{'s' if years > 1 else ''}"))
    renew_from = _minus_months(end, window)
    today = date.today()
    warnings = []
    if end < today:
        warnings.append("Certificat expiré : achat et utilisation de produits phytopharmaceutiques interdits jusqu'au renouvellement.")
    elif renew_from <= today:
        warnings.append("Dans la fenêtre de renouvellement : lancez la démarche (formation, test ou diplôme de moins de 5 ans).")
    return Result(headline=[("Valide jusqu'au", f"{end:%d/%m/%Y}"), ("Renouveler à partir du", f"{renew_from:%d/%m/%Y}")],
                  details=details, warnings=warnings)


# ------------------------------------------------------------------ 20 DUER

def duer(v, on):
    threshold = reg_params.value("labour.duer.annual_threshold", on)
    staff = v["staff"]
    if staff < 0:
        raise CalculatorError("Effectif positif ou nul attendu.", "staff")
    always = "À mettre à jour aussi à tout aménagement important (santé, sécurité, conditions de travail) et à toute " \
             "information nouvelle sur un risque."
    if staff < threshold:
        return Result(headline=[("Mise à jour annuelle", "non obligatoire")],
                      details=[("Effectif", str(staff)), ("Seuil de la mise à jour annuelle", f"{threshold} salariés")],
                      warnings=[always])
    due = _plus_years(v["last_update"], 1)
    warnings = [always]
    if due < date.today():
        warnings.insert(0, f"Mise à jour en retard depuis le {due:%d/%m/%Y}.")
    return Result(headline=[("Prochaine mise à jour au plus tard", f"{due:%d/%m/%Y}")],
                  details=[("Effectif", str(staff)), ("Dernière mise à jour", f"{v['last_update']:%d/%m/%Y}")],
                  warnings=warnings)


# ------------------------------------------------------------------ 10 TO-DE

def tode(v, on):
    pay, smic = positive(v, "pay", "Rémunération mensuelle brute"), positive(v, "smic", "SMIC mensuel")
    c = positive(v, "rate", "Taux des cotisations patronales exonérées", True) / 100
    full = D(reg_params.value("msa.tode.full_ceiling_smic_bp", on)) / 10000
    zero = D(reg_params.value("msa.tode.zero_ceiling_smic_bp", on)) / 10000
    divisor = D(reg_params.value("msa.tode.formula_divisor_bp", on)) / 10000
    ratio = D(pay) / D(smic)
    if ratio <= full:
        rate, zone = c, "exonération totale"
    elif ratio >= zero:
        rate, zone = D(0), "pas d'exonération"
    else:
        rate = min(c, max(D(0), full * c / divisor * (zero * D(smic) / D(pay) - 1)))
        zone = "exonération dégressive"
    amount = int((D(pay) * rate).quantize(D(1)))
    return Result(headline=[("Exonération du mois", euros(amount)), ("Taux d'exonération", f"{number(rate * 100, 3)} %")],
                  details=[("Rémunération / SMIC", f"{number(ratio, 3)} SMIC"), ("Zone", zone),
                           ("Cotisations patronales concernées", euros(int((D(pay) * c).quantize(D(1)))))])


# ------------------------------------------------------------------ 16 aides PAC

ECOREGIME = [("none", "Pas d'écorégime"), ("base", "Niveau de base"), ("higher", "Niveau supérieur"),
             ("organic", "Agriculture biologique")]


def pac(v, on):
    p = lambda key: reg_params.value(key, on)  # noqa: E731
    rows = []
    if v["dpb_value"]:
        rows.append(("Paiement de base (DPB activés)", v["dpb_value"]))
    hectares = v["hectares"] or D(0)
    if hectares:
        redistributive_ha = min(hectares, D(p("pac.redistributive.max_ha")))
        rows.append((f"Aide redistributive ({number(redistributive_ha, 2)} ha)",
                     int((redistributive_ha * p("pac.redistributive.amount_cents")).quantize(D(1)))))
    if v["ecoregime"] != "none" and hectares:
        unit = p(f"pac.ecoregime.{v['ecoregime']}_cents")
        rows.append(("Écorégime", int((hectares * unit).quantize(D(1)))))
        if v["hedges"] == "yes" and v["ecoregime"] in ("base", "higher"):
            rows.append(("Bonus haies", int((hectares * p("pac.ecoregime.hedges_bonus_cents")).quantize(D(1)))))
    if v["young_farmer"] == "yes":
        rows.append(("Aide jeune agriculteur", p("pac.young_farmer.amount_cents")))
    if v["bovines"]:
        unit = p("pac.bovine.higher_cents") if v["bovine_level"] == "higher" else p("pac.bovine.base_cents")
        rows.append(("Aide bovine (UGB de plus de 16 mois)", int((v["bovines"] * unit).quantize(D(1)))))
    if v["ewes"]:
        ewes = int(v["ewes"])
        bonus = min(ewes, p("pac.ovine.bonus_heads")) * p("pac.ovine.bonus_cents")
        rows.append(("Aide ovine", ewes * p("pac.ovine.amount_cents") + bonus))
    if v["goats"]:
        rows.append(("Aide caprine", int(v["goats"]) * p("pac.caprine.amount_cents")))
    if not rows:
        raise CalculatorError("Renseignez au moins une aide (DPB, hectares, animaux).", "hectares")
    total = sum(amount for _, amount in rows)
    return Result(headline=[("Total estimé", euros(total))], details=[(label, euros(amount)) for label, amount in rows],
                  warnings=["Montants provisoires de la campagne : le paiement fait foi (TéléPAC). Non comptés : "
                            "coefficient stabilisateur du DPB, transparence GAEC, ICHN, aides couplées végétales, "
                            "réductions et pénalités."],
                  actions=[("Aides et subventions", "/aids/")])


def I(key, label, kind="number", unit=None, required=True, **kw):  # noqa: E743
    return Input(key, label, kind, unit, required, **kw)


YES_NO = [("no", "Non"), ("yes", "Oui")]

TOOLS = [
    Tool(Spec(code="certiphyto", number="02", title="Validité du Certiphyto", category="regulatory",
              summary="Date de fin de validité d'un certificat individuel phytopharmaceutique, prorogations comprises, "
                      "et date conseillée de renouvellement.",
              inputs=[I("expiry", "Date d'échéance indiquée sur le certificat", "date"),
                      I("category", "Catégorie", "choice", choices=CERTIPHYTO_CATEGORIES, default="dea")],
              example={"expiry": "2024-10-11", "category": "dea"},
              method="Un Certiphyto vaut 5 ans. Les certificats DEA et DENSA arrivant à échéance entre le 10/04/2024 et "
                     "le 01/05/2026 sont prorogés automatiquement de 1 à 3 ans selon leur date d'échéance (décrets de "
                     "2024 et 2025). Le renouvellement se fait de préférence dans les 12 mois avant la fin. Limites : un "
                     "projet de décret non publié n'est pas pris en compte ; la décision de l'administration fait foi.",
              params=("phyto.certiphyto.validity_years", "phyto.certiphyto.renewal_window_months",
                      "phyto.certiphyto.extensions")), certiphyto),
    Tool(Spec(code="duer", number="20", title="Mise à jour du DUER", category="regulatory",
              summary="Échéance de mise à jour du document unique d'évaluation des risques professionnels.",
              inputs=[I("staff", "Effectif salarié", "integer"), I("last_update", "Date de la dernière mise à jour", "date")],
              example={"staff": "12", "last_update": "2025-11-15"},
              method="Mise à jour au moins chaque année à partir de 11 salariés ; dans tous les cas, lors de tout "
                     "aménagement important modifiant les conditions de santé, de sécurité ou de travail, et de toute "
                     "information nouvelle sur un risque (Code du travail art. R4121-2). Limites : l'effectif se calcule "
                     "selon les règles du Code de la sécurité sociale ; le DUER se conserve 40 ans dans ses versions.",
              params=("labour.duer.annual_threshold",)), duer),
    Tool(Spec(code="tode", number="10", title="Exonération TO-DE", category="social",
              summary="Exonération de cotisations patronales pour un travailleur occasionnel agricole, sur un mois.",
              inputs=[I("pay", "Rémunération mensuelle brute", "money", "€", help="Hors heures supplémentaires et complémentaires"),
                      I("smic", "SMIC mensuel du salarié", "money", "€",
                        help="SMIC horaire × heures rémunérées du mois, comme pour la réduction générale (CSS D241-8)"),
                      I("rate", "Taux des cotisations patronales exonérées", unit="%",
                        help="Somme des taux concernés (art. L741-16 I), d'après votre caisse")],
              example={"pay": "2200", "smic": "1823.03", "rate": "28"},
              method="Jusqu'à 1,25 SMIC : exonération totale des cotisations concernées. Au-delà : taux = 1,25 × C ÷ 0,35 "
                     "× (1,6 × SMIC mensuel ÷ rémunération − 1), nul à partir de 1,6 SMIC (CRPM art. D741-60, version du "
                     "15/06/2025). Limites : conditions d'éligibilité (contrat saisonnier, durée maximale par salarié, "
                     "employeurs concernés) à vérifier ; le taux C se lit sur les bordereaux de la caisse.",
              params=("msa.tode.full_ceiling_smic_bp", "msa.tode.zero_ceiling_smic_bp", "msa.tode.formula_divisor_bp")),
         tode),
    Tool(Spec(code="aides-pac", number="16", title="Aides PAC de la campagne", category="fiscal",
              summary="Estimation des aides découplées et couplées animales de la campagne aux montants de l'arrêté.",
              inputs=[I("campaign", "Campagne", "integer", default="2026"),
                      I("dpb_value", "Valeur de vos DPB activés", "money", "€", required=False, help="Montant TéléPAC"),
                      I("hectares", "Hectares admissibles", unit="ha", required=False),
                      I("ecoregime", "Écorégime", "choice", choices=ECOREGIME, default="base"),
                      I("hedges", "Bonus haies", "choice", choices=YES_NO, default="no"),
                      I("young_farmer", "Jeune agriculteur (aide complémentaire)", "choice", choices=YES_NO, default="no"),
                      I("bovines", "UGB bovines de plus de 16 mois", required=False),
                      I("bovine_level", "Montant bovin", "choice", choices=[("base", "Base"), ("higher", "Supérieur")],
                        default="base"),
                      I("ewes", "Brebis primables", required=False), I("goats", "Chèvres primables", required=False)],
              example={"campaign": "2026", "dpb_value": "11500", "hectares": "95", "ecoregime": "base", "hedges": "yes",
                       "young_farmer": "no", "bovines": "40", "bovine_level": "base", "ewes": "", "goats": ""},
              method="Aide redistributive sur les premiers hectares admissibles, écorégime selon le niveau (bonus haies en "
                     "plus), forfait jeune agriculteur, aides animales par UGB, brebis (majoration sur les premières) et "
                     "chèvres, aux montants unitaires de l'arrêté de la campagne ; DPB : montant saisi. Limites : montants "
                     "provisoires, ni coefficient stabilisateur, ni transparence GAEC, ni ICHN.",
              params=("pac.redistributive.amount_cents", "pac.redistributive.max_ha", "pac.ecoregime.base_cents",
                      "pac.ecoregime.higher_cents", "pac.ecoregime.organic_cents", "pac.ecoregime.hedges_bonus_cents",
                      "pac.young_farmer.amount_cents", "pac.bovine.higher_cents", "pac.ovine.bonus_cents",
                      "pac.ovine.bonus_heads", "pac.bovine.base_cents", "pac.ovine.amount_cents",
                      "pac.caprine.amount_cents")),
         pac, on_date=lambda v: date(v["campaign"], 12, 31)),
]
