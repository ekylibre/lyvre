"""Déclarations de TVA (lot T3, claudedocs/design_societe_tva.md § 3.4-3.5) : CA3 mensuelle calculée
depuis les lignes codées du grand livre (lot T2).

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
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path

from app.extensions import db
from app.models import Account, FiscalYear, Journal, JournalEntry, JournalLine, Organization, VatReturn
from app.models.journal_entry import SOURCE_OPENING, SOURCE_VAT_RETURN
from app.services import account_roles, vat_codes
from app.services.ledger_errors import LedgerError

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "ca3"
FORM = "CA3"
ON_RECEIPTS = "44574"          # TVA collectée en attente : déclarée à l'encaissement
DEFAULT_DUE_DAY = 24           # dernier jour possible fixé par le SIE (du 15 au 24)
RATE_TOLERANCE_CENTS = 100     # écart toléré entre la taxe et base × taux, par ligne
VAT_ACCOUNTS = ("4452", "4453", "4456", "4457")
REVERSAL_BOX = "15"            # TVA déduite à reverser : avoirs reçus des fournisseurs


class VatReturnError(LedgerError):
    def __init__(self, message, field=None, status=409, problems=None):
        super().__init__(message)
        self.field = field
        self.status = status
        self.problems = problems or []


# ------------------------------------------------------------------ formulaire et périodes

@lru_cache(maxsize=8)
def form_spec(year: int) -> dict:
    """Formulaire du millésime `year`, sinon le plus récent qui le précède."""
    years = sorted(int(p.stem) for p in DATA_DIR.glob("*.json") if p.stem.isdigit())
    usable = [y for y in years if y <= year] or years[:1]
    if not usable:
        raise VatReturnError("Aucun formulaire de déclaration de TVA (data/ca3).")
    spec = json.loads((DATA_DIR / f"{usable[-1]}.json").read_text(encoding="utf-8"))
    spec["year"] = usable[-1]
    return spec


def month_bounds(start: date) -> tuple[date, date]:
    first = start.replace(day=1)
    return first, first.replace(day=calendar.monthrange(first.year, first.month)[1])


def parse_period(text: str | None) -> tuple[date, date]:
    """« 2026-07 » → (1er juillet, 31 juillet)."""
    try:
        year, month = (int(part) for part in str(text or "").split("-")[:2])
        return month_bounds(date(year, month, 1))
    except (TypeError, ValueError):
        raise VatReturnError("Période attendue sous la forme AAAA-MM.", "period", status=422) from None


def period_key(start: date) -> str:
    return f"{start:%Y-%m}"


def deadline(period_end: date) -> date:
    """Échéance : jour fixé par le SIE (Structure), le mois suivant la période."""
    org = Organization.query.first()
    day = (org.vat_due_day if org is not None and org.vat_due_day else None) or DEFAULT_DUE_DAY
    year, month = (period_end.year + 1, 1) if period_end.month == 12 else (period_end.year, period_end.month + 1)
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def fiscal_year_for(day: date) -> FiscalYear | None:
    return FiscalYear.query.filter(FiscalYear.start_date <= day, FiscalYear.end_date >= day).first()


def declaring_years():
    return FiscalYear.query.filter(FiscalYear.vat_period.isnot(None)).order_by(FiscalYear.start_date.desc()).all()


def return_for(start: date) -> VatReturn | None:
    return VatReturn.query.filter_by(period_start=start, form=FORM).first()


def _previous_month(start: date) -> date:
    return month_bounds(date(start.year - 1, 12, 1) if start.month == 1 else date(start.year, start.month - 1, 1))[0]


def periods(fy: FiscalYear, today: date | None = None) -> list[dict]:
    """Mois de l'exercice : déclaration enregistrée ou non, échéance et retard."""
    today = today or date.today()
    rows, start = [], month_bounds(fy.start_date)[0]
    while start <= fy.end_date:
        _, end = month_bounds(start)
        ret = return_for(start)
        due = ret.deadline if ret is not None and ret.deadline else deadline(end)
        status = ret.status if ret is not None else ("in_progress" if end >= today else "to_prepare")
        rows.append({"period": period_key(start), "start": start, "end": end, "deadline": due, "status": status,
                     "late": (ret is None or ret.status != "declared") and end < today and due < today,
                     "return": ret})
        start = date(end.year + (end.month == 12), end.month % 12 + 1, 1)
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


