"""Acomptes de TVA du régime simplifié agricole, bulletin 3525 bis (lot AG2.c, claudedocs/design_tva_agricole.md § 4).

- **Échéancier** : la période annuelle de la CA12A (année civile, ou exercice sous l'option CA12AE) se découpe en
  blocs de trois mois ; chaque bloc a son acompte, dû à la première des dates du paramètre
  `vat.rsa.installment_calendar` (5 février, 5 mai, 5 août, 5 novembre) après sa fin, reportée au jour ouvré.
- **Référence** : TVA due l'année précédente, ligne 23 de la CA12A précédente dans Lyvre, sinon saisie sur l'exercice
  (`fiscal_years.vat_reference_cents`, TVA sur immobilisations déduite en `vat_reference_assets_cents`). Sans
  référence : nouvel assujetti, montants saisis (au moins 70 % de l'impôt réel du trimestre, CGI art. 1693 bis II).
- **Dispense** : TVA due avant déduction de la TVA sur immobilisations (ligne 23 + ligne 17) sous
  `vat.rsa.installment_exemption_cents` (1 000 €).
- **Montant proposé** : ⌈ référence × `vat.rsa.installment_share_bp` (20 %) ⌉ à l'euro. Un autre montant (modulation,
  suspension par un bulletin à 0) demande un motif ; alerte si la TVA estimée de l'année dépasse de plus de
  `vat.rsa.installment_tolerance_bp` (30 %) les acomptes (intérêt de retard et majoration, CGI art. 1727 et 1731).
- **Valider** : déclaration de forme `ACOMPTE` (période = le bloc), écriture débit 44581, crédit 44551 (journal OD,
  source `VAT_RETURN`, brouillard). **Déposer** : paiement fait, écriture validée ; la période n'est pas verrouillée.
  La CA12A impute les acomptes enregistrés (ligne 25) ; une fois validée, ils sont figés.
"""
from __future__ import annotations

import calendar
import json
from datetime import date, datetime, timedelta

from app.extensions import db
from app.models import Account, JournalEntry, JournalLine, VatReturn
from app.models.journal_entry import SOURCE_VAT_RETURN
from app.services import fr_calendar, reg_params, vat_codes
from app.services import vat_return as vr
from app.services.vat_return import CA12A, INSTALLMENT, INSTALLMENTS_ACCOUNT, VatReturnError

DEFAULT_CALENDAR = ("02-05", "05-05", "08-05", "11-05")
BULLETIN = "3525 bis"
MIN_ESTIMATE_DAYS = 30  # pas d'extrapolation de la TVA de l'année sur moins d'un mois d'écritures


def _add_months(day: date, months: int) -> date:
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def blocks(start: date, end: date) -> list[tuple[date, date]]:
    """Blocs de trois mois de la période annuelle, le dernier borné à sa fin."""
    out, current = [], start
    while current <= end:
        stop = min(_add_months(current, 3) - timedelta(days=1), end)
        out.append((current, stop))
        current = stop + timedelta(days=1)
    return out


def due_date(block_end: date) -> date:
    """Première date du calendrier des acomptes après la fin du bloc, reportée au jour ouvré."""
    days = reg_params.value("vat.rsa.installment_calendar", block_end, default=None) or DEFAULT_CALENDAR
    for year in (block_end.year, block_end.year + 1):
        for text in sorted(days):
            month, day = (int(part) for part in text.split("-"))
            candidate = date(year, month, day)
            if candidate > block_end:
                return fr_calendar.next_working_day(candidate)
    raise VatReturnError("Calendrier des acomptes invalide (paramètre vat.rsa.installment_calendar).")


def block_label(start: date, end: date) -> str:
    if start.year == end.year:
        return f"{start:%m}–{end:%m/%Y}" if start.month != end.month else f"{start:%m/%Y}"
    return f"{start:%m/%Y}–{end:%m/%Y}"


