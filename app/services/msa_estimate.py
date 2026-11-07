"""Estimation indicative des cotisations MSA d'un exploitant (lot AG7.e, claudedocs/design_msa.md § 7, AGD24 Q-M6).

Barème NSA 2026 de la MSA en paramètres datés (`data/regulatory/msa.json`), appliqué à l'assiette retenue pour
l'année de cotisation (AG7.b) : chef d'exploitation domicilié en France, à titre exclusif ou principal, ou secondaire.
Taux progressifs (AMEXA, prestations familiales) lus sur cette assiette retenue, et même barème AMEXA pour le chef à
titre secondaire : barème 2026 de la MSA, vérifié au lot CG3.c.
Lignes : AMEXA (taux progressif), invalidité, IJ AMEXA, retraite de base plafonnée et déplafonnée, RCO et RCO
complémentaire, ATEXA (catégorie de risques), prestations familiales, CSG / CRDS, formation (VIVEA), FMSE.
Assiettes minimales en SMIC ou en % du PASS. **Indicatif** : ni exonération JA, ni cotisations complémentaires par
production (FMSE, InterApi, Val'hor), ni membres de la famille ; le montant appelé par la caisse fait foi.
"""
from __future__ import annotations

from datetime import date

from app.services import reg_params

ATEXA_CATEGORIES = ("A", "B", "C", "D", "E")


def _params(year: int) -> tuple[dict, str | None]:
    """Paramètres du barème de l'année de cotisation, sinon ceux du dernier barème connu."""
    keys = ("msa.pass_cents", "msa.smic_hour_cents", "msa.amexa.rates", "msa.amexa.top_rate_bp", "msa.invalidity.rate_bp",
            "msa.invalidity.min_pass_bp", "msa.ij.amount_cents", "msa.pension.capped_rate_bp",
            "msa.pension.capped_secondary_rate_bp", "msa.pension.uncapped_rate_bp", "msa.pension.min_smic",
            "msa.pfa.rate_bp", "msa.atexa.amounts", "msa.rco.rate_bp", "msa.rco.min_smic", "msa.rco_extra.rates",
            "msa.csg.deductible_bp", "msa.csg.non_deductible_bp", "msa.crds_bp", "msa.vivea.rate_bp",
            "msa.vivea.min_pass_bp", "msa.vivea.max_pass_bp", "msa.fmse.amount_cents")
    on = date(year, 1, 1)
    values = {k: reg_params.value(k, on, None) for k in keys}
    if all(v is not None for v in values.values()):
        return values, None
    latest = max((p.valid_from for p in reg_params.history("msa.amexa.rates")), default=None)
    if latest is None:
        return {}, "Barème MSA non paramétré."
    values = {k: reg_params.value(k, latest, None) for k in keys}
    if any(v is None for v in values.values()):
        return {}, "Barème MSA incomplet."
    return values, f"Barème {year} non publié : barème {latest.year} appliqué."


def _interpolate(base: int, pass_cents: int, points: list[tuple[int, int]]) -> float:
    """Taux (pb) interpolé linéairement entre des points (assiette en % du PASS en pb, taux en pb)."""
    ratio = base * 10000 / pass_cents
    if ratio <= points[0][0]:
        return float(points[0][1])
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if ratio <= x1:
            return y0 + (y1 - y0) * (ratio - x0) / (x1 - x0)
    return float(points[-1][1])


def _amexa(base: int, p: dict) -> tuple[int, str]:
    pass_cents = p["msa.pass_cents"]
    t1, t2, t3, t4, t5 = p["msa.amexa.rates"]
    if base <= 0:
        return 0, "assiette nulle"
    if base * 10000 >= 30000 * pass_cents:
        top = 3 * pass_cents
        amount = top * t5 / 10000 + (base - top) * p["msa.amexa.top_rate_bp"] / 10000
        return round(amount), f"{t5 / 100:.2f} % jusqu'à 300 % du PASS, {p['msa.amexa.top_rate_bp'] / 100:.2f} % au-delà"
    rate = _interpolate(base, pass_cents, [(2000, 0), (4000, t1), (6000, t2), (11000, t3), (20000, t4), (30000, t5)])
    return round(base * rate / 10000), f"taux progressif {rate / 100:.3f} %"


def _rco_extra(base: int, p: dict) -> tuple[int, str]:
    if base <= 0:
        return 0, "assiette nulle"
    t1, t2, t3, t4 = p["msa.rco_extra.rates"]
    rate = _interpolate(base, p["msa.pass_cents"], [(0, 0), (4000, t1), (6000, t2), (10000, t3), (20000, t4)])
    return round(base * rate / 10000), f"taux progressif {rate / 100:.3f} %"


def _pfa(base: int, p: dict) -> tuple[int, str]:
    if base <= 0:
        return 0, "assiette nulle"
    rate = _interpolate(base, p["msa.pass_cents"], [(11000, 0), (14000, p["msa.pfa.rate_bp"])])
    return round(base * rate / 10000), f"taux {rate / 100:.3f} % (nul jusqu'à 110 % du PASS)"


def _fmt(cents: int) -> str:
    return f"{cents / 100:,.0f} €".replace(",", " ")


