"""Déduction pour épargne de précaution, DEP (lot AG6.c, claudedocs/design_fiscalite_ba.md § 5, art. 73, AGD23).

- **Plafond** (barème daté `ba.dep.*`) sur le bénéfice après l'abattement JA : 100 % jusqu'au 1er seuil, puis 30 %,
  20 % et 10 % des tranches suivantes, plafonné ; × associés exploitants (4 au plus), sans dépasser le bénéfice ;
  au prorata de la durée de l'exercice ; plafond global des déductions non rapportées.
- **Déduction extra-comptable** (Q-F3) : ligne de passage −, sans écriture.
- **Registre par exercice d'origine** (DEP, anciennes DPI / DPA) : utilisations (réintégrées dans l'exercice, 30 %
  exonérés en cas d'aléa, dans les plafonds), réintégrations, **10e exercice** (réintégration proposée).
- **Épargne** : solde des comptes bancaires repérés « épargne DEP » et substituts saisis (fourrage, stocks à rotation
  lente) ; ratio ≥ 50 % (et ≤ 100 %) des déductions non rapportées ; en défaut, réintégration proposée de la fraction
  qui excède le double de l'épargne (à valider).
- **Valeur ajoutée** sur 3 exercices pour l'aléa économique (formule de l'art. 73 II-2 d), affichée pour l'attestation.
"""
from __future__ import annotations

import calendar
from datetime import date

from sqlalchemy import func

from app.extensions import db
from app.models import Account, Associate, BankAccount, DepEntry, DepMovement, DepSubstitute, FiscalYear, JournalEntry, JournalLine
from app.models.journal_entry import SOURCE_OPENING
from app.models.tax_result import DEP_HAZARDS, DEP_KINDS, DEP_MOVEMENTS
from app.services import reg_params
from app.services.tax_result import TaxResultError


def _p(key: str, fy: FiscalYear):
    return reg_params.value(key, fy.end_date, default=None)


def _add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year, month = day.year + month // 12, month % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def operators(fy: FiscalYear) -> int:
    """Associés exploitants (multiplicateur des plafonds, 4 au plus) ; 1 pour l'exploitant individuel."""
    count = Associate.query.filter_by(is_operator=True).count()
    cap = reg_params.value("ba.associates.multiplier_cap", fy.end_date, default=4) or 4
    return max(1, min(count, cap))


def _months(fy: FiscalYear) -> int:
    return (fy.end_date.year - fy.start_date.year) * 12 + fy.end_date.month - fy.start_date.month + 1


def ceiling(base: int, fy: FiscalYear) -> dict:
    """Plafond de la DEP de l'exercice pour un bénéfice `base` (après abattement JA)."""
    keys = ("band1_cents", "band2_cents", "band3_cents", "band4_cents", "rate2_bp", "rate3_bp", "rate4_bp", "cap_cents")
    values = {k: _p(f"ba.dep.{k}", fy) for k in keys}
    if any(v is None for v in values.values()):
        return {"ceiling_cents": 0, "error": "Barème de la DEP introuvable pour la date de clôture."}
    end = _p("ba.dep.end_date", fy)
    if end and fy.end_date > date.fromisoformat(end):
        return {"ceiling_cents": 0, "error": f"DEP applicable aux exercices clos jusqu'au {date.fromisoformat(end):%d/%m/%Y}."}
    if base <= 0:
        return {"ceiling_cents": 0, "per_operator_cents": 0, "operators": operators(fy)}
    b1, b2, b3, b4 = (values[k] for k in ("band1_cents", "band2_cents", "band3_cents", "band4_cents"))
    amount = min(base, b1)
    for low, high, rate in ((b1, b2, values["rate2_bp"]), (b2, b3, values["rate3_bp"]), (b3, b4, values["rate4_bp"])):
        if base > low:
            amount += round((min(base, high) - low) * rate / 10000)
    amount = values["cap_cents"] if base >= b4 else min(amount, values["cap_cents"])
    months = _months(fy)
    if months != 12:
        amount = round(amount * months / 12)
    n = operators(fy)
    total = min(amount * n, base)
    global_cap = (_p("ba.dep.global_cap_cents", fy) or 0) * n
    pending = outstanding(fy, exclude_fy=fy)
    room = max(global_cap - pending, 0)
    return {"ceiling_cents": min(total, room), "per_operator_cents": amount, "operators": n, "global_cap_cents": global_cap,
            "pending_cents": pending, "months": months}