def _annual(period: tuple[date, date]) -> tuple[date, date]:
    start, end = period
    if not vr._is_annual(start, end) or vr.kind_of(start) != vr.ANNUAL:
        raise VatReturnError("Les acomptes concernent la déclaration annuelle CA12A (exercice au rythme annuel).",
                             "period", status=422)
    return start, end


# ------------------------------------------------------------------ référence, dispense, montant proposé

def reference(start: date) -> dict:
    """TVA due de l'année précédente (centimes) et TVA due avant déduction de la TVA sur immobilisations."""
    previous = VatReturn.query.filter(VatReturn.form == CA12A, VatReturn.period_end == start - timedelta(days=1)).first()
    if previous is not None:
        boxes = previous.detail.get("boxes", {})
        amount = lambda line: int(boxes.get(line, {}).get("amount", 0) or 0)  # noqa: E731
        due, assets = amount("23"), amount("17")
        before = max(amount("15") - amount("21") + assets, 0) if "15" in boxes else due + assets
        return {"source": "ca12a", "return_id": previous.id, "due_cents": due * 100, "assets_cents": assets * 100,
                "before_assets_cents": before * 100,
                "label": vr.period_label(previous.period_start, previous.period_end)}
    fy = vr.period_fiscal_year(start)
    if fy is not None and fy.vat_reference_cents is not None:
        assets = fy.vat_reference_assets_cents or 0
        return {"source": "entered", "return_id": None, "due_cents": fy.vat_reference_cents, "assets_cents": assets,
                "before_assets_cents": fy.vat_reference_cents + assets, "label": None}
    return {"source": "missing", "return_id": None, "due_cents": None, "assets_cents": None,
            "before_assets_cents": None, "label": None}