def estimate(base: int | None, year: int, status: str = "principal", atexa_category: str | None = None) -> dict:
    """Cotisations et contributions estimées de l'année `year` sur l'assiette `base` (centimes)."""
    if status not in ("principal", "secondary"):
        return {"available": False, "reason": "Estimation réservée aux chefs d'exploitation (statut du collaborateur non couvert)."}
    if base is None:
        return {"available": False, "reason": f"Assiette des cotisations {year} inconnue : historique des assiettes à compléter."}
    p, warning = _params(year)
    if not p:
        return {"available": False, "reason": warning}
    pass_cents, smic = p["msa.pass_cents"], p["msa.smic_hour_cents"]
    positive = max(base, 0)
    lines = []

    def add(key, label, amount, detail, group, deductible=True):
        lines.append({"key": key, "label": label, "amount_cents": int(amount), "detail": detail, "group": group,
                      "deductible": deductible})

    amexa, detail = _amexa(positive, p)
    add("amexa", "Assurance maladie (AMEXA)", amexa, detail, "cotisations")
    inv_base = max(positive, round(pass_cents * p["msa.invalidity.min_pass_bp"] / 10000))
    if status == "principal":
        add("invalidity", "Invalidité", round(inv_base * p["msa.invalidity.rate_bp"] / 10000),
            f"{p['msa.invalidity.rate_bp'] / 100:.2f} % de {_fmt(inv_base)} (minimum 11,5 % du PASS)", "cotisations")
        add("ij", "Indemnités journalières AMEXA", p["msa.ij.amount_cents"], "forfait", "cotisations")
    pension_min = p["msa.pension.min_smic"] * smic
    capped_rate = p["msa.pension.capped_rate_bp"] if status == "principal" else p["msa.pension.capped_secondary_rate_bp"]
    capped_base = min(max(positive, pension_min), pass_cents)
    add("pension_capped", "Retraite de base plafonnée (AVI / AVA)", round(capped_base * capped_rate / 10000),
        f"{capped_rate / 100:.2f} % de {_fmt(capped_base)} (entre 600 SMIC et le PASS)", "cotisations")
    uncapped_base = max(positive, pension_min)
    add("pension_uncapped", "Retraite de base déplafonnée", round(uncapped_base * p["msa.pension.uncapped_rate_bp"] / 10000),
        f"{p['msa.pension.uncapped_rate_bp'] / 100:.2f} % de {_fmt(uncapped_base)}", "cotisations")
    rco_base = max(positive, p["msa.rco.min_smic"] * smic)
    add("rco", "Retraite complémentaire (RCO)", round(rco_base * p["msa.rco.rate_bp"] / 10000),
        f"{p['msa.rco.rate_bp'] / 100:.2f} % de {_fmt(rco_base)} (minimum 1 820 SMIC)", "cotisations")
    extra, detail = _rco_extra(positive, p)
    add("rco_extra", "RCO complémentaire", extra, detail, "cotisations")
    pfa, detail = _pfa(positive, p)
    add("pfa", "Prestations familiales", pfa, detail, "cotisations")
    amounts = p["msa.atexa.amounts"].get(status) or []
    if atexa_category in ATEXA_CATEGORIES and len(amounts) == 5:
        add("atexa", f"Accidents du travail (ATEXA, catégorie {atexa_category})",
            amounts[ATEXA_CATEGORIES.index(atexa_category)], "forfait", "cotisations")
    csg_d = round(positive * p["msa.csg.deductible_bp"] / 10000)
    csg_n = round(positive * p["msa.csg.non_deductible_bp"] / 10000)
    crds = round(positive * p["msa.crds_bp"] / 10000)
    add("csg_deductible", "CSG déductible", csg_d, f"{p['msa.csg.deductible_bp'] / 100:.1f} %", "contributions")
    add("csg_non_deductible", "CSG non déductible", csg_n, f"{p['msa.csg.non_deductible_bp'] / 100:.1f} %", "contributions",
        deductible=False)
    add("crds", "CRDS", crds, f"{p['msa.crds_bp'] / 100:.1f} %", "contributions", deductible=False)
    vivea = min(max(round(positive * p["msa.vivea.rate_bp"] / 10000), round(pass_cents * p["msa.vivea.min_pass_bp"] / 10000)),
                round(pass_cents * p["msa.vivea.max_pass_bp"] / 10000))
    add("vivea", "Formation professionnelle (VIVEA)", vivea, f"{p['msa.vivea.rate_bp'] / 100:.2f} % entre 0,17 % et 0,89 % du PASS",
        "third_party")
    add("fmse", "FMSE (cotisation commune)", p["msa.fmse.amount_cents"], "forfait", "third_party")
    total = sum(l["amount_cents"] for l in lines)
    warnings = [w for w in (warning,) if w]
    if atexa_category not in ATEXA_CATEGORIES:
        warnings.append("Catégorie de risques ATEXA à choisir (avis MSA) : ATEXA non comptée.")
    return {"available": True, "year": year, "base_cents": base, "status": status, "lines": lines,
            "totals": {"total_cents": total,
                       "contributions_cents": sum(l["amount_cents"] for l in lines if l["group"] == "cotisations"),
                       "csg_crds_cents": csg_d + csg_n + crds, "non_deductible_cents": csg_n + crds,
                       "third_party_cents": sum(l["amount_cents"] for l in lines if l["group"] == "third_party")},
            "warnings": warnings,
            "notes": ["Estimation indicative d'après le barème NSA de la MSA : le montant appelé par la caisse fait foi.",
                      "Non comptés : exonération jeune agriculteur (65 % à 15 % sur 5 ans), cotisations complémentaires "
                      "FMSE / InterApi / Val'hor, membres de la famille, modulation."]}