# ------------------------------------------------------------------ registre

def _fy_index() -> list[FiscalYear]:
    return FiscalYear.query.order_by(FiscalYear.start_date).all()


def deadline_label(entry: DepEntry) -> str:
    years = _fy_index()
    if entry.fiscal_year_id is not None:
        ids = [y.id for y in years]
        index = ids.index(entry.fiscal_year_id) + (reg_params.value("ba.dep.reintegration_years", entry.fiscal_year.end_date,
                                                                   default=10) or 10)
        if index < len(years):
            return years[index].label
        return f"{entry.fiscal_year.end_date.year + 10}"
    return f"{(entry.origin_year or 0) + 10}"


def _is_deadline(entry: DepEntry, fy: FiscalYear) -> bool:
    years = _fy_index()
    if entry.fiscal_year_id is not None:
        ids = [y.id for y in years]
        n = reg_params.value("ba.dep.reintegration_years", fy.end_date, default=10) or 10
        index = ids.index(entry.fiscal_year_id) + n
        return index < len(years) and years[index].id == fy.id
    return entry.origin_year is not None and fy.end_date.year == entry.origin_year + 10


def _before_or_in(entry: DepEntry, fy: FiscalYear) -> bool:
    if entry.fiscal_year_id is not None:
        return entry.fiscal_year.end_date <= fy.end_date
    return entry.origin_year is not None and entry.origin_year <= fy.end_date.year


def entry_outstanding(entry: DepEntry, fy: FiscalYear | None = None, include_fy: bool = True) -> int:
    used = 0
    for m in entry.movements:
        mfy = db.session.get(FiscalYear, m.fiscal_year_id)
        if fy is None or mfy.end_date < fy.end_date or (include_fy and mfy.id == fy.id):
            used += m.amount_cents
    return entry.amount_cents - used


def outstanding(fy: FiscalYear, exclude_fy: FiscalYear | None = None) -> int:
    """Déductions non rapportées à la clôture de `fy` (hors la déduction de `exclude_fy`)."""
    total = 0
    for entry in DepEntry.query.all():
        if not _before_or_in(entry, fy) or (exclude_fy is not None and entry.fiscal_year_id == exclude_fy.id):
            continue
        total += max(entry_outstanding(entry, fy), 0)
    return total


def register(fy: FiscalYear) -> list[dict]:
    out = []
    for entry in sorted(DepEntry.query.all(), key=lambda e: (e.fiscal_year.end_date if e.fiscal_year else date(e.origin_year or 1900, 12, 31))):
        if not _before_or_in(entry, fy):
            continue
        out.append({"id": entry.id, "kind": entry.kind, "kind_label": DEP_KINDS[entry.kind],
                    "origin": entry.fiscal_year.label if entry.fiscal_year else str(entry.origin_year),
                    "amount_cents": entry.amount_cents, "outstanding_cents": entry_outstanding(entry, fy),
                    "deadline": deadline_label(entry), "deadline_now": _is_deadline(entry, fy), "note": entry.note,
                    "movements": [{"id": m.id, "kind": m.kind, "kind_label": DEP_MOVEMENTS[m.kind], "on": m.on.isoformat(),
                                   "amount_cents": m.amount_cents, "exempt_cents": m.exempt_cents, "hazard": m.hazard,
                                   "reason": m.reason, "fiscal_year_id": m.fiscal_year_id} for m in entry.movements]})
    return out


# ------------------------------------------------------------------ épargne

def _balance(account_id: int, on: date) -> int:
    total = (db.session.query(func.coalesce(func.sum(JournalLine.debit_cents - JournalLine.credit_cents), 0))
             .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
             .filter(JournalLine.account_id == account_id, JournalEntry.entry_date <= on,
                     db.or_(JournalEntry.source.is_(None), JournalEntry.source != SOURCE_OPENING)).scalar())
    opening = (db.session.query(func.coalesce(func.sum(JournalLine.debit_cents - JournalLine.credit_cents), 0))
               .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
               .join(FiscalYear, FiscalYear.id == JournalEntry.fiscal_year_id)
               .filter(JournalLine.account_id == account_id, JournalEntry.source == SOURCE_OPENING,
                       FiscalYear.start_date == db.session.query(func.min(FiscalYear.start_date)).scalar_subquery()).scalar())
    return int(total or 0) + int(opening or 0)