def proposed_amount(due_cents: int, on: date) -> int:
    """⌈ TVA due × part ⌉ à l'euro, en centimes."""
    share = reg_params.value("vat.rsa.installment_share_bp", on, default=2000)
    return -(-due_cents * share // 1_000_000) * 100


def _dispensed(ref: dict, on: date) -> bool:
    if ref["before_assets_cents"] is None:
        return False
    return ref["before_assets_cents"] < reg_params.value("vat.rsa.installment_exemption_cents", on, default=100000)


# ------------------------------------------------------------------ TVA estimée de l'année

def _net_tax(start: date, end: date) -> int:
    """TVA collectée et due moins TVA déductible des lignes codées datées de la période (centimes)."""
    rows = (db.session.query(Account.code, JournalLine.debit_cents, JournalLine.credit_cents)
            .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
            .join(Account, Account.id == JournalLine.account_id)
            .filter(JournalLine.vat_code.isnot(None), JournalEntry.entry_date.between(start, end),
                    ~Account.code.like(f"{vr.ON_RECEIPTS}%")).all())
    total = 0
    for code, debit, credit in rows:
        role = vr._role(code or "")
        if role in ("collected", "due"):
            total += credit - debit
        elif role == "deductible":
            total -= debit - credit
    return total


def estimate(start: date, end: date, today: date) -> dict | None:
    """TVA nette de l'année extrapolée depuis les écritures à date (None avant un mois d'écritures)."""
    upto = min(today, end)
    elapsed = (upto - start).days + 1
    if elapsed < MIN_ESTIMATE_DAYS:
        return None
    to_date = _net_tax(start, upto)
    total_days = (end - start).days + 1
    return {"to_date_cents": to_date, "until": upto, "year_cents": round(to_date * total_days / elapsed)}


# ------------------------------------------------------------------ échéancier

def _detail(ret: VatReturn) -> dict:
    try:
        return ret.detail
    except (TypeError, ValueError):
        return {}


def schedule(period: tuple[date, date], today: date | None = None) -> dict:
    """Acomptes de la période annuelle : référence, dispense, montant proposé, état et échéance de chacun."""
    today = today or date.today()
    start, end = _annual(period)
    ref = reference(start)
    dispensed = _dispensed(ref, end)
    proposed = None if dispensed or ref["due_cents"] is None else proposed_amount(ref["due_cents"], end)
    annual = vr.return_for(start, CA12A)
    items, planned, modulated = [], 0, False
    for number, (block_start, block_end) in enumerate(blocks(start, end), start=1):
        ret = vr.return_for(block_start, INSTALLMENT)
        detail = _detail(ret) if ret is not None else {}
        due = ret.deadline if ret is not None and ret.deadline else due_date(block_end)
        if ret is not None:
            status, amount = ret.status, ret.due_cents
            modulated = modulated or (proposed is not None and amount < proposed)
        else:
            status, amount = ("dispensed" if dispensed else "to_prepare"), None
        planned += amount if amount is not None else (proposed or 0)
        items.append({"number": number, "start": block_start, "end": block_end, "label": block_label(block_start, block_end),
                      "deadline": due, "status": status, "amount_cents": amount, "motive": detail.get("motive"),
                      "late": status in ("to_prepare", "validated") and due < today, "return": ret,
                      "can_validate": status == "to_prepare" and annual is None and not dispensed
                      and all(i["return"] is not None for i in items)})
    warnings = []
    estimated = estimate(start, end, today) if not dispensed else None
    tolerance = reg_params.value("vat.rsa.installment_tolerance_bp", end, default=3000)
    if estimated and modulated and estimated["year_cents"] > planned * (10000 + tolerance) // 10000:
        warnings.append(f"TVA estimée de l'année ({estimated['year_cents'] // 100} €) supérieure de plus de "
                        f"{tolerance // 100} % aux acomptes réduits ({planned // 100} €) : intérêt de retard et majoration "
                        "de 5 % sur l'insuffisance (CGI art. 1727 et 1731).")
    if ref["source"] == "missing":
        warnings.append("Pas de CA12A de l'année précédente dans Lyvre : saisissez la TVA due l'an dernier pour calculer "
                        "les acomptes. Nouvel assujetti : fixez chaque acompte à au moins 70 % de la TVA réelle du "
                        "trimestre (CGI art. 1693 bis II).")
    return {"period": vr.period_key(start, end), "label": vr.period_label(start, end), "start": start, "end": end,
            "reference": ref, "dispensed": dispensed, "proposed_cents": proposed, "planned_cents": planned,
            "estimate": estimated, "annual_return": annual, "items": items, "warnings": warnings,
            "exemption_cents": reg_params.value("vat.rsa.installment_exemption_cents", end, default=100000),
            "share_bp": reg_params.value("vat.rsa.installment_share_bp", end, default=2000)}


def missing(start: date, end: date, today: date | None = None) -> list[dict]:
    """Acomptes dus (échéance passée) non enregistrés de la période annuelle, hors dispense."""
    today = today or date.today()
    data = schedule((start, end), today)
    return [] if data["dispensed"] else [i for i in data["items"] if i["status"] == "to_prepare" and i["deadline"] <= today]


# ------------------------------------------------------------------ saisie de la référence, validation

def save_reference(period: tuple[date, date], due_cents, assets_cents=None) -> None:
    """Référence saisie pour la première année dans Lyvre (sans commit) ; montant vide : saisie retirée."""
    start, _ = _annual(period)
    if VatReturn.query.filter(VatReturn.form == CA12A, VatReturn.period_end == start - timedelta(days=1)).first():
        raise VatReturnError("La CA12A de l'année précédente est dans Lyvre : sa ligne 23 sert de référence.")
    if any(VatReturn.query.filter(VatReturn.form == INSTALLMENT, VatReturn.period_start >= start,
                                  VatReturn.period_end <= period[1])):
        raise VatReturnError("Des acomptes de l'année sont enregistrés : annulez-les avant de changer la référence.")
    fy = vr.period_fiscal_year(start, period[1])
    if fy is None:
        raise VatReturnError("Aucun exercice ne couvre la période.")
    for value, field in ((due_cents, "reference_cents"), (assets_cents, "assets_cents")):
        if value not in (None, "") and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
            raise VatReturnError("Montant en centimes, positif ou nul.", field, status=422)
    if due_cents in (None, ""):
        fy.vat_reference_cents = fy.vat_reference_assets_cents = None
    else:
        fy.vat_reference_cents, fy.vat_reference_assets_cents = due_cents, assets_cents or None
    db.session.flush()


def validate(period: tuple[date, date], number, amount_cents, motive=None, user_id=None) -> tuple[VatReturn, list[str]]:
    """Enregistre l'acompte n° `number` de la période annuelle (sans commit) : déclaration `ACOMPTE` et écriture
    44581 / 44551 ; avertissements (modulation au-delà de la tolérance)."""
    from app.services.ledger import post_entry

    start, end = _annual(period)
    data = schedule((start, end))
    if not isinstance(number, int) or isinstance(number, bool) or not 1 <= number <= len(data["items"]):
        raise VatReturnError("Acompte inconnu.", "number", status=422)
    item = data["items"][number - 1]
    if data["annual_return"] is not None:
        raise VatReturnError(f"La CA12A {data['label']} est validée : ses acomptes sont figés.")
    if data["dispensed"]:
        raise VatReturnError(f"Dispensé d'acomptes : TVA due l'année précédente, avant TVA sur immobilisations, sous "
                             f"{data['exemption_cents'] // 100} € ; tout se paie avec la CA12A.")
    if item["return"] is not None:
        raise VatReturnError(f"L'acompte n° {number} est déjà enregistré.")
    earlier = next((i for i in data["items"][:number - 1] if i["return"] is None), None)
    if earlier is not None:
        raise VatReturnError(f"Enregistrez d'abord l'acompte n° {earlier['number']}.")
    if not isinstance(amount_cents, int) or isinstance(amount_cents, bool) or amount_cents < 0 or amount_cents % 100:
        raise VatReturnError("Acompte en euros entiers, positif ou nul.", "amount_cents", status=422)
    motive = (str(motive or "").strip())[:300] or None
    proposed = data["proposed_cents"]
    if proposed is not None and amount_cents != proposed and motive is None:
        raise VatReturnError(f"Montant différent de l'acompte calculé ({proposed // 100} €) : indiquez le motif de la "
                             "modulation.", "motive", status=422)
    fy = vr.fiscal_year_for(item["end"])
    if fy is None:
        raise VatReturnError("Aucun exercice ne couvre la fin du trimestre de l'acompte.")
    ret = VatReturn(fiscal_year_id=fy.id, period_start=item["start"], period_end=item["end"], form=INSTALLMENT,
                    status="validated", due_cents=amount_cents, deadline=item["deadline"],
                    boxes_json=json.dumps({"form": BULLETIN, "number": number, "annual_period": data["period"],
                                           "proposed_cents": proposed, "motive": motive}, ensure_ascii=False),
                    validated_at=datetime.utcnow(), validated_by_user_id=user_id)
    db.session.add(ret)
    db.session.flush()
    if amount_cents:
        label = f"Acompte de TVA n° {number} — {block_label(item['start'], item['end'])}"
        lines = [{"account_id": vat_codes.account(INSTALLMENTS_ACCOUNT).id, "label": label, "debit_cents": amount_cents,
                  "credit_cents": 0},
                 {"account_id": vr._role_account("vat_payable", "44551").id, "label": label, "debit_cents": 0,
                  "credit_cents": amount_cents}]
        entry = post_entry(fy.id, vr._journal().id, item["end"], f"{label} ({BULLETIN})", lines,
                           source=SOURCE_VAT_RETURN, source_ref=f"VAT_RETURN:{ret.id}", commit=False)
        ret.liquidation_entry_id = entry.id
    db.session.flush()
    warnings = schedule((start, end))["warnings"]
    return ret, [w for w in warnings if w.startswith("TVA estimée")]


def annual_period_of(ret: VatReturn) -> tuple[date, date]:
    return vr.annual_bounds(ret.period_start)
