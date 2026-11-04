"""Déclarations de TVA (lot T3, claudedocs/design_societe_tva.md § 3.4-3.5) : CA3 mensuelle ou trimestrielle
(lot AG2.a, claudedocs/design_tva_agricole.md § 5) calculée depuis les lignes codées du grand livre (lot T2).

Périodes : `fiscal_years.vat_period` = `monthly` (clé « 2026-07 ») ou `quarterly` (clé « 2026-T3 », trimestres
civils, échéance le 5 du deuxième mois après le trimestre, reportée au jour ouvré). Remboursement de crédit (3519) : case 26, à partir
de 760 € pour une période, de 150 € sur la dernière de l'année ; débit 44583 dans la liquidation.

CA12A / CA12AE (lot AG2.b, design § 3) : `vat_period = annual` ; formulaire 3517-AGR-SD (`data/ca12a/`), période
civile (clé « 2026-A ») ou exercice si l'option `rsa_fiscal_year` est enregistrée (clé « 2025-07-A ») ; crédit
antérieur ligne 19, acomptes ligne 25 (déclarations « ACOMPTE », lot AG2.c), cadres VI et VII.

- **Lignes retenues** pour un mois : lignes codées des écritures datées jusqu'à la fin du mois, pas
  encore déclarées (`vat_return_id` nul), hors TVA en attente (44574). Un mois non déclaré reprend donc
  les pièces des mois précédents saisies après coup.
- **Cases** : correspondance code → case dans `data/ca3/<année>.json`, arrondies à l'euro ; totaux
  recalculés sur les cases arrondies, comme le formulaire ; crédit du mois précédent en case 22.
- **Valider** : écritures en brouillard du mois validées, cases figées, lignes rattachées, écriture de
  **liquidation** (journal OD, source gérée `VAT_RETURN`) : comptes de TVA soldés, TVA due en 44551 ou
  crédit en 44567, écart d'arrondi en 658 / 758. Seule la dernière déclaration non déposée s'annule.
- **Déclarée** (dépôt sur TeleDEC) : liquidation validée, mois verrouillé (lot F2).

Montants : les lignes de taxe sont signées par leur sens (avoir, contrepassation : négatif) ; la base
suit le signe de la taxe (`vat_codes`).
"""
from __future__ import annotations

import calendar
import json
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path

from app.extensions import db
from app.models import Account, FiscalYear, Journal, JournalEntry, JournalLine, Organization, VatReturn
from app.models.journal_entry import SOURCE_OPENING, SOURCE_VAT_RETURN
from app.services import account_roles, vat_codes
from app.services.ledger_errors import LedgerError

DATA_ROOT = Path(__file__).resolve().parents[2] / "data"
FORM = "CA3"
CA12A = "CA12A"
INSTALLMENT = "ACOMPTE"
FORM_DIRS = {FORM: "ca3", CA12A: "ca12a"}
ON_RECEIPTS = "44574"          # TVA collectée en attente : déclarée à l'encaissement
DEFAULT_DUE_DAY = 24           # dernier jour possible fixé par le SIE (du 15 au 24)
RATE_TOLERANCE_CENTS = 100     # écart toléré entre la taxe et base × taux, par ligne
VAT_ACCOUNTS = ("4452", "4453", "4456", "4457")
REVERSAL_BOX = "15"            # TVA déduite à reverser : avoirs reçus des fournisseurs
MONTHLY, QUARTERLY, ANNUAL = "monthly", "quarterly", "annual"
PERIODS = (MONTHLY, QUARTERLY, ANNUAL)
INSTALLMENTS_ACCOUNT = "44581"  # acomptes du régime simplifié
REFUND_ACCOUNT = "44583"       # remboursement de taxes sur le chiffre d'affaires demandé


class VatReturnError(LedgerError):
    def __init__(self, message, field=None, status=409, problems=None):
        super().__init__(message)
        self.field = field
        self.status = status
        self.problems = problems or []


# ------------------------------------------------------------------ formulaire et périodes

@lru_cache(maxsize=16)
def form_spec(year: int, form: str = FORM) -> dict:
    """Formulaire `form` du millésime `year`, sinon le plus récent qui le précède."""
    directory = DATA_ROOT / FORM_DIRS[form]
    years = sorted(int(p.stem) for p in directory.glob("*.json") if p.stem.isdigit())
    usable = [y for y in years if y <= year] or years[:1]
    if not usable:
        raise VatReturnError(f"Aucun formulaire de déclaration de TVA (data/{FORM_DIRS[form]}).")
    spec = json.loads((directory / f"{usable[-1]}.json").read_text(encoding="utf-8"))
    spec["year"] = usable[-1]
    return spec


def month_bounds(start: date) -> tuple[date, date]:
    first = start.replace(day=1)
    return first, first.replace(day=calendar.monthrange(first.year, first.month)[1])


