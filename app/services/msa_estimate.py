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


def collaborator(year: int, atexa_category: str | None = None, secondary: bool = False) -> dict:
    """Lot CG5.f : collaborateur d'exploitation, cotisations sur assiettes forfaitaires (barème MSA 2026) : retraite de
    base sur 600 SMIC, RCO sur 1 200 SMIC, invalidité et IJ forfaitaires, ATEXA propre, VIVEA « membres de la famille » ;
    ni AMEXA, ni prestations familiales, ni CSG (pas de revenu professionnel propre)."""
    keys = ("msa.smic_hour_cents", "msa.pass_cents", "msa.rco.rate_bp", "msa.ij.amount_cents",
            "msa.collaborator.pension_rates", "msa.collaborator.pension_base_smic", "msa.collaborator.rco_base_smic",
            "msa.collaborator.invalidity_cents", "msa.collaborator.atexa.amounts", "msa.family.vivea_pass_bp")
    on = date(year, 1, 1)
    p = {k: reg_params.value(k, on, None) for k in keys}
    warning = None
    if any(v is None for v in p.values()):
        latest = max((x.valid_from for x in reg_params.history("msa.collaborator.pension_rates")), default=None)
        if latest is None:
            return {"available": False, "reason": "Barème du collaborateur non paramétré."}
        p = {k: reg_params.value(k, latest, None) for k in keys}
        if any(v is None for v in p.values()):
            return {"available": False, "reason": "Barème du collaborateur incomplet."}
        warning = f"Barème {year} non publié : barème {latest.year} appliqué."
    smic, kind = p["msa.smic_hour_cents"], "secondary" if secondary else "principal"
    lines = []

    def add(key, label, amount, detail, group="cotisations"):
        lines.append({"key": key, "label": label, "amount_cents": int(amount), "detail": detail, "group": group,
                      "deductible": True})

    pension_base = p["msa.collaborator.pension_base_smic"] * smic
    rate = p["msa.collaborator.pension_rates"][kind]
    add("pension", "Retraite de base (forfaitaire)", round(pension_base * rate / 10000),
        f"{rate / 100:.2f} % de {_fmt(pension_base)} ({p['msa.collaborator.pension_base_smic']} SMIC)")
    rco_base = p["msa.collaborator.rco_base_smic"] * smic
    add("rco", "Retraite complémentaire (RCO)", round(rco_base * p["msa.rco.rate_bp"] / 10000),
        f"{p['msa.rco.rate_bp'] / 100:.2f} % de {_fmt(rco_base)} ({p['msa.collaborator.rco_base_smic']} SMIC)")
    add("invalidity", "Invalidité", p["msa.collaborator.invalidity_cents"], "forfait")
    if not secondary:
        add("ij", "Indemnités journalières AMEXA", p["msa.ij.amount_cents"], "forfait")
    amounts = p["msa.collaborator.atexa.amounts"].get(kind) or []
    if atexa_category in ATEXA_CATEGORIES and len(amounts) == 5:
        add("atexa", f"Accidents du travail (ATEXA, catégorie {atexa_category})",
            amounts[ATEXA_CATEGORIES.index(atexa_category)], "forfait du collaborateur")
    add("vivea", "Formation professionnelle (VIVEA)", round(p["msa.pass_cents"] * p["msa.family.vivea_pass_bp"] / 10000),
        f"{p['msa.family.vivea_pass_bp'] / 100:.2f} % du PASS", "third_party")
    warnings = [w for w in (warning,) if w]
    if atexa_category not in ATEXA_CATEGORIES:
        warnings.append("Catégorie de risques ATEXA à choisir : cotisation non comptée.")
    warnings.append("Statut de collaborateur limité à 5 ans ; fin au 31/12/2026 pour un conjoint déjà collaborateur au "
                    "01/01/2022 [SOC-06].")
    total = sum(l["amount_cents"] for l in lines)
    return {"available": True, "year": year, "base_cents": None, "status": "collaborator", "lines": lines,
            "totals": {"total_cents": total,
                       "contributions_cents": sum(l["amount_cents"] for l in lines if l["group"] == "cotisations"),
                       "csg_crds_cents": 0, "non_deductible_cents": 0,
                       "third_party_cents": sum(l["amount_cents"] for l in lines if l["group"] == "third_party")},
            "warnings": warnings,
            "notes": ["Collaborateur : assiettes forfaitaires du barème NSA de la MSA, sans revenu propre ; le montant "
                      "appelé par la caisse fait foi."]}