def _box_targets(spec: dict, line: JournalLine, credit_notes=frozenset()) -> list[tuple[str, str, str]]:
    """Cases alimentées par une ligne : [(case, colonne, valeur)] ; colonne `base`, `tax` ou `amount`
    (case à un seul montant) ; valeur `base` (base HT), `amount` (taxe de la ligne) ou `reversal` (taxe
    déductible d'un avoir reçu, reversée : son opposé)."""
    mapping = spec["codes"].get(line.vat_code)
    if mapping is None:
        return []
    role = _role(line.account.code or "")
    if role == "deductible" and mapping.get("deductible") and line.entry_id in credit_notes:
        return [(REVERSAL_BOX, "amount", "reversal")]
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


def _credit_carried(start: date) -> int:
    """Case 22 (centimes) : crédit à reporter de la déclaration précédente ; la première, solde débiteur
    de 44567 dans les à-nouveaux de l'exercice."""
    previous = (VatReturn.query.filter(VatReturn.form == FORM, VatReturn.period_end < start)
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


def compute(start: date, end: date, lines=None) -> dict:
    """Cases de la CA3 du mois : `boxes` {case: {base?, tax?, amount?} en euros}, `rows` (ordre du
    formulaire), détail par code (centimes), crédit reporté, TVA due ou crédit."""
    spec = form_spec(end.year)
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
        for box, column, source in _box_targets(spec, line, credit_notes):
            value = base if source == "base" else -amount if source == "reversal" else amount
            cell = cents.setdefault(box, {})
            cell[column] = cell.get(column, 0) + value
            if (line.vat_code or "").startswith("AL_") and source == "amount" and column in ("tax", "amount") \
                    and box not in ("17", "24"):
                reverse_charge[box] = reverse_charge.get(box, 0) + value
    boxes = {box: {column: _euros(value) for column, value in cell.items()} for box, cell in cents.items()}
    with_base = [box["line"] for section in spec["sections"] for box in section["boxes"] if box.get("with_base")]
    carried = _credit_carried(start)
    gross = sum(boxes.get(box, {}).get("tax", 0) for box in with_base) + boxes.get(REVERSAL_BOX, {}).get("amount", 0)
    boxes["16"] = {"amount": gross}
    boxes["22"] = {"amount": _euros(carried)}
    deductible = sum(boxes.get(box, {}).get("amount", 0) for box in ("19", "20", "22"))
    boxes["23"] = {"amount": deductible}
    due, credit = max(gross - deductible, 0), max(deductible - gross, 0)
    boxes.update({"TD": {"amount": due}, "28": {"amount": due}, "32": {"amount": due},
                  "25": {"amount": credit}, "26": {"amount": 0}, "27": {"amount": credit}})
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
    return {"period": period_key(start), "start": start, "end": end, "form": spec["form"], "form_year": spec["year"],
            "boxes": boxes, "rows": rows, "codes": codes, "credit_carried_cents": carried,
            "due_cents": due * 100, "credit_cents": credit * 100, "lines_count": len(lines),
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
    spec = form_spec(end.year)
    query = (JournalLine.query.filter(JournalLine.vat_return_id == vat_return.id) if vat_return is not None
             else retained_lines(start, end))
    lines = list(query)
    credit_notes = credit_note_entries(lines)
    return [line for line in lines if any(target == box for target, _c, _s in _box_targets(spec, line, credit_notes))]


# ------------------------------------------------------------------ contrôles

def _previous_missing(start: date) -> date | None:
    """Mois précédent à déclarer d'abord (exercice déclarant, sans déclaration enregistrée)."""
    previous = _previous_month(start)
    fy = fiscal_year_for(previous)
    if fy is not None and fy.vat_period and return_for(previous) is None:
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
    missing = _previous_missing(start)
    if missing is not None:
        add("error", f"Validez d'abord la déclaration de {missing:%m/%Y} : son crédit se reporte sur ce mois.")
    if end >= today:
        add("warning", "Le mois n'est pas terminé : d'autres pièces peuvent encore arriver.")
    lines = list(retained_lines(start, end)) if lines is None else lines
    drafts = {line.entry_id for line in lines if line.entry.validation_number is None}
    if fy is not None:
        drafts |= {e.id for e in JournalEntry.query.filter(
            JournalEntry.fiscal_year_id == fy.id, JournalEntry.validation_number.is_(None),
            JournalEntry.entry_date <= end, JournalEntry.entry_date >= start)}
    if drafts:
        add("warning", "Écritures en brouillard jusqu'à la fin du mois : elles seront validées avec la déclaration.",
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
        add("warning", "Pièces de mois précédents saisies après leur déclaration : reprises dans ce mois.", earlier)
    return found


def preview(start: date, end: date) -> dict:
    lines = list(retained_lines(start, end))
    return {**compute(start, end, lines), "checks": checks(start, end, lines), "deadline": deadline(end)}


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
    gap = sum(l["debit_cents"] for l in out) - sum(l["credit_cents"] for l in out)
    if gap:
        account = _rounding_account(expense=gap < 0)
        out.append({"account_id": account.id, "label": f"{label} — arrondi à l'euro",
                    "debit_cents": max(-gap, 0), "credit_cents": max(gap, 0)})
    return out


def validate(start: date, end: date, user_id=None) -> VatReturn:
    """Valide la déclaration du mois (sans commit) ; VatReturnError si un contrôle bloque."""
    from app.services import validation
    from app.services.ledger import post_entry

    if return_for(start) is not None:
        raise VatReturnError(f"La déclaration de {start:%m/%Y} est déjà validée.")
    blocking = [c for c in checks(start, end) if c["level"] == "error"]
    if blocking:
        raise VatReturnError(blocking[0]["message"], problems=[c["message"] for c in blocking])
    fy = fiscal_year_for(start)
    try:
        validation.validate(fy, validation.drafts(fy, end).all(), "vat", user_id, until=end)
    except validation.ValidationError as exc:
        raise VatReturnError(str(exc), problems=exc.problems) from None
    lines = list(retained_lines(start, end))
    result = compute(start, end, lines)
    ret = VatReturn(fiscal_year_id=fy.id, period_start=start, period_end=end, form=FORM, status="validated",
                    boxes_json=json.dumps({"form_year": result["form_year"], "boxes": result["boxes"],
                                           "rows": result["rows"], "codes": result["codes"]}, ensure_ascii=False),
                    credit_carried_cents=result["credit_carried_cents"], due_cents=result["due_cents"],
                    credit_cents=result["credit_cents"], deadline=deadline(end), validated_at=datetime.utcnow(),
                    validated_by_user_id=user_id)
    db.session.add(ret)
    db.session.flush()
    for line in lines:
        line.vat_return_id = ret.id
    entry_lines = liquidation_lines(lines, result, f"TVA {start:%m/%Y}")
    if entry_lines:
        entry = post_entry(fy.id, _journal().id, end, f"Liquidation de la TVA — CA3 {start:%m/%Y}", entry_lines,
                           source=SOURCE_VAT_RETURN, source_ref=f"VAT_RETURN:{ret.id}", commit=False)
        ret.liquidation_entry_id = entry.id
    db.session.flush()
    return ret


def last_return() -> VatReturn | None:
    return VatReturn.query.filter_by(form=FORM).order_by(VatReturn.period_end.desc()).first()


def unvalidate(ret: VatReturn) -> None:
    """Annule la dernière déclaration non déposée : lignes libérées, liquidation supprimée (brouillard) ou
    contrepassée (validée) ; sans commit."""
    from app.services.ledger import delete_entries, post_entry

    if ret.status == "declared":
        raise VatReturnError("Déclaration déposée : elle ne s'annule plus (régularisez sur une déclaration suivante).")
    if last_return() is not ret:
        raise VatReturnError("Seule la dernière déclaration s'annule.")
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
                       f"Annulation de la liquidation — CA3 {ret.period_start:%m/%Y}", inverse,
                       source=SOURCE_VAT_RETURN, source_ref=f"VAT_RETURN_CANCEL:{ret.id}", commit=False)
    db.session.delete(ret)
    db.session.flush()


def declare(ret: VatReturn, declared_on: date, reference: str | None = None, user_id=None) -> None:
    """Dépôt sur TeleDEC : liquidation validée, mois verrouillé ; dans l'ordre des mois (sans commit)."""
    from app.services import period_lock, validation

    if ret.status == "declared":
        raise VatReturnError("Déclaration déjà déposée.")
    earlier = (VatReturn.query.filter(VatReturn.form == FORM, VatReturn.period_end < ret.period_start,
                                      VatReturn.status != "declared").first())
    if earlier is not None:
        raise VatReturnError(f"Déposez d'abord la déclaration de {earlier.period_start:%m/%Y}.")
    if not isinstance(declared_on, date) or declared_on < ret.period_end:
        raise VatReturnError("Date de dépôt invalide (après la fin du mois).", "declared_on", status=422)
    fy = ret.fiscal_year
    entry = ret.liquidation_entry
    if entry is not None and entry.validation_number is None:
        validation.validate(fy, [entry], "vat", user_id, until=ret.period_end)
    if fy.locked_until is None or fy.locked_until < ret.period_end:
        try:
            period_lock.advance(fy, ret.period_end, user_id)
        except period_lock.LockError as exc:
            raise VatReturnError(str(exc), problems=exc.problems) from None
    ret.status = "declared"
    ret.declared_on = declared_on
    ret.declared_reference = (reference or "").strip()[:50] or None
    db.session.flush()
