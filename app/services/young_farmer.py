"""Abattement jeune agriculteur (lot AG6.b, claudedocs/design_fiscalite_ba.md § 4, art. 73 B, AGD23).

- Bénéficiaires : l'exploitant individuel (date d'installation aidée du profil) ou, en société à l'IR, chaque associé
  exploitant qui a une date d'octroi de la première aide JA ; exercices clos dans les 60 mois suivant cet octroi.
- Base : bénéfice après les retraitements du tableau de passage (avant la DEP), quote-part de l'associé en société.
- Barème daté `ba.ja.*` : 75 % si la base n'excède pas la première tranche (50 700 €) ; sinon 50 % de la première
  tranche et 30 % de la seconde (jusqu'à 67 600 €), rien au-delà ; l'exercice d'inscription de la DJA en comptabilité,
  100 % puis 60 %, et l'abattement au moins égal à la DJA (dossier DJA d'AG3, Q-F9), sans dépasser la base.
"""
from __future__ import annotations

import calendar
from datetime import date

from app.models import Aid, FiscalYear
from app.services import reg_params


def _add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year, month = day.year + month // 12, month % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _param(key: str, fy: FiscalYear):
    return reg_params.value(key, fy.end_date, default=None)


def eligible(granted_on: date | None, fy: FiscalYear) -> bool:
    if granted_on is None:
        return False
    duration = _param("ba.ja.duration_months", fy) or 60
    return granted_on <= fy.end_date <= _add_months(granted_on, duration)


def dja(fy: FiscalYear) -> tuple[int, Aid | None]:
    """DJA inscrite en comptabilité dans l'exercice (dossier d'aide « dja », décision datée dans l'exercice)."""
    for aid in Aid.query.filter_by(scheme="dja"):
        if aid.decision_on and fy.start_date <= aid.decision_on <= fy.end_date and aid.status != "refused":
            from app.services import aids
            return aids.acquired_cents(aid), aid
    return 0, None


def compute(base: int, fy: FiscalYear, dja_cents: int = 0) -> dict:
    """Abattement sur une base (centimes) ; `dja_cents` > 0 : exercice d'inscription de la DJA."""
    low, high = _param("ba.ja.threshold_low_cents", fy), _param("ba.ja.threshold_high_cents", fy)
    if low is None or high is None:
        return {"amount_cents": 0, "error": "Barème de l'abattement JA introuvable pour la date de clôture."}
    if base <= 0:
        return {"amount_cents": 0, "detail": "Pas de bénéfice."}
    first, second = min(base, low), max(min(base, high) - low, 0)
    if dja_cents:
        amount = round(first * _param("ba.ja.dja_rate_low_bp", fy) / 10000 + second * _param("ba.ja.dja_rate_high_bp", fy) / 10000)
        floor = min(dja_cents, base)
        detail = "exercice d'inscription de la DJA : 100 % puis 60 %"
        if amount < floor:
            amount, detail = floor, detail + " ; porté au montant de la DJA"
    elif base <= low:
        amount = round(base * _param("ba.ja.rate_full_bp", fy) / 10000)
        detail = "75 % de la base"
    else:
        amount = round(first * _param("ba.ja.rate_low_bp", fy) / 10000 + second * _param("ba.ja.rate_high_bp", fy) / 10000)
        detail = "50 % de la première tranche, 30 % de la seconde" + (" ; rien au-delà du plafond" if base > high else "")
    return {"amount_cents": amount, "detail": detail}


def abatements(fy: FiscalYear, base_total: int, associates: list[dict]) -> tuple[list[dict], list[str]]:
    """Lignes d'abattement JA de l'exercice : une par bénéficiaire. `associates` : quotes-parts (tax_result.shares)."""
    from app.models import Associate
    from app.services import agri_profile

    warnings, lines = [], []
    dja_cents, dja_aid = dja(fy)
    if associates:
        beneficiaries = []
        for row in associates:
            associate = Associate.query.get(row["associate_id"])
            if associate.young_farmer_since and eligible(associate.young_farmer_since, fy):
                if not associate.is_operator:
                    warnings.append(f"{associate.name} : date JA saisie mais associé non exploitant, pas d'abattement.")
                    continue
                beneficiaries.append((associate, row))
        if dja_cents and len(beneficiaries) > 1:
            warnings.append("DJA de l'exercice et plusieurs associés JA : le minimum « au moins égal à la DJA » n'est pas "
                            "appliqué ; saisissez la part de chacun en ligne de déduction si besoin.")
        for associate, row in beneficiaries:
            base = round(base_total * row["share_bp"] / 10000)
            result = compute(base, fy, dja_cents if len(beneficiaries) == 1 else 0)
            if result.get("error"):
                warnings.append(result["error"])
            if result["amount_cents"]:
                lines.append({"key": f"ja_{associate.id}", "associate_id": associate.id, "source": "young_farmer",
                              "label": f"Abattement jeune agriculteur — {associate.name} ({result['detail']})",
                              "amount_cents": -result["amount_cents"], "base_cents": base})
    else:
        raw = agri_profile.get().get("young_farmer_since")
        try:
            granted = date.fromisoformat(raw) if raw else None
        except ValueError:
            granted = None
        if granted and eligible(granted, fy):
            result = compute(base_total, fy, dja_cents)
            if result.get("error"):
                warnings.append(result["error"])
            if result["amount_cents"]:
                lines.append({"key": "ja", "associate_id": None, "source": "young_farmer",
                              "label": f"Abattement jeune agriculteur ({result['detail']})",
                              "amount_cents": -result["amount_cents"], "base_cents": base_total})
    if dja_aid is not None and not lines and dja_cents:
        warnings.append("DJA inscrite dans l'exercice sans bénéficiaire JA éligible (date d'octroi à saisir).")
    return lines, warnings