def _install_params(year: int) -> dict | None:
    keys = ("msa.install.base_smic", "msa.install.vivea_base_smic")
    for on in (date(year, 1, 1), *(p.valid_from for p in reg_params.history("msa.install.base_smic"))):
        values = {k: reg_params.value(k, on, None) for k in keys}
        if all(v is not None for v in values.values()):
            return values
    return None


def solidarity(base: int | None, year: int, installation: bool = False) -> dict:
    """Lot CG5.f : cotisant de solidarité (CRPM L.731-23, barème MSA 2026) : cotisation de 14 % des revenus (ou de
    l'assiette forfaitaire de 100 SMIC sans revenus), CSG / CRDS, ATEXA forfaitaire, VIVEA 0,17 % du PASS."""
    keys = ("msa.smic_hour_cents", "msa.pass_cents", "msa.solidarity.rate_bp", "msa.solidarity.install_base_smic",
            "msa.solidarity.atexa_cents", "msa.family.vivea_pass_bp", "msa.csg.deductible_bp", "msa.csg.non_deductible_bp",
            "msa.crds_bp")
    p, warning = None, None
    for on in (date(year, 1, 1), *(x.valid_from for x in reg_params.history("msa.solidarity.rate_bp"))):
        values = {k: reg_params.value(k, on, None) for k in keys}
        if all(v is not None for v in values.values()):
            p = values
            if on != date(year, 1, 1):
                warning = f"Barème {year} non publié : barème {on.year} appliqué."
            break
    if p is None:
        return {"available": False, "reason": "Barème du cotisant de solidarité non paramétré."}
    if base is None and not installation:
        return {"available": False, "reason": "Revenus professionnels de l'année précédente à saisir (ou nouvel installé)."}
    smic = p["msa.smic_hour_cents"]
    assiette = p["msa.solidarity.install_base_smic"] * smic if installation else max(base, 0)
    lines = []

    def add(key, label, amount, detail, group, deductible=True):
        lines.append({"key": key, "label": label, "amount_cents": int(amount), "detail": detail, "group": group,
                      "deductible": deductible})

    rate = p["msa.solidarity.rate_bp"]
    add("solidarity", "Cotisation de solidarité", round(assiette * rate / 10000),
        f"{rate / 100:.0f} % de {_fmt(assiette)}", "cotisations")
    add("atexa", "Accidents du travail (ATEXA)", p["msa.solidarity.atexa_cents"], "forfait du cotisant de solidarité",
        "cotisations")
    csg_d = round(assiette * p["msa.csg.deductible_bp"] / 10000)
    csg_n = round(assiette * p["msa.csg.non_deductible_bp"] / 10000)
    crds = round(assiette * p["msa.crds_bp"] / 10000)
    add("csg_deductible", "CSG déductible", csg_d, f"{p['msa.csg.deductible_bp'] / 100:.1f} %", "contributions")
    add("csg_non_deductible", "CSG non déductible", csg_n, f"{p['msa.csg.non_deductible_bp'] / 100:.1f} %",
        "contributions", deductible=False)
    add("crds", "CRDS", crds, f"{p['msa.crds_bp'] / 100:.1f} %", "contributions", deductible=False)
    add("vivea", "Formation professionnelle (VIVEA)", round(p["msa.pass_cents"] * p["msa.family.vivea_pass_bp"] / 10000),
        f"{p['msa.family.vivea_pass_bp'] / 100:.2f} % du PASS", "third_party")
    total = sum(l["amount_cents"] for l in lines)
    warnings = [w for w in (warning,) if w]
    if installation:
        warnings.append(f"Sans revenus : assiette forfaitaire de {p['msa.solidarity.install_base_smic']} SMIC, régularisée "
                        "ensuite.")
    return {"available": True, "year": year, "base_cents": assiette, "status": "solidarity", "lines": lines,
            "totals": {"total_cents": total,
                       "contributions_cents": sum(l["amount_cents"] for l in lines if l["group"] == "cotisations"),
                       "csg_crds_cents": csg_d + csg_n + crds, "non_deductible_cents": csg_n + crds,
                       "third_party_cents": sum(l["amount_cents"] for l in lines if l["group"] == "third_party")},
            "warnings": warnings,
            "notes": ["Cotisant de solidarité (CRPM L.731-23) : estimation indicative, le montant appelé par la caisse fait foi."]}