def savings(fy: FiscalYear, today: date | None = None) -> dict:
    accounts = BankAccount.query.filter_by(dep_savings=True).all()
    at_close = sum(_balance(a.account_id, fy.end_date) for a in accounts)
    deadline = _add_months(fy.end_date, 6)
    at_deadline = sum(_balance(a.account_id, deadline) for a in accounts)
    substitutes = DepSubstitute.query.filter_by(fiscal_year_id=fy.id).all()
    sub_total = sum(s.amount_cents for s in substitutes)
    pending = outstanding(fy)
    best = max(at_close, at_deadline) + sub_total
    minimum = round(pending * (_p("ba.dep.savings_min_bp", fy) or 5000) / 10000)
    passed = (today or date.today()) > deadline                     # épargne à constituer dans les 6 mois
    shortfall = max(pending - 2 * best, 0) if pending and best < minimum and passed else 0
    return {"accounts": [{"id": a.id, "label": a.label} for a in accounts], "at_close_cents": at_close,
            "deadline": deadline.isoformat(), "at_deadline_cents": at_deadline, "substitutes_cents": sub_total,
            "substitutes": [{"id": s.id, "label": s.label, "amount_cents": s.amount_cents} for s in substitutes],
            "savings_cents": best, "pending_cents": pending, "minimum_cents": minimum,
            "ratio_bp": round(best * 10000 / pending) if pending else None, "below": pending > 0 and best < minimum,
            "deadline_passed": passed,
            "above": pending > 0 and best > pending, "shortfall_reintegration_cents": shortfall}


# ------------------------------------------------------------------ valeur ajoutée (aléa économique)

def value_added(fy: FiscalYear) -> int:
    """VA de l'exercice : produits 70 à 74 − consommations de tiers (60, 61, 62), hors à-nouveaux."""
    rows = (db.session.query(Account.code, func.sum(JournalLine.credit_cents - JournalLine.debit_cents))
            .join(JournalLine, JournalLine.account_id == Account.id)
            .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
            .filter(JournalEntry.fiscal_year_id == fy.id,
                    db.or_(*[Account.code.like(f"{p}%") for p in ("70", "71", "72", "73", "74", "60", "61", "62")]))
            .group_by(Account.code).all())
    return sum(int(v or 0) for _code, v in rows)


def economic_hazard(fy: FiscalYear) -> dict:
    years = [y for y in _fy_index() if y.end_date <= fy.end_date]
    index = [y.id for y in years].index(fy.id)
    current = value_added(fy)
    prev3 = [value_added(y) for y in years[max(index - 3, 0):index]]
    older3 = [value_added(y) for y in years[max(index - 4, 0):max(index - 1, 0)]]
    avg3 = round(sum(prev3) / len(prev3)) if len(prev3) == 3 else None
    avg_older = round(sum(older3) / len(older3)) if len(older3) == 3 else None
    drop3 = round((avg3 - current) * 10000 / avg3) if avg3 else None
    drop_older = round((avg_older - current) * 10000 / avg_older) if avg_older else None
    return {"value_added_cents": current, "average3_cents": avg3, "drop3_bp": drop3, "average_older_cents": avg_older,
            "drop_older_bp": drop_older,
            "hazard": bool((drop3 is not None and drop3 > 1000) or (drop_older is not None and drop_older > 1500))}


# ------------------------------------------------------------------ saisie

def _require_open(fy: FiscalYear) -> None:
    if fy.status == "closed":
        raise TaxResultError("Exercice clôturé : la DEP est figée.", status=409)


