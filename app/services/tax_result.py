"""Résultat fiscal BA et tableau de passage (lot AG6.a, claudedocs/design_fiscalite_ba.md §§ 2 et 3, AGD23).

- Résultat comptable de l'exercice (classes 6 et 7), puis lignes de passage **extra-comptables**, sans écriture :
  - proposées par Lyvre : écart de valeur fiscale des stocks (AG4.e) ; exonération de l'indemnité d'abattage sanitaire
    des reproducteurs (indemnité − valeur nette, exercice de l'abattage) et réintégration de la part non réinvestie
    à l'échéance de 2 ans (AG5.c, art. 75-0 D, à vérifier) ;
  - saisies : part de la CSG non déductible (depuis l'appel MSA, Q-F2), autres réintégrations et déductions avec motif.
  - L'abattement JA (AG6.b) et la DEP (AG6.c) viendront s'insérer après ces retraitements.
- Répartition entre associés (sociétés à l'IR) : droits aux bénéfices saisis s'ils le sont pour tous les associés,
  sinon parts en **pleine propriété et en usufruit** à la clôture, la nue-propriété n'en recevant aucune (Q-F1).
- Figé au premier calcul après la clôture définitive de l'exercice.
"""
from __future__ import annotations

import json
from datetime import datetime

from app.extensions import db
from app.models import Associate, FiscalYear, TaxResult, TaxResultLine
from app.models.tax_result import TAX_LINE_KINDS


class TaxResultError(Exception):
    def __init__(self, message, field=None, status=422):
        super().__init__(message)
        self.message, self.field, self.status = message, field, status


def enabled() -> bool:
    from app.services.rule_entries import simple_mode
    from app.tenant import is_agri

    return is_agri() and not simple_mode()


def _is_company_is(fy: FiscalYear) -> bool:
    from app.services import tax_profile
    return (tax_profile.current_value("income_tax", fy.end_date) or "").upper() == "IS"


# ------------------------------------------------------------------ lignes proposées

def _stock_line(fy: FiscalYear) -> list[dict]:
    from app.services import stock_tax
    gap = stock_tax.totals(fy)["gap_cents"]
    if not gap:
        return []
    return [{"key": "stock_gap", "label": "Écart de valeur fiscale des stocks (forfaitaire, stock bloqué, valeur saisie)",
             "amount_cents": gap, "source": "inventory", "link": f"/inventory/?fiscal_year={fy.id}"}]


def _slaughter_lines(fy: FiscalYear) -> list[dict]:
    from app.models import LivingReinvestment
    out = []
    for r in LivingReinvestment.query.all():
        exit_ = r.exit
        if exit_.asset.living_kind != "breeding":
            continue
        gain = r.indemnity_cents - r.book_value_cents
        if gain <= 0:
            continue
        if fy.start_date <= exit_.on <= fy.end_date:
            out.append({"key": f"slaughter_exempt_{r.id}", "amount_cents": -gain, "source": "living_assets",
                        "label": f"Abattage sanitaire du {exit_.on:%d/%m/%Y} : indemnité exonérée (indemnité − valeur nette)",
                        "link": "/assets/?living=1", "to_validate": True})
        if fy.start_date <= r.deadline <= fy.end_date and r.reinvested_cents < r.indemnity_cents:
            share = round(gain * (r.indemnity_cents - r.reinvested_cents) / r.indemnity_cents) if r.indemnity_cents else gain
            if share:
                out.append({"key": f"slaughter_reintegration_{r.id}", "amount_cents": share, "source": "living_assets",
                            "label": f"Abattage sanitaire du {exit_.on:%d/%m/%Y} : part non réinvestie à 2 ans",
                            "link": "/assets/?living=1", "to_validate": True})
    return out


def _manual_lines(fy: FiscalYear) -> list[dict]:
    out = []
    for row in TaxResultLine.query.filter_by(fiscal_year_id=fy.id).order_by(TaxResultLine.id):
        sign = -1 if row.kind == "deduct" else 1
        out.append({"key": f"manual_{row.id}", "id": row.id, "kind": row.kind, "label": row.label,
                    "amount_cents": sign * row.amount_cents, "reason": row.reason, "source": "manual"})
    return out