def estimate(base: int | None, year: int, status: str = "principal", atexa_category: str | None = None,
             installation: bool = False) -> dict:
    """Cotisations et contributions estimées de l'année `year` sur l'assiette `base` (centimes). `installation` : nouvel
    installé sans revenus professionnels, assiettes forfaitaires provisoires du barème (lot CG5.f)."""
    if status == "collaborator":                       # lot CG5.f : assiettes forfaitaires, sans revenu propre
        return collaborator(year, atexa_category)
    if status == "solidarity":
        return solidarity(base, year, installation)
    if status not in ("principal", "secondary"):
        return {"available": False, "reason": "Statut non couvert par l'estimation."}
    if base is None and not installation:
        return {"available": False, "reason": f"Assiette des cotisations {year} inconnue : historique des assiettes à compléter."}
    p, warning = _params(year)
    if not p:
        return {"available": False, "reason": warning}
    pass_cents, smic = p["msa.pass_cents"], p["msa.smic_hour_cents"]
    install = _install_params(year) if installation else None
    if installation and install is None:
        return {"available": False, "reason": "Assiettes forfaitaires d'installation non paramétrées."}
    positive = install["msa.install.base_smic"] * smic if installation else max(base, 0)
    lines = []

    def add(key, label, amount, detail, group, deductible=True):
        lines.append({"key": key, "label": label, "amount_cents": int(amount), "detail": detail, "group": group,
                      "deductible": deductible})

    amexa, detail = _amexa(positive, p)
    add("amexa", "Assurance maladie (AMEXA)", amexa, detail, "cotisations")
    inv_min = round(pass_cents * p["msa.invalidity.min_pass_bp"] / 10000)
    inv_base = inv_min if installation else max(positive, inv_min)
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
    rco_base = p["msa.rco.min_smic"] * smic if installation else max(positive, p["msa.rco.min_smic"] * smic)
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
    vivea_base = install["msa.install.vivea_base_smic"] * smic if installation else positive
    vivea = min(max(round(vivea_base * p["msa.vivea.rate_bp"] / 10000), round(pass_cents * p["msa.vivea.min_pass_bp"] / 10000)),
                round(pass_cents * p["msa.vivea.max_pass_bp"] / 10000))
    add("vivea", "Formation professionnelle (VIVEA)", vivea, f"{p['msa.vivea.rate_bp'] / 100:.2f} % entre 0,17 % et 0,89 % du PASS",
        "third_party")
    add("fmse", "FMSE (cotisation commune)", p["msa.fmse.amount_cents"], "forfait", "third_party")
    total = sum(l["amount_cents"] for l in lines)
    warnings = [w for w in (warning,) if w]
    if atexa_category not in ATEXA_CATEGORIES:
        warnings.append("Catégorie de risques ATEXA à choisir (avis MSA) : ATEXA non comptée.")
    if installation:
        warnings.append(f"Nouvel installé : assiettes forfaitaires provisoires ({install['msa.install.base_smic']} SMIC, "
                        f"{install['msa.install.vivea_base_smic']} SMIC en formation, 1 820 SMIC en RCO, 11,5 % du PASS "
                        "en invalidité), régularisées sur les revenus réels. Exonération JA non comptée.")
        base = positive
    return {"available": True, "year": year, "base_cents": base, "status": status, "lines": lines,
            "totals": {"total_cents": total,
                       "contributions_cents": sum(l["amount_cents"] for l in lines if l["group"] == "cotisations"),
                       "csg_crds_cents": csg_d + csg_n + crds, "non_deductible_cents": csg_n + crds,
                       "third_party_cents": sum(l["amount_cents"] for l in lines if l["group"] == "third_party")},
            "warnings": warnings,
            "notes": ["Estimation indicative d'après le barème NSA de la MSA : le montant appelé par la caisse fait foi.",
                      "Non comptés : exonération jeune agriculteur (65 % à 15 % sur 5 ans), cotisations complémentaires "
                      "FMSE / InterApi / Val'hor, membres de la famille, modulation."]}