def set_deduction(fy: FiscalYear, amount, base: int) -> DepEntry | None:
    _require_open(fy)
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
        raise TaxResultError("Montant de la DEP positif en centimes attendu.", "amount_cents")
    entry = DepEntry.query.filter_by(fiscal_year_id=fy.id).first()
    if amount == 0:
        if entry is not None:
            if entry.movements:
                raise TaxResultError("Cette DEP a déjà des utilisations ou réintégrations.", status=409)
            db.session.delete(entry)
            db.session.flush()
        return None
    limit = ceiling(base, fy)
    if limit.get("error"):
        raise TaxResultError(limit["error"], "amount_cents")
    if amount > limit["ceiling_cents"]:
        raise TaxResultError(f"La DEP dépasse le plafond de l'exercice ({limit['ceiling_cents'] / 100:.2f} €).".replace(".", ",", 1),
                             "amount_cents")
    if entry is None:
        entry = DepEntry(kind="dep", fiscal_year_id=fy.id, amount_cents=amount)
        db.session.add(entry)
    entry.amount_cents = amount
    db.session.flush()
    return entry


def add_history(data: dict) -> DepEntry:
    kind = data.get("kind") or "dep"
    if kind not in DEP_KINDS:
        raise TaxResultError("Type inconnu (DEP, DPI, DPA).", "kind")
    year, amount = data.get("origin_year"), data.get("amount_cents")
    if isinstance(year, bool) or not isinstance(year, int) or not 1990 <= year <= 2100:
        raise TaxResultError("Exercice d'origine : année attendue.", "origin_year")
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        raise TaxResultError("Montant non rapporté positif attendu.", "amount_cents")
    entry = DepEntry(kind=kind, origin_year=year, amount_cents=amount, note=(str(data.get("note") or "").strip()[:300]) or None)
    db.session.add(entry)
    db.session.flush()
    return entry


def _exempt_used(fy: FiscalYear, economic: bool | None = None) -> int:
    query = DepMovement.query.filter_by(fiscal_year_id=fy.id)
    rows = query.all()
    return sum(m.exempt_cents for m in rows if economic is None or (m.hazard == "economic") == economic)


def add_movement(fy: FiscalYear, data: dict) -> DepMovement:
    _require_open(fy)
    entry = db.session.get(DepEntry, data.get("entry_id")) if isinstance(data.get("entry_id"), int) else None
    if entry is None or not _before_or_in(entry, fy):
        raise TaxResultError("Déduction introuvable.", "entry_id", 404)
    kind = data.get("kind")
    if kind not in DEP_MOVEMENTS:
        raise TaxResultError("Mouvement inconnu (utilisation, réintégration).", "kind")
    try:
        on = date.fromisoformat(str(data.get("on") or "")[:10])
    except ValueError:
        raise TaxResultError("Date : AAAA-MM-JJ.", "on") from None
    if not fy.start_date <= on <= fy.end_date:
        raise TaxResultError("Date hors de l'exercice.", "on")
    amount = data.get("amount_cents")
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        raise TaxResultError("Montant positif attendu.", "amount_cents")
    if amount > entry_outstanding(entry, fy):
        raise TaxResultError("Le montant dépasse ce qui reste de cette déduction.", "amount_cents")
    hazard = data.get("hazard") or None
    if hazard is not None and (kind != "use" or hazard not in DEP_HAZARDS):
        raise TaxResultError("Aléa inconnu, ou réservé à une utilisation.", "hazard")
    exempt = 0
    if hazard:
        n = operators(fy)
        cap = (_p("ba.dep.exempt_cap_cents", fy) or 0) * n
        exempt = round(amount * (_p("ba.dep.exempt_rate_bp", fy) or 3000) / 10000)
        exempt = min(exempt, max(cap - _exempt_used(fy), 0))
        if hazard == "economic":
            eco_cap = round(cap * (_p("ba.dep.economic_share_bp", fy) or 4000) / 10000)
            exempt = min(exempt, max(eco_cap - _exempt_used(fy, economic=True), 0))
    row = DepMovement(entry=entry, fiscal_year_id=fy.id, kind=kind, on=on, amount_cents=amount, hazard=hazard,
                      exempt_cents=exempt, reason=(str(data.get("reason") or "").strip()[:300]) or None)
    db.session.add(row)
    db.session.flush()
    return row