# ------------------------------------------------------------------ répartition

def shares(fy: FiscalYear) -> tuple[list[dict], list[str]]:
    """Quote-parts des associés à la clôture : (lignes, avertissements)."""
    from app.services import associates as assoc

    warnings = []
    held = assoc.holdings(fy.end_date)
    rows = []
    for associate in Associate.query.order_by(Associate.id):
        parts = held.get(associate.id, {})
        weight = (parts.get("full", 0) or 0) + (parts.get("usufruct", 0) or 0)
        if weight or associate.profit_share_bp:
            rows.append({"associate_id": associate.id, "name": associate.name, "weight": weight,
                         "profit_share_bp": associate.profit_share_bp, "is_operator": associate.is_operator,
                         "young_farmer_since": associate.young_farmer_since.isoformat() if associate.young_farmer_since else None})
    if not rows:
        return [], warnings
    explicit = [r for r in rows if r["profit_share_bp"] is not None]
    if explicit and len(explicit) == len(rows):
        total = sum(r["profit_share_bp"] for r in rows)
        if total != 10000:
            warnings.append(f"Droits aux bénéfices saisis : {total / 100:.2f} % au total au lieu de 100 %.".replace(".", ","))
        for r in rows:
            r["share_bp"] = round(r["profit_share_bp"] * 10000 / total) if total else 0
            r["basis"] = "statuts"
    else:
        if explicit:
            warnings.append("Droits aux bénéfices saisis pour une partie des associés seulement : répartition sur les parts.")
        total = sum(r["weight"] for r in rows)
        for r in rows:
            r["share_bp"] = round(r["weight"] * 10000 / total) if total else 0
            r["basis"] = "parts (pleine propriété et usufruit)"
    return rows, warnings


def _split(amount: int, rows: list[dict]) -> list[int]:
    out, left = [], amount
    for index, r in enumerate(rows):
        part = left if index == len(rows) - 1 else round(amount * r["share_bp"] / 10000)
        out.append(part)
        left -= part
    return out


# ------------------------------------------------------------------ calcul

def compute(fy: FiscalYear) -> dict:
    from app.services import closing

    accounting = closing.result(fy)["result_cents"]
    from app.services import cow_provision                       # lot AG6.d : exonération au 6e exercice
    from app.services import ba_regimes                          # lot AG6.e : 72 E bis, étalement 75-0 A
    from app.services import capital_gains                       # lot AG6.g : plus-values à long terme, 151 septies
    from app.services import msa_ventilation                     # lot AG7.d : CSG non déductible des appels MSA (EI)
    msa_lines = [] if _is_company_is(fy) else msa_ventilation.tax_lines(fy)
    lines = [*_stock_line(fy), *_slaughter_lines(fy), *cow_provision.tax_lines(fy), *ba_regimes.tax_lines(fy),
             *capital_gains.tax_lines(fy), *msa_lines, *_manual_lines(fy)]
    before_ja = accounting + sum(l["amount_cents"] for l in lines)
    company_is = _is_company_is(fy)
    rows, warnings = ([], []) if company_is else shares(fy)
    if not company_is:                                            # lot AG6.b : abattement JA, avant la DEP
        from app.services import young_farmer
        ja_lines, ja_warnings = young_farmer.abatements(fy, before_ja, rows)
        lines += ja_lines
        warnings += ja_warnings
    else:
        ja_lines = []
    before_dep = accounting + sum(l["amount_cents"] for l in lines)
    dep_lines = []
    if not company_is:                                            # lot AG6.c : DEP après l'abattement JA
        from app.services import dep
        dep_lines = dep.tax_lines(fy)
        lines += dep_lines
    total = accounting + sum(l["amount_cents"] for l in lines)
    shared = before_ja + sum(l["amount_cents"] for l in dep_lines)
    if rows:
        for r, part in zip(rows, _split(shared, rows)):
            own = sum(l["amount_cents"] for l in ja_lines if l["associate_id"] == r["associate_id"])
            r["ja_cents"] = -own
            r["fiscal_result_cents"] = part + own
    if any(l.get("to_validate") and l.get("source") == "living_assets" for l in lines):
        warnings.append("Exonération et réintégration de l'abattage sanitaire : règle de l'art. 75-0 D à vérifier.")
    if not company_is:
        warnings += msa_ventilation.tax_warnings(fy, lines)
    if any(l.get("source") == "capital_gains" for l in lines):
        warnings.append("Plus-values : régime court / long terme et seuils de l'art. 151 septies à valider.")
    return {"fiscal_year": {"id": fy.id, "label": fy.label, "end_date": fy.end_date.isoformat(), "status": fy.status},
            "accounting_result_cents": accounting, "lines": lines,
            "additions_cents": sum(l["amount_cents"] for l in lines if l["amount_cents"] > 0),
            "deductions_cents": -sum(l["amount_cents"] for l in lines if l["amount_cents"] < 0),
            "fiscal_result_before_ja_cents": before_ja, "fiscal_result_before_dep_cents": before_dep,
            "fiscal_result_cents": total, "company_is": company_is, "associates": rows, "warnings": warnings,
            "frozen": False, "frozen_at": None}


