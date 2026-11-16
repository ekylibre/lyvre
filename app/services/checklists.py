"""Listes de contrôle guidées (lot AG9b.e, AG9.6, claudedocs/design_assistant_agricole.md, AGD26 Q-C7) — sans IA.

- Listes en données : `data/checklists/checklists.yml` (clôture, campagne PAC, mois fiscal de mai, automne).
- **Fenêtre** : autour de la clôture de chaque exercice (J - 30 à J + 60) ou mois de l'année ; une liste s'affiche
  pendant sa fenêtre, et 15 jours avant (« à venir »).
- **Applicabilité** : mêmes conditions que les fiches d'échéances (`deadlines.applies`) ; une donnée de profil
  manquante laisse la liste visible, avec la mention « profil à compléter ».
- **Étapes** : lien vers l'écran Lyvre ; certaines se cochent d'après le dossier (contrôle `auto`), les autres à la
  main (`checklist_marks`).
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import yaml

from app.extensions import db
from app.models import ChecklistMark, FiscalYear

DATA = Path(__file__).resolve().parents[2] / "data" / "checklists" / "checklists.yml"
UPCOMING_DAYS = 15


class ChecklistError(Exception):
    def __init__(self, message, field=None, status=422):
        super().__init__(message)
        self.message, self.field, self.status = message, field, status


def enabled() -> bool:
    from app.tenant import is_agri
    return is_agri()


@lru_cache(maxsize=1)
def definitions() -> tuple[dict, ...]:
    items = yaml.safe_load(DATA.read_text(encoding="utf-8")) or []
    problems = validate(items)
    if problems:
        raise ValueError("; ".join(problems))
    return tuple(items)


def validate(items: list[dict]) -> list[str]:
    problems, seen = [], set()
    for c in items:
        cid = c.get("id")
        if not cid or cid in seen:
            problems.append(f"identifiant manquant ou en double : {cid}")
        seen.add(cid)
        window = c.get("window") or {}
        if window.get("type") not in ("closing", "months"):
            problems.append(f"{cid} : fenêtre inconnue")
        steps = c.get("steps") or []
        if not steps or len({s.get("id") for s in steps}) != len(steps):
            problems.append(f"{cid} : étapes manquantes ou en double")
        for s in steps:
            if s.get("auto") and s["auto"] not in AUTO_CHECKS:
                problems.append(f"{cid}.{s.get('id')} : contrôle automatique inconnu {s['auto']}")
    return problems


# ------------------------------------------------------------------ contrôles automatiques
#
# Rendent True (fait), False (à faire) ou None (rien à contrôler : case à cocher). `scope` : exercice (clôture) ou
# année (listes de calendrier).

def _bank_reconciled(fy: FiscalYear | None, _year: int) -> bool | None:
    from app.models import BankTransaction
    if fy is None:
        return None
    rows = BankTransaction.query.filter(BankTransaction.transaction_date.between(fy.start_date, fy.end_date),
                                        BankTransaction.is_reversed.is_(False))
    if rows.first() is None:
        return None
    return rows.filter(BankTransaction.reconciled.is_(False)).first() is None


def _inventory_lines(fy, _year):
    from app.models import StockLine
    return None if fy is None else StockLine.query.filter_by(fiscal_year_id=fy.id).first() is not None


def _stock_entry(fy, _year):
    from app.models import JournalEntry
    from app.models.journal_entry import SOURCE_STOCK
    return None if fy is None else JournalEntry.query.filter_by(fiscal_year_id=fy.id, source=SOURCE_STOCK).first() is not None


def _msa_calls_fy(fy, _year):
    from app.models import MsaCall
    if fy is None:
        return None
    return MsaCall.query.filter(MsaCall.due_on.between(fy.start_date, fy.end_date)).first() is not None


def _closing_checks_clear(fy, _year):
    from app.services import closing
    if fy is None:
        return None
    return not any(c.severity == "anomaly" for c in closing.checks(fy))


def _annual_vat(year_end: int) -> bool:
    from app.models import VatReturn
    rows = VatReturn.query.filter(VatReturn.form == "CA12A").all()
    return any(r.period_end.year == year_end and (r.declared_on is not None or r.status in ("validated", "declared"))
               for r in rows)


def _vat_annual_fy(fy, _year):
    return None if fy is None else _annual_vat(fy.end_date.year)


def _vat_annual_previous(_fy, year):
    return _annual_vat(year - 1)


def _fiscal_year_closed(fy, _year):
    return None if fy is None else fy.status == "closed"


def _activity_measures(_fy, year):
    from app.models import Activity
    from app.services import analytic
    activities = Activity.query.filter(Activity.archived.is_(False), Activity.nature == "main").all()
    if not activities:
        return None
    for activity in activities:
        listing = analytic.activity_payload(activity, year).get("campaign") or {}
        if listing.get("measure") is None:
            return False
    return True


def _aids_campaign(year: int) -> list:
    from app.models import Aid
    return Aid.query.filter(Aid.campaign == year, Aid.status != "refused").all()


def _aids_previous_campaign(_fy, year):
    from app.services import aids
    rows = _aids_campaign(year - 1)
    if not rows:
        return None
    return all(aids.acquired_cents(a) - aids.paid_cents(a) <= 0 for a in rows)


def _aids_current_campaign(_fy, year):
    return bool(_aids_campaign(year))


def _fiscal_profile(_fy, _year):
    from app.services import tax_profile
    today = date.today()
    return all(tax_profile.current_value(kind, today) for kind in ("ba_regime", "vat_regime", "income_tax"))


def _msa_calls_year(_fy, year):
    from app.models import MsaCall
    return MsaCall.query.filter(MsaCall.year == year, MsaCall.kind.in_(("balance", "single"))).first() is not None


AUTO_CHECKS = {
    "bank_reconciled": _bank_reconciled, "inventory_lines": _inventory_lines, "stock_entry": _stock_entry,
    "msa_calls_fy": _msa_calls_fy, "closing_checks_clear": _closing_checks_clear, "vat_annual_fy": _vat_annual_fy,
    "vat_annual_previous": _vat_annual_previous, "fiscal_year_closed": _fiscal_year_closed,
    "activity_measures": _activity_measures, "aids_previous_campaign": _aids_previous_campaign,
    "aids_current_campaign": _aids_current_campaign, "fiscal_profile": _fiscal_profile, "msa_calls_year": _msa_calls_year,
}


# ------------------------------------------------------------------ occurrences

def _month_day(year: int, text: str) -> date:
    return date(year, int(text[:2]), int(text[3:]))


def _windows(checklist: dict, today: date) -> list[tuple[str, date, date, FiscalYear | None, int]]:
    """(période, début, fin, exercice, année) des fenêtres en cours ou à venir."""
    window = checklist["window"]
    out = []
    if window["type"] == "closing":
        for fy in FiscalYear.query.order_by(FiscalYear.end_date):
            start = fy.end_date - timedelta(days=window.get("before_days", 30))
            end = fy.end_date + timedelta(days=window.get("after_days", 60))
            if start - timedelta(days=UPCOMING_DAYS) <= today <= end:
                out.append((fy.label, start, end, fy, fy.end_date.year))
    else:
        for year in (today.year, today.year + 1):
            start, end = _month_day(year, window["start"]), _month_day(year, window["end"])
            if start - timedelta(days=UPCOMING_DAYS) <= today <= end:
                fy = FiscalYear.query.filter(FiscalYear.start_date <= start, FiscalYear.end_date >= start).first()
                out.append((str(year), start, end, fy, year))
    return out


def _link(link: str | None, fy: FiscalYear | None) -> str | None:
    if not link:
        return None
    if "{fy}" in link:
        return link.replace("{fy}", str(fy.id)) if fy is not None else link.split("?")[0].replace("/{fy}/closing", "/")
    return link


def listing(today: date | None = None) -> dict:
    from app.services import deadlines
    today = today or date.today()
    ctx = deadlines.context()
    marks = {(m.checklist_id, m.period, m.step_id): m for m in ChecklistMark.query.all()}
    items = []
    for checklist in definitions():
        for period, start, end, fy, year in _windows(checklist, today):
            applies = deadlines.applies(checklist.get("applies"), ctx, end)
            if applies is False:
                continue
            steps = []
            for step in checklist["steps"]:
                if deadlines.applies(step.get("applies"), ctx, end) is False:
                    continue
                auto = AUTO_CHECKS[step["auto"]](fy, year) if step.get("auto") else None
                mark = marks.get((checklist["id"], period, step["id"]))
                steps.append({"id": step["id"], "label": step["label"], "link": _link(step.get("link"), fy),
                              "fiche": step.get("fiche"), "auto": step.get("auto") is not None and auto is not None,
                              "auto_done": auto, "marked_on": mark.done_on.isoformat() if mark else None,
                              "done": bool(auto) or mark is not None})
            done = sum(1 for s in steps if s["done"])
            items.append({"id": checklist["id"], "title": checklist["title"], "summary": checklist.get("summary"),
                          "period": period, "start": start.isoformat(), "end": end.isoformat(),
                          "status": "upcoming" if today < start else "current",
                          "profile_incomplete": applies is None, "fiscal_year_id": fy.id if fy else None,
                          "progress": {"done": done, "total": len(steps)}, "steps": steps})
    items.sort(key=lambda c: (c["status"] != "current", c["end"]))
    return {"today": today.isoformat(), "items": items}


def mark(checklist_id: str, period: str, step_id: str, done: bool, user_id=None, today: date | None = None) -> None:
    checklist = next((c for c in definitions() if c["id"] == checklist_id), None)
    if checklist is None or not any(s["id"] == step_id for s in checklist["steps"]):
        raise ChecklistError("Étape inconnue.", status=404)
    period = str(period or "")[:20]
    if not period:
        raise ChecklistError("Période attendue.", "period")
    row = ChecklistMark.query.filter_by(checklist_id=checklist_id, period=period, step_id=step_id).first()
    if done and row is None:
        db.session.add(ChecklistMark(checklist_id=checklist_id, period=period, step_id=step_id,
                                     done_on=today or date.today(), user_id=user_id))
    elif not done and row is not None:
        db.session.delete(row)