def quarter_bounds(day: date) -> tuple[date, date]:
    first = date(day.year, 3 * ((day.month - 1) // 3) + 1, 1)
    last_month = first.month + 2
    return first, date(first.year, last_month, calendar.monthrange(first.year, last_month)[1])


def kind_of(day: date) -> str:
    """Rythme de déclaration de l'exercice qui couvre `day` (mensuel par défaut)."""
    fy = fiscal_year_for(day)
    return fy.vat_period if fy is not None and fy.vat_period in PERIODS else MONTHLY


def _fiscal_year_option(day: date) -> bool:
    """Option CA12AE : déclaration annuelle sur l'exercice (code `rsa_fiscal_year`, non dénoncée)."""
    from app.models import TaxOption
    return TaxOption.query.filter(TaxOption.code == "rsa_fiscal_year", TaxOption.start_date <= day,
                                  db.or_(TaxOption.renounced_on.is_(None), TaxOption.renounced_on > day)).first() is not None


def annual_bounds(day: date) -> tuple[date, date]:
    fy = fiscal_year_for(day)
    if fy is not None and _fiscal_year_option(fy.start_date):
        return fy.start_date, fy.end_date
    return date(day.year, 1, 1), date(day.year, 12, 31)


def bounds(day: date, kind: str | None = None) -> tuple[date, date]:
    kind = kind or kind_of(day)
    if kind == ANNUAL:
        return annual_bounds(day)
    return quarter_bounds(day) if kind == QUARTERLY else month_bounds(day)


def form_for(day: date) -> str:
    """Formulaire de la période qui contient `day` : CA12A au rythme annuel, CA3 sinon."""
    return CA12A if kind_of(day) == ANNUAL else FORM


def _is_annual(start: date, end: date) -> bool:
    return (end - start).days > 100


def parse_period(text: str | None) -> tuple[date, date]:
    """« 2026-07 » → (1er juillet, 31 juillet) ; « 2026-T3 » → (1er juillet, 30 septembre) ; « 2026-A » → année
    civile ; « 2025-07-A » → exercice commençant en juillet 2025 (CA12AE)."""
    raw = str(text or "").strip().upper()
    try:
        if raw.endswith("-A"):
            parts = raw[:-2].split("-")
            if len(parts) == 1:
                year = int(parts[0])
                return date(year, 1, 1), date(year, 12, 31)
            fy = FiscalYear.query.filter_by(start_date=date(int(parts[0]), int(parts[1]), 1)).first()
            if fy is None:
                raise ValueError
            return fy.start_date, fy.end_date
        year, rest = raw.split("-")[:2]
        if rest.startswith("T"):
            quarter = int(rest[1:])
            if not 1 <= quarter <= 4:
                raise ValueError
            return quarter_bounds(date(int(year), 3 * quarter - 2, 1))
        return month_bounds(date(int(year), int(rest), 1))
    except (TypeError, ValueError):
        raise VatReturnError("Période attendue sous la forme AAAA-MM, AAAA-T1 à T4, AAAA-A ou AAAA-MM-A (exercice).",
                             "period", status=422) from None


def period_key(start: date, end: date | None = None) -> str:
    if end is not None and _is_annual(start, end):
        return f"{start.year}-A" if (start.month, start.day, end.month, end.day) == (1, 1, 12, 31) else f"{start:%Y-%m}-A"
    if end is not None and (end - start).days > 31:
        return f"{start.year}-T{(start.month - 1) // 3 + 1}"
    return f"{start:%Y-%m}"


def period_label(start: date, end: date) -> str:
    """« 07/2026 », « T3 2026 », « 2026 » (année civile) ou « exercice 2025-2026 »."""
    if _is_annual(start, end):
        civil = (start.month, start.day, end.month, end.day) == (1, 1, 12, 31)
        return str(start.year) if civil else f"exercice {start.year}-{end.year}"
    if (end - start).days > 31:
        return f"T{(start.month - 1) // 3 + 1} {start.year}"
    return f"{start:%m/%Y}"


def _period_word(start: date, end: date) -> str:
    if _is_annual(start, end):
        return "exercice"
    return "trimestre" if (end - start).days > 31 else "mois"


def _this(word: str) -> str:
    return "cet exercice" if word == "exercice" else f"ce {word}"


def _end_of(word: str) -> str:
    return "la fin de l'exercice" if word == "exercice" else f"la fin du {word}"


def deadline(period_end: date) -> date:
    """Échéance. Mensuelle : jour fixé par le SIE (Structure), le mois suivant. Trimestrielle (RSA) : le 5 du
    deuxième mois après le trimestre (5 mai, 5 août, 5 novembre, 5 février ; paramètre `vat.rsa.quarterly_due_day`),
    reportée au premier jour ouvré."""
    year, month = (period_end.year + 1, 1) if period_end.month == 12 else (period_end.year, period_end.month + 1)
    if kind_of(period_end) == ANNUAL:
        # CA12A : 2e jour ouvré après le 1er mai de N+1 ; CA12AE : 5e jour du 5e mois après la clôture.
        from app.services import fr_calendar
        if (period_end.month, period_end.day) == (12, 31):
            return fr_calendar.nth_working_day_after(date(period_end.year + 1, 5, 1), 2)
        month_index = period_end.month + 5
        return fr_calendar.next_working_day(date(period_end.year + (month_index - 1) // 12, (month_index - 1) % 12 + 1, 5))
    if kind_of(period_end) == QUARTERLY:
        from app.services import fr_calendar, reg_params
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        day = reg_params.value("vat.rsa.quarterly_due_day", period_end, default=5)
        return fr_calendar.next_working_day(date(year, month, day))
    org = Organization.query.first()
    day = (org.vat_due_day if org is not None and org.vat_due_day else None) or DEFAULT_DUE_DAY
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def fiscal_year_for(day: date) -> FiscalYear | None:
    return FiscalYear.query.filter(FiscalYear.start_date <= day, FiscalYear.end_date >= day).first()


def declaring_years():
    return FiscalYear.query.filter(FiscalYear.vat_period.isnot(None)).order_by(FiscalYear.start_date.desc()).all()


def return_for(start: date, form: str | None = None) -> VatReturn | None:
    return VatReturn.query.filter_by(period_start=start, form=form or form_for(start)).first()


def _previous_period(start: date) -> date:
    """Début de la période précédente, au rythme de l'exercice qui la couvre."""
    day = start - timedelta(days=1)
    return bounds(day)[0]


def periods(fy: FiscalYear, today: date | None = None) -> list[dict]:
    """Périodes (mois ou trimestres) de l'exercice : déclaration enregistrée ou non, échéance et retard."""
    today = today or date.today()
    kind = fy.vat_period if fy.vat_period in PERIODS else MONTHLY
    rows, start = [], bounds(fy.start_date, kind)[0]
    while start <= fy.end_date:
        _, end = bounds(start, kind)
        ret = return_for(start)
        due = ret.deadline if ret is not None and ret.deadline else deadline(end)
        status = ret.status if ret is not None else ("in_progress" if end >= today else "to_prepare")
        rows.append({"period": period_key(start, end), "label": period_label(start, end), "start": start, "end": end,
                     "deadline": due, "status": status,
                     "late": (ret is None or ret.status != "declared") and end < today and due < today,
                     "return": ret})
        start = end + timedelta(days=1)
    return rows


# ------------------------------------------------------------------ lignes et montants

def _role(code: str) -> str:
    """Rôle d'une ligne d'après son compte : taxe collectée, due (autoliquidation), déductible, ou base."""
    if code.startswith("4457"):
        return "collected"
    if code.startswith(("4452", "4453")):
        return "due"
    if code.startswith("4456"):
        return "deductible"
    return "base"


def retained_lines(start: date, end: date):
    """Lignes codées non déclarées des écritures datées jusqu'à `end` (hors 44574)."""
    return (JournalLine.query.join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
            .join(Account, Account.id == JournalLine.account_id)
            .filter(JournalLine.vat_code.isnot(None), JournalLine.vat_return_id.is_(None),
                    JournalEntry.entry_date <= end, ~Account.code.like(f"{ON_RECEIPTS}%"))
            .order_by(JournalEntry.entry_date, JournalLine.id))


def _signed(line: JournalLine) -> tuple[str, int, int]:
    """(rôle, montant signé, base signée) d'une ligne retenue."""
    role = _role(line.account.code or "")
    amount = line.debit_cents - line.credit_cents if role == "deductible" else line.credit_cents - line.debit_cents
    if role == "base":
        return role, amount, amount
    base = line.vat_base_cents or 0
    return role, amount, -base if amount < 0 else base


def _euros(cents: int) -> int:
    return int((Decimal(cents) / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def credit_note_entries(lines) -> set[int]:
    """Écritures d'avoirs reçus des fournisseurs parmi celles des lignes : leur TVA déductible est reversée
    ligne 15 (notice de la CA3), au lieu de réduire les lignes 19-20."""
    from app.models import Purchase
    ids = {line.entry_id for line in lines}
    if not ids:
        return set()
    return {row[0] for row in db.session.query(Purchase.journal_entry_id).filter(
        Purchase.is_credit_note.is_(True), Purchase.journal_entry_id.in_(ids))}


def _box_targets(spec: dict, line: JournalLine, credit_notes=frozenset(),
                 reversal_box: str = REVERSAL_BOX) -> list[tuple[str, str, str]]:
    """Cases alimentées par une ligne : [(case, colonne, valeur)] ; colonne `base`, `tax` ou `amount`
    (case à un seul montant) ; valeur `base` (base HT), `amount` (taxe de la ligne) ou `reversal` (taxe
    déductible d'un avoir reçu, reversée : son opposé)."""
    mapping = spec["codes"].get(line.vat_code)
    if mapping is None:
        return []
    role = _role(line.account.code or "")
    if role == "deductible" and mapping.get("deductible") and line.entry_id in credit_notes:
        return [(reversal_box, "amount", "reversal")]
    with_base = {box["line"] for section in spec["sections"] for box in section["boxes"] if box.get("with_base")}
    targets = []
    if role in ("collected", "due", "base"):
        for box in mapping.get("base", []):
            targets.append((box, "base" if box in with_base else "amount", "base"))
    if role in ("collected", "due") and mapping.get("tax"):
        targets.append((mapping["tax"], "tax", "amount"))
        targets += [(box, "amount", "amount") for box in mapping.get("also", [])]
    if role == "deductible" and mapping.get("deductible"):
        lines = spec["deductible_lines"]
        box = lines.get("44562") if (line.account.code or "").startswith("44562") else lines["default"]
        targets.append((box, "amount", "amount"))
        targets += [(box, "amount", "amount") for box in mapping.get("deductible_also", [])]
    return targets


def _credit_carried(start: date, form: str = FORM) -> int:
    """Case 22 de la CA3 ou ligne 19 de la CA12A (centimes) : crédit à reporter de la déclaration précédente ; la
    première, solde débiteur de 44567 dans les à-nouveaux de l'exercice."""
    previous = (VatReturn.query.filter(VatReturn.form == form, VatReturn.period_end < start)
                .order_by(VatReturn.period_end.desc()).first())
    if previous is not None:
        return previous.credit_cents
    fy = fiscal_year_for(start)
    if fy is None:
        return 0
    balance = (db.session.query(db.func.coalesce(db.func.sum(JournalLine.debit_cents - JournalLine.credit_cents), 0))
               .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
               .join(Account, Account.id == JournalLine.account_id)
               .filter(JournalEntry.fiscal_year_id == fy.id, JournalEntry.source == SOURCE_OPENING,
                       Account.code.like("44567%")).scalar())
    return max(int(balance or 0), 0)


def installments_paid(start: date, end: date) -> int:
    """Acomptes (centimes) de la période annuelle, validés ou déposés (lot AG2.c) : ligne 25 de la CA12A."""
    return int(db.session.query(db.func.coalesce(db.func.sum(VatReturn.due_cents), 0)).filter(
        VatReturn.form == INSTALLMENT, VatReturn.period_start >= start, VatReturn.period_end <= end).scalar() or 0)


def _ca12a_totals(boxes: dict, start: date, end: date, refund_cents: int, extra: dict) -> dict:
    """Lignes 15 à 46 de la CA12A, en euros, sur les lignes arrondies (règles de la notice)."""
    from app.services import reg_params

    amount = lambda line: boxes.get(line, {}).get("amount", 0)  # noqa: E731
    with_base = ("04", "5A", "5C", "09", "I1", "I2", "I4", "I5", "9C", "12", "13")
    gross = sum(boxes.get(line, {}).get("tax", 0) for line in with_base) + amount("14") + amount("4B")
    carried = _euros(_credit_carried(start, CA12A))
    deductible = amount("17") + amount("18") + carried + amount("20") + amount("2B")
    due, credit = max(gross - deductible, 0), max(deductible - gross, 0)
    paid = _euros(installments_paid(start, end))
    balance_due, excess = max(due - credit - paid, 0), max(paid - due, 0) if not credit else paid
    surplus = credit + excess
    minimum = _euros(reg_params.value("vat.rsa.refund_min_annual_cents", end, default=15000))
    refundable_credit = credit if credit >= minimum else 0
    maximum = refundable_credit + excess
    refund = min(_euros(refund_cents), maximum)
    tca = int(extra.get("31") or 0)
    boxes.update({"15": {"amount": gross}, "19": {"amount": carried}, "21": {"amount": deductible},
                  "23": {"amount": due}, "24": {"amount": credit}, "25": {"amount": paid},
                  "28": {"amount": balance_due}, "29": {"amount": excess}, "30": {"amount": surplus},
                  "31": {"amount": tca}, "36": {"amount": surplus}, "37": {"amount": refund},
                  "38": {"amount": surplus - refund}, "39": {"amount": balance_due}, "40": {"amount": tca},
                  "41": {"amount": balance_due + tca}, "42": {"amount": refundable_credit}, "43": {"amount": excess},
                  "44": {"amount": maximum}, "45": {"amount": refund}, "46": {"amount": maximum - refund}})
    return {"carried": carried * 100, "due": balance_due, "credit": surplus - refund, "refund": refund,
            "paid": paid * 100, "maximum": maximum, "gross_credit": surplus, "advice": excess > (4 * due) / 5 and excess > 0}


def compute(start: date, end: date, lines=None, refund_cents: int = 0, extra: dict | None = None) -> dict:
    """Cases de la CA3 de la période : `boxes` {case: {base?, tax?, amount?} en euros}, `rows` (ordre du
    formulaire), détail par code (centimes), crédit reporté, TVA due ou crédit ; remboursement demandé (case 26,
    euros entiers) déduit du crédit à reporter (case 27)."""
    form = CA12A if _is_annual(start, end) else FORM
    spec = form_spec(end.year, form)
    reversal_box = spec.get("reversal_line", REVERSAL_BOX)
    lines = list(retained_lines(start, end)) if lines is None else lines
    credit_notes = credit_note_entries(lines)
    cents: dict[str, dict[str, int]] = {}
    codes: dict[str, dict[str, int]] = {}
    reverse_charge: dict[str, int] = {}   # case → TVA autoliquidée (due ou déduite), centimes
    for line in lines:
        role, amount, base = _signed(line)
        detail = codes.setdefault(line.vat_code, {"base": 0, "tax": 0, "deductible": 0})
        if role == "deductible":
            detail["deductible"] += amount
        elif role == "base":
            detail["base"] += base
        else:
            detail["base"] += base
            detail["tax"] += amount
        for box, column, source in _box_targets(spec, line, credit_notes, reversal_box):
            value = base if source == "base" else -amount if source == "reversal" else amount
            cell = cents.setdefault(box, {})
            cell[column] = cell.get(column, 0) + value
            if (line.vat_code or "").startswith("AL_") and source == "amount" and column in ("tax", "amount") \
                    and box not in ("17", "24"):
                reverse_charge[box] = reverse_charge.get(box, 0) + value
    boxes = {box: {column: _euros(value) for column, value in cell.items()} for box, cell in cents.items()}
    if form == CA12A:
        totals = _ca12a_totals(boxes, start, end, refund_cents, extra or {})
        return _result(spec, form, start, end, boxes, codes, lines, {}, totals["carried"], totals["due"],
                       totals["credit"], totals["refund"], totals["gross_credit"],
                       {"installments_cents": totals["paid"], "refund_max_cents": totals["maximum"] * 100,
                        "refund_min_cents": 0, "refund_advice": totals["advice"]})
    with_base = [box["line"] for section in spec["sections"] for box in section["boxes"] if box.get("with_base")]
    carried = _credit_carried(start)
    gross = sum(boxes.get(box, {}).get("tax", 0) for box in with_base) + boxes.get(REVERSAL_BOX, {}).get("amount", 0)
    boxes["16"] = {"amount": gross}
    boxes["22"] = {"amount": _euros(carried)}
    deductible = sum(boxes.get(box, {}).get("amount", 0) for box in ("19", "20", "22"))
    boxes["23"] = {"amount": deductible}
    due, credit = max(gross - deductible, 0), max(deductible - gross, 0)
    refund = min(_euros(refund_cents), credit)
    boxes.update({"TD": {"amount": due}, "28": {"amount": due}, "32": {"amount": due},
                  "25": {"amount": credit}, "26": {"amount": refund}, "27": {"amount": credit - refund}})
    return _result(spec, form, start, end, boxes, codes, lines, reverse_charge, carried, due, credit - refund, refund,
                   credit, {"refund_max_cents": credit * 100, "refund_min_cents": None})


def _result(spec, form, start, end, boxes, codes, lines, reverse_charge, carried, due, credit, refund, gross_credit,
            extra) -> dict:
    notes = reverse_charge_notes(reverse_charge)
    rows = []
    for section in spec["sections"]:
        rows.append({"kind": "section", "label": section["title"]})
        for box in section["boxes"]:
            values = boxes.get(box["line"], {})
            row = {"kind": "total" if box.get("total") else "box", "line": box["line"], "code": box["code"],
                   "label": box["label"], "with_base": bool(box.get("with_base")),
                   "base": values.get("base", 0) if box.get("with_base") else None,
                   "amount": values.get("tax", 0) if box.get("with_base") else values.get("amount", 0)}
            if box["line"] in notes:
                row["note"] = notes[box["line"]]
            rows.append(row)
    return {"period": period_key(start, end), "label": period_label(start, end), "start": start, "end": end,
            "form": spec["form"], "form_code": form, "form_year": spec["year"],
            "boxes": boxes, "rows": rows, "codes": codes, "credit_carried_cents": carried,
            "due_cents": due * 100, "credit_cents": credit * 100, "refund_cents": refund * 100,
            "gross_credit_cents": gross_credit * 100, "lines_count": len(lines), **extra,
            "reverse_charge_cents": sum(v for b, v in reverse_charge.items() if b not in DEDUCTIBLE_BOXES)}


DEDUCTIBLE_BOXES = ("19", "20")


def _fmt(cents: int) -> str:
    return f"{cents / 100:,.2f} €".replace(",", "\u202f").replace(".", ",")


def reverse_charge_notes(reverse_charge: dict[str, int]) -> dict[str, str]:
    """Mentions sous les lignes qui portent de la TVA autoliquidée : due d'un côté, déduite de l'autre,
    sans effet sur la TVA nette (au droit à déduction près)."""
    due = {b: v for b, v in reverse_charge.items() if b not in DEDUCTIBLE_BOXES and v}
    deducted = {b: v for b, v in reverse_charge.items() if b in DEDUCTIBLE_BOXES and v}
    notes = {}
    for box, value in due.items():
        notes[box] = f"dont {_fmt(value)} de TVA autoliquidée, déduite ligne {' / '.join(deducted) or '20'}"
    for box, value in deducted.items():
        notes[box] = f"dont {_fmt(value)} de TVA autoliquidée, due ligne {' / '.join(due) or '08'} : sans effet sur la TVA nette"
    return notes


def lines_for(start: date, end: date, box: str, vat_return: VatReturn | None = None) -> list[JournalLine]:
    """Lignes qui composent une case (R4.4) : celles de la déclaration figée, sinon les lignes retenues."""
    form = CA12A if _is_annual(start, end) else FORM
    spec = form_spec(end.year, form)
    reversal = spec.get("reversal_line", REVERSAL_BOX)
    query = (JournalLine.query.filter(JournalLine.vat_return_id == vat_return.id) if vat_return is not None
             else retained_lines(start, end))
    lines = list(query)
    credit_notes = credit_note_entries(lines)
    return [line for line in lines
            if any(target == box for target, _c, _s in _box_targets(spec, line, credit_notes, reversal))]


# ------------------------------------------------------------------ contrôles

def _previous_missing(start: date) -> date | None:
    """Période précédente à déclarer d'abord (exercice déclarant, sans déclaration enregistrée)."""
    previous = _previous_period(start)
    fy = fiscal_year_for(previous)
    if fy is not None and fy.vat_period and form_for(previous) == form_for(start) and return_for(previous) is None:
        return previous
    return None


def checks(start: date, end: date, lines=None, today: date | None = None) -> list[dict]:
    """Contrôles avant validation : `error` (bloquant) ou `warning`."""
    today = today or date.today()
    found = []

    def add(level, message, count=None):
        found.append({"level": level, "message": message, "count": count})

    fy = fiscal_year_for(start)
    if fy is None or not fy.vat_period:
        add("error", "L'exercice de cette période ne déclare pas la TVA (réglage de l'exercice).")
    elif fy.closed:
        add("error", f"L'exercice « {fy.label} » est clôturé.")
    word = _period_word(start, end)
    missing = _previous_missing(start)
    if missing is not None:
        label = period_label(*bounds(missing))
        add("error", f"Validez d'abord la déclaration de {label} : son crédit se reporte sur {_this(word)}.")
    if end >= today:
        add("warning", f"{'L' + chr(39) + 'exercice' if word == 'exercice' else 'Le ' + word} n'est pas terminé : "
            "d'autres pièces peuvent encore arriver.")
    lines = list(retained_lines(start, end)) if lines is None else lines
    drafts = {line.entry_id for line in lines if line.entry.validation_number is None}
    if fy is not None:
        drafts |= {e.id for e in JournalEntry.query.filter(
            JournalEntry.fiscal_year_id == fy.id, JournalEntry.validation_number.is_(None),
            JournalEntry.entry_date <= end, JournalEntry.entry_date >= start)}
    if drafts:
        add("warning", f"Écritures en brouillard jusqu'à {_end_of(word)} : elles seront validées avec la déclaration.",
            len(drafts))
    uncoded = (JournalLine.query.join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
               .join(Account, Account.id == JournalLine.account_id)
               .filter(JournalLine.vat_code.is_(None), JournalEntry.entry_date.between(start, end),
                       db.or_(*[Account.code.like(f"{prefix}%") for prefix in VAT_ACCOUNTS]),
                       ~Account.code.like(f"{ON_RECEIPTS}%"), JournalEntry.source != SOURCE_VAT_RETURN).count())
    if uncoded:
        add("warning", "Lignes de TVA sans code de TVA : elles ne sont pas déclarées (code à ajouter sur l'écriture).",
            uncoded)
    inconsistent = 0
    for line in lines:
        role, amount, base = _signed(line)
        rate = vat_codes.codes().get(line.vat_code, {}).get("rate_bp", 0)
        if role != "base" and rate and abs(amount - round(base * rate / 10000)) > RATE_TOLERANCE_CENTS:
            inconsistent += 1
    if inconsistent:
        add("warning", "Taxe différente de base × taux (plus d'un euro d'écart) : vérifiez la base ou le code.",
            inconsistent)
    imports = {line.entry_id for line in lines if (line.vat_code or "").startswith("AL_I")}
    if imports:
        add("warning", "Importations : comparez les lignes A4 et I1 à I5 aux montants préremplis par la douane. La base "
            "comprend les droits de douane et les frais jusqu'au premier lieu de destination (ligne à ajouter sur la "
            "facture d'import s'ils manquent).", len(imports))
    earlier = sum(1 for line in lines if line.entry.entry_date < start)
    if earlier:
        add("warning", f"Pièces de {'mois' if word == 'mois' else word + 's'} précédents saisies après leur déclaration : "
            f"reprises dans {_this(word)}.", earlier)
    return found


def preview(start: date, end: date) -> dict:
    lines = list(retained_lines(start, end))
    result = compute(start, end, lines)
    found = checks(start, end, lines)
    if result["form_code"] == CA12A:  # lot AG2.c : acomptes échus non enregistrés, absents de la ligne 25
        from app.services import vat_installments
        late = vat_installments.missing(start, end)
        if late:
            found.append({"level": "warning", "count": len(late), "message": "Acompte" + ("s" if len(late) > 1 else "")
                          + " n° " + ", ".join(str(i["number"]) for i in late) + " non enregistré" + ("s" if len(late) > 1 else "")
                          + " (Déclarations de TVA, acomptes) : la ligne 25 ne reprend que les acomptes enregistrés."})
    if result.get("refund_advice"):
        found.append({"level": "warning", "count": None, "message": "Excédent de versement supérieur aux 4/5 de la TVA "
                      "due : son remboursement immédiat est conseillé (notice 3517-AGR, cadre VII)."})
    return {**result, "checks": found, "deadline": deadline(end)}


# ------------------------------------------------------------------ validation et liquidation

def _journal() -> Journal:
    journal = Journal.query.filter_by(code="OD").first()
    if journal is None:
        journal = Journal(code="OD", label="Opérations diverses")
        db.session.add(journal)
        db.session.flush()
    return journal


def _rounding_account(expense: bool) -> Account:
    try:
        return account_roles.account_for("vat_rounding_expense" if expense else "vat_rounding_income")
    except account_roles.RoleError:
        return account_roles.account_for("lettering_gap_expense" if expense else "lettering_gap_income")


def _role_account(role: str, fallback: str) -> Account:
    try:
        return account_roles.account_for(role)
    except account_roles.RoleError:
        return vat_codes.account(fallback)


def liquidation_lines(lines, result: dict, label: str) -> list[dict]:
    """Comptes de TVA des lignes retenues soldés, crédit reporté repris, TVA due (44551) ou crédit (44567),
    écart d'arrondi en 658 / 758."""
    balances: dict[int, int] = {}
    for line in lines:
        if _role(line.account.code or "") != "base":
            balances[line.account_id] = balances.get(line.account_id, 0) + line.credit_cents - line.debit_cents
    out = []
    for account_id, balance in sorted(balances.items()):
        if balance:
            out.append({"account_id": account_id, "label": label, "debit_cents": max(balance, 0),
                        "credit_cents": max(-balance, 0)})
    credit_account = _role_account("vat_credit", "44567")
    if result["credit_carried_cents"]:
        out.append({"account_id": credit_account.id, "label": f"{label} — crédit reporté", "debit_cents": 0,
                    "credit_cents": result["credit_carried_cents"]})
    if result["due_cents"]:
        out.append({"account_id": _role_account("vat_payable", "44551").id, "label": f"{label} — TVA à décaisser",
                    "debit_cents": 0, "credit_cents": result["due_cents"]})
    if result["credit_cents"]:
        out.append({"account_id": credit_account.id, "label": f"{label} — crédit à reporter",
                    "debit_cents": result["credit_cents"], "credit_cents": 0})
    if result.get("refund_cents"):
        out.append({"account_id": vat_codes.account(REFUND_ACCOUNT).id, "label": f"{label} — remboursement demandé",
                    "debit_cents": result["refund_cents"], "credit_cents": 0})
    if result.get("installments_cents"):  # CA12A : acomptes versés imputés (ligne 25)
        out.append({"account_id": vat_codes.account(INSTALLMENTS_ACCOUNT).id, "label": f"{label} — acomptes versés",
                    "debit_cents": 0, "credit_cents": result["installments_cents"]})
    gap = sum(l["debit_cents"] for l in out) - sum(l["credit_cents"] for l in out)
    if gap:
        account = _rounding_account(expense=gap < 0)
        out.append({"account_id": account.id, "label": f"{label} — arrondi à l'euro",
                    "debit_cents": max(-gap, 0), "credit_cents": max(gap, 0)})
    return out


def refund_problem(start: date, end: date, refund_cents: int, gross_credit_cents: int,
                   maximum_cents: int | None = None) -> str | None:
    """Remboursement de crédit demandé. CA3 (3519) : au plus le crédit, au moins 760 € pour une période, 150 € sur la
    dernière période de l'année civile (paramètres `vat.rsa.refund_min_*`). CA12A (cadre VII) : au plus la ligne 44
    (crédit d'au moins 150 € et excédent de versement)."""
    if not refund_cents:
        return None
    from app.services import reg_params
    if refund_cents < 0 or refund_cents % 100:
        return "Remboursement en euros entiers, positif."
    if _is_annual(start, end):
        if refund_cents > (maximum_cents or 0):
            return "Le remboursement dépasse le maximum remboursable (ligne 44 : crédit d'au moins 150 € et excédent de versement)."
        return None
    if refund_cents > gross_credit_cents:
        return "Le remboursement dépasse le crédit de la période."
    annual = end.month == 12
    key = "vat.rsa.refund_min_annual_cents" if annual else "vat.rsa.refund_min_period_cents"
    minimum = reg_params.value(key, end, default=15000 if annual else 76000)
    if refund_cents < minimum:
        return (f"Remboursement d'au moins {minimum // 100} € "
                f"{'sur la dernière période de l’année' if annual else 'en cours d’année'} (formulaire 3519).")
    return None


def validate(start: date, end: date, user_id=None, refund_cents: int = 0, extra: dict | None = None) -> VatReturn:
    """Valide la déclaration de la période (sans commit) ; VatReturnError si un contrôle bloque. `extra` : saisies
    libres de la CA12A (ligne 31, euros)."""
    from app.services import validation
    from app.services.ledger import post_entry

    label = period_label(start, end)
    if return_for(start) is not None:
        raise VatReturnError(f"La déclaration de {label} est déjà validée.")
    blocking = [c for c in checks(start, end) if c["level"] == "error"]
    if blocking:
        raise VatReturnError(blocking[0]["message"], problems=[c["message"] for c in blocking])
    fy = fiscal_year_for(start)
    form = form_for(start)
    # Une CA12A civile d'un exercice décalé couvre deux exercices : brouillards validés dans chacun.
    years = {y.id: y for y in (fy, fiscal_year_for(end)) if y is not None}
    try:
        for year in years.values():
            validation.validate(year, validation.drafts(year, end).all(), "vat", user_id, until=min(end, year.end_date))
    except validation.ValidationError as exc:
        raise VatReturnError(str(exc), problems=exc.problems) from None
    lines = list(retained_lines(start, end))
    result = compute(start, end, lines, refund_cents, extra)
    problem = refund_problem(start, end, refund_cents, result["gross_credit_cents"], result.get("refund_max_cents"))
    if problem:
        raise VatReturnError(problem, "refund", status=422)
    entry_fy = fiscal_year_for(end) or fy
    ret = VatReturn(fiscal_year_id=entry_fy.id, period_start=start, period_end=end, form=form, status="validated",
                    boxes_json=json.dumps({"form": result["form"], "form_year": result["form_year"], "boxes": result["boxes"],
                                           "rows": result["rows"], "codes": result["codes"]}, ensure_ascii=False),
                    credit_carried_cents=result["credit_carried_cents"], due_cents=result["due_cents"],
                    credit_cents=result["credit_cents"], refund_cents=result["refund_cents"],
                    deadline=deadline(end), validated_at=datetime.utcnow(),
                    validated_by_user_id=user_id)
    db.session.add(ret)
    db.session.flush()
    for line in lines:
        line.vat_return_id = ret.id
    entry_lines = liquidation_lines(lines, result, f"TVA {label}")
    if entry_lines:
        entry = post_entry(entry_fy.id, _journal().id, end, f"Liquidation de la TVA — {form} {label}", entry_lines,
                           source=SOURCE_VAT_RETURN, source_ref=f"VAT_RETURN:{ret.id}", commit=False)
        ret.liquidation_entry_id = entry.id
    db.session.flush()
    return ret


def last_return(form: str = FORM) -> VatReturn | None:
    return VatReturn.query.filter_by(form=form).order_by(VatReturn.period_end.desc()).first()


def unvalidate(ret: VatReturn) -> None:
    """Annule la dernière déclaration non déposée : lignes libérées, liquidation supprimée (brouillard) ou
    contrepassée (validée) ; sans commit."""
    from app.services.ledger import delete_entries, post_entry

    if ret.status == "declared":
        raise VatReturnError("Déclaration déposée : elle ne s'annule plus (régularisez sur une déclaration suivante).")
    if last_return(ret.form) is not ret:
        raise VatReturnError("Seule la dernière déclaration s'annule.")
    if ret.form == INSTALLMENT:  # lot AG2.c : acomptes figés par la CA12A qui les impute (ligne 25)
        start, end = annual_bounds(ret.period_start)
        if return_for(start, CA12A) is not None:
            raise VatReturnError(f"La CA12A {period_label(start, end)} impute cet acompte : annulez-la d'abord.")
    entry = ret.liquidation_entry
    for line in JournalLine.query.filter_by(vat_return_id=ret.id):
        line.vat_return_id = None
    if entry is not None:
        if entry.validation_number is None:
            (outcome,) = delete_entries([entry.id], allow_managed=True)
            if outcome["status"] != "ok":
                raise VatReturnError(outcome["message"])
        else:
            inverse = [{"account_id": l.account_id, "label": l.label, "debit_cents": l.credit_cents,
                        "credit_cents": l.debit_cents} for l in entry.lines]
            post_entry(entry.fiscal_year_id, entry.journal_id, ret.period_end,
                       f"Annulation de la liquidation — {ret.form} {period_label(ret.period_start, ret.period_end)}", inverse,
                       source=SOURCE_VAT_RETURN, source_ref=f"VAT_RETURN_CANCEL:{ret.id}", commit=False)
    db.session.delete(ret)
    db.session.flush()


def declare(ret: VatReturn, declared_on: date, reference: str | None = None, user_id=None) -> None:
    """Dépôt sur TeleDEC : liquidation validée, mois verrouillé ; dans l'ordre des mois (sans commit). Acompte
    (lot AG2.c) : paiement fait, écriture validée, période non verrouillée."""
    from app.services import period_lock, validation

    if ret.status == "declared":
        raise VatReturnError("Déclaration déjà déposée.")
    earlier = (VatReturn.query.filter(VatReturn.form == ret.form, VatReturn.period_end < ret.period_start,
                                      VatReturn.status != "declared").first())
    if earlier is not None:
        raise VatReturnError(f"Déposez d'abord la déclaration de {period_label(earlier.period_start, earlier.period_end)}.")
    if not isinstance(declared_on, date) or declared_on < ret.period_end:
        raise VatReturnError(f"Date de dépôt invalide (après la fin du {_period_word(ret.period_start, ret.period_end)}).",
                             "declared_on", status=422)
    fy = ret.fiscal_year
    entry = ret.liquidation_entry
    if entry is not None and entry.validation_number is None:
        validation.validate(fy, [entry], "vat", user_id, until=ret.period_end)
    if ret.form != INSTALLMENT and (fy.locked_until is None or fy.locked_until < ret.period_end):
        try:
            period_lock.advance(fy, ret.period_end, user_id)
        except period_lock.LockError as exc:
            raise VatReturnError(str(exc), problems=exc.problems) from None
    ret.status = "declared"
    ret.declared_on = declared_on
    ret.declared_reference = (reference or "").strip()[:50] or None
    db.session.flush()