def view(fy: FiscalYear) -> dict:
    """Résultat fiscal : figé après la clôture définitive (premier calcul), recalculé sinon."""
    row = TaxResult.query.filter_by(fiscal_year_id=fy.id).first()
    if row is not None and row.snapshot_json:
        if fy.status == "closed":
            return json.loads(row.snapshot_json)
        row.snapshot_json, row.frozen_at = None, None                      # exercice rouvert : recalcul
        db.session.commit()
    data = compute(fy)
    if fy.status == "closed":
        if row is None:
            row = TaxResult(fiscal_year_id=fy.id)
            db.session.add(row)
        row.frozen_at = datetime.utcnow()
        data.update(frozen=True, frozen_at=row.frozen_at.isoformat(timespec="seconds"))
        row.snapshot_json = json.dumps(data)
        db.session.commit()
    return data


# ------------------------------------------------------------------ saisie

def _editable(fy: FiscalYear) -> None:
    if fy.status == "closed":
        raise TaxResultError("Exercice clôturé : le résultat fiscal est figé.", status=409)


def add_line(fy: FiscalYear, data: dict) -> TaxResultLine:
    _editable(fy)
    kind = data.get("kind")
    if kind not in TAX_LINE_KINDS:
        raise TaxResultError("Type de ligne inconnu (CSG non déductible, réintégration, déduction).", "kind")
    amount = data.get("amount_cents")
    if isinstance(amount, bool) or not isinstance(amount, int) or not 0 < amount <= 10 ** 11:
        raise TaxResultError("Montant positif en centimes attendu (le sens vient du type).", "amount_cents")
    label = (str(data.get("label") or "").strip()[:200]) or TAX_LINE_KINDS[kind]
    reason = (str(data.get("reason") or "").strip()[:500]) or None
    if kind != "csg" and (reason is None or len(reason) < 5):
        raise TaxResultError("Motif obligatoire (5 caractères au moins) pour une réintégration ou une déduction saisie.",
                             "reason")
    row = TaxResultLine(fiscal_year_id=fy.id, kind=kind, label=label, amount_cents=amount, reason=reason)
    db.session.add(row)
    db.session.flush()
    return row


def delete_line(fy: FiscalYear, line_id) -> None:
    _editable(fy)
    row = db.session.get(TaxResultLine, line_id) if isinstance(line_id, int) else None
    if row is None or row.fiscal_year_id != fy.id:
        raise TaxResultError("Ligne introuvable.", status=404)
    db.session.delete(row)
    db.session.flush()


def meta() -> dict:
    return {"kinds": [{"value": k, "label": v} for k, v in TAX_LINE_KINDS.items()]}