def delete_movement(fy: FiscalYear, movement_id) -> None:
    _require_open(fy)
    row = db.session.get(DepMovement, movement_id) if isinstance(movement_id, int) else None
    if row is None or row.fiscal_year_id != fy.id:
        raise TaxResultError("Mouvement introuvable.", status=404)
    db.session.delete(row)
    db.session.flush()


def add_substitute(fy: FiscalYear, data: dict) -> DepSubstitute:
    _require_open(fy)
    label, amount = str(data.get("label") or "").strip()[:200], data.get("amount_cents")
    if not label or isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        raise TaxResultError("Libellé et montant positif attendus.", "amount_cents")
    row = DepSubstitute(fiscal_year_id=fy.id, label=label, amount_cents=amount)
    db.session.add(row)
    db.session.flush()
    return row


def delete_substitute(fy: FiscalYear, substitute_id) -> None:
    _require_open(fy)
    row = db.session.get(DepSubstitute, substitute_id) if isinstance(substitute_id, int) else None
    if row is None or row.fiscal_year_id != fy.id:
        raise TaxResultError("Substitut introuvable.", status=404)
    db.session.delete(row)
    db.session.flush()


# ------------------------------------------------------------------ tableau de passage

def tax_lines(fy: FiscalYear, today: date | None = None) -> list[dict]:
    """Lignes de passage de la DEP pour l'exercice : déduction, réintégrations, 10e exercice, défaut d'épargne."""
    lines = []
    entry = DepEntry.query.filter_by(fiscal_year_id=fy.id).first()
    if entry is not None:
        lines.append({"key": "dep", "source": "dep", "amount_cents": -entry.amount_cents,
                      "label": "Déduction pour épargne de précaution (DEP) de l'exercice"})
    for m in DepMovement.query.filter_by(fiscal_year_id=fy.id).order_by(DepMovement.on, DepMovement.id):
        origin = m.entry.fiscal_year.label if m.entry.fiscal_year else str(m.entry.origin_year)
        taxed = m.amount_cents - m.exempt_cents
        label = f"{DEP_KINDS[m.entry.kind]} {origin} : {DEP_MOVEMENTS[m.kind].lower()}"
        if m.exempt_cents:
            label += f" (dont {m.exempt_cents / 100:.2f} € exonérés, aléa)".replace(".", ",")
        lines.append({"key": f"dep_move_{m.id}", "source": "dep", "amount_cents": taxed, "label": label})
    for e in DepEntry.query.all():
        if _is_deadline(e, fy):
            left = entry_outstanding(e, fy)
            if left > 0:
                origin = e.fiscal_year.label if e.fiscal_year else str(e.origin_year)
                lines.append({"key": f"dep_deadline_{e.id}", "source": "dep", "amount_cents": left,
                              "label": f"{DEP_KINDS[e.kind]} {origin} non utilisée : réintégration au 10e exercice"})
    s = savings(fy, today)
    if s["shortfall_reintegration_cents"]:
        lines.append({"key": "dep_shortfall", "source": "dep", "amount_cents": s["shortfall_reintegration_cents"],
                      "label": "DEP : épargne insuffisante, réintégration de la fraction qui excède le double de l'épargne "
                               "(majorée de l'intérêt de retard)", "to_validate": True})
    return lines


def checks(fy: FiscalYear) -> list[tuple[str, str, int, str]]:
    out = []
    s = savings(fy)
    if s["below"] and s["deadline_passed"]:
        out.append(("dep_savings", f"Épargne DEP insuffisante ({(s['ratio_bp'] or 0) / 100:.0f} % des déductions non rapportées, "
                    "50 % au moins)", 1, "anomaly"))
    elif s["below"]:
        out.append(("dep_savings_due", f"Épargne DEP à constituer avant le {date.fromisoformat(s['deadline']):%d/%m/%Y} "
                    "(50 % au moins des déductions non rapportées)", 1, "info"))
    elif s["above"]:
        out.append(("dep_savings_above", "Épargne DEP au-delà des déductions non rapportées (100 % au plus)", 1, "info"))
    due = [e for e in DepEntry.query.all() if _is_deadline(e, fy) and entry_outstanding(e, fy) > 0]
    if due:
        out.append(("dep_deadline", "DEP ou DPI/DPA arrivées au 10e exercice : réintégration", len(due), "info"))
    return out
