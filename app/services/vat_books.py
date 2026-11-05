"""Livres de TVA du régime simplifié agricole (lot AG2.d, claudedocs/design_tva_agricole.md § 7).

- **Livre des ventes** : une ligne par pièce et par code de TVA de vente (codes `V…`) datée de la période, avec sa
  catégorie (ligne de la CA12A : export 01, non imposable 02, livraison intracommunautaire 03, taxable par taux 04,
  5A, 5C, 09), sa base et sa taxe ; totaux par ligne.
- **Livre des achats** : **tous** les achats de la période, codés ou non (comptes 20, 21, 23, 60 sauf 603, 61, 62),
  une ligne par pièce et par nature (immobilisations, autres biens et services), avec la TVA déductible (44562 pour
  les immobilisations, autres 4456 sinon), la TVA autoliquidée, ou la mention « non déductible ».
- **Contrôle croisé** (période annuelle de la CA12A) : totaux du livre des ventes égaux aux lignes 01 à 09 ; TVA
  déductible du livre des achats égale à 17 + 18 − 14 (les avoirs reçus vont en ligne 14 sur la déclaration). La
  CA12A reprend les lignes codées non déclarées jusqu'à la fin de la période, le livre les pièces datées de la
  période : un écart signale une pièce antérieure reprise, une pièce déclarée ailleurs ou une TVA sans code.

Montants en centimes, signés (avoir : négatif).
"""
from __future__ import annotations

from datetime import date

from app.extensions import db
from app.models import Account, Entity, JournalEntry, JournalLine
from app.models.journal_entry import (
    SOURCE_AID_GRANT, SOURCE_AID_RELEASE, SOURCE_ALLOCATION, SOURCE_CLOSING, SOURCE_DEPRECIATION, SOURCE_INVENTORY,
    SOURCE_LIVING_IMPAIRMENT, SOURCE_LIVING_WIP, SOURCE_OPENING, SOURCE_REVERSAL, SOURCE_STOCK, SOURCE_VAT_RETURN,
)
from app.services import vat_codes
from app.services import vat_return as vr

EXCLUDED_SOURCES = (SOURCE_OPENING, SOURCE_CLOSING, SOURCE_ALLOCATION, SOURCE_VAT_RETURN, SOURCE_DEPRECIATION,
                    SOURCE_INVENTORY, SOURCE_REVERSAL, SOURCE_AID_GRANT, SOURCE_AID_RELEASE, SOURCE_STOCK, SOURCE_LIVING_WIP, SOURCE_LIVING_IMPAIRMENT)
SALES_LINES = ("01", "02", "03", "04", "5A", "5C", "09")
SALES_CATEGORIES = {"01": "Exportations hors UE", "02": "Exonérées ou non imposables",
                    "03": "Livraisons intracommunautaires", "04": "Taxables à 20 %", "5A": "Taxables à 10 %",
                    "5C": "Taxables à 5,5 %", "09": "Taxables à taux particulier (2,1 %)"}
FIXED_ASSETS = ("20", "21", "23")
PURCHASES = ("60", "61", "62")
GROUPS = {"assets": "Immobilisations", "other": "Autres biens et services"}


class BookError(Exception):
    def __init__(self, message, field=None):
        super().__init__(message)
        self.message, self.field = message, field


def default_period(today: date | None = None) -> tuple[date, date]:
    """Période de la CA12A en cours (rythme annuel), sinon l'exercice en cours, sinon l'année civile."""
    today = today or date.today()
    fy = vr.fiscal_year_for(today)
    if fy is not None and fy.vat_period == vr.ANNUAL:
        return vr.annual_bounds(today)
    if fy is not None:
        return fy.start_date, fy.end_date
    return date(today.year, 1, 1), date(today.year, 12, 31)


def parse_bounds(start_text: str | None, end_text: str | None, period: str | None = None) -> tuple[date, date]:
    if period:
        try:
            return vr.parse_period(period)
        except vr.VatReturnError as exc:
            raise BookError(str(exc), "period") from None
    if not start_text and not end_text:
        return default_period()
    try:
        start, end = date.fromisoformat(str(start_text)[:10]), date.fromisoformat(str(end_text)[:10])
    except ValueError:
        raise BookError("Dates de début et de fin attendues (AAAA-MM-JJ).", "start") from None
    if end < start:
        raise BookError("La fin précède le début.", "end")
    if (end - start).days > 800:
        raise BookError("Période de 26 mois au plus.", "end")
    return start, end


def _entries(start: date, end: date):
    return (JournalEntry.query.filter(JournalEntry.entry_date.between(start, end),
                                      db.or_(JournalEntry.source.is_(None), JournalEntry.source.notin_(EXCLUDED_SOURCES))))


def _names(entity_ids) -> dict[int, str]:
    ids = {i for i in entity_ids if i}
    return {e.id: e.name for e in Entity.query.filter(Entity.id.in_(ids))} if ids else {}


def _sale_line(code: str, spec: dict) -> str | None:
    target = spec["codes"].get(code) or {}
    for line in (target.get("tax"), *(target.get("base") or [])):
        if line in SALES_LINES:
            return line
    return None


def _euros(cents: int) -> int:
    return vr._euros(cents)


def _ca12a_rows(start: date, end: date) -> dict[str, dict] | None:
    """Lignes de la CA12A de la période (figées si validée, sinon calculées) ; None hors période annuelle."""
    if vr.kind_of(start) != vr.ANNUAL or vr.annual_bounds(start) != (start, end):
        return None
    ret = vr.return_for(start, vr.CA12A)
    rows = ret.detail["rows"] if ret is not None else vr.compute(start, end)["rows"]
    return {row["line"]: row for row in rows if row["kind"] != "section"}


# ------------------------------------------------------------------ livre des ventes

def sales_book(start: date, end: date) -> dict:
    spec = vr.form_spec(end.year, vr.CA12A)
    lines = (JournalLine.query.join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
             .join(Account, Account.id == JournalLine.account_id)
             .filter(JournalLine.vat_code.like("V%"), JournalEntry.id.in_(_entries(start, end).with_entities(JournalEntry.id)),
                     ~Account.code.like(f"{vr.ON_RECEIPTS}%"))
             .order_by(JournalEntry.entry_date, JournalEntry.id, JournalLine.id).all())
    groups: dict[tuple[int, str], dict] = {}
    entities: dict[int, set] = {}
    for line in lines:
        entry = line.entry
        group = groups.setdefault((entry.id, line.vat_code), {
            "entry": entry, "code": line.vat_code, "tax": 0, "base_tax": 0, "base_lines": 0, "has_tax": False})
        role, amount, base = vr._signed(line)
        if role == "base":
            group["base_lines"] += amount
        else:
            group["has_tax"] = True
            group["tax"] += amount
            group["base_tax"] += base
    for entry_id in {key[0] for key in groups}:
        entities[entry_id] = set()
    for entry_id, entity_id in (db.session.query(JournalLine.entry_id, JournalLine.entity_id)
                                .filter(JournalLine.entry_id.in_(list(entities)), JournalLine.entity_id.isnot(None))):
        entities[entry_id].add(entity_id)
    names = _names({i for ids in entities.values() for i in ids})
    items, totals = [], {line: {"base_cents": 0, "tax_cents": 0} for line in SALES_LINES}
    other = {"base_cents": 0, "tax_cents": 0}
    for (entry_id, code), group in groups.items():
        entry = group["entry"]
        line = _sale_line(code, spec)
        base = group["base_tax"] if group["has_tax"] else group["base_lines"]
        bucket = totals.get(line, other)
        bucket["base_cents"] += base
        bucket["tax_cents"] += group["tax"]
        items.append({"date": entry.entry_date, "entry_id": entry.id, "reference": entry.reference,
                      "label": entry.description or "", "entity": ", ".join(sorted(names[i] for i in entities[entry_id] if i in names)),
                      "code": code, "code_label": vat_codes.label(code), "line": line,
                      "category": SALES_CATEGORIES.get(line, "Hors CA12A"), "base_cents": base, "tax_cents": group["tax"]})
    summary = [{"line": line, "category": SALES_CATEGORIES[line], **totals[line]} for line in SALES_LINES]
    if other["base_cents"] or other["tax_cents"]:
        summary.append({"line": None, "category": "Hors CA12A", **other})
    return {"start": start, "end": end, "items": items, "totals": summary,
            "total": {"base_cents": sum(t["base_cents"] for t in summary), "tax_cents": sum(t["tax_cents"] for t in summary)},
            "control": _sales_control(start, end, totals)}


def _sales_control(start, end, totals) -> dict | None:
    rows = _ca12a_rows(start, end)
    if rows is None:
        return None
    out = []
    for line in SALES_LINES:
        row = rows.get(line, {})
        with_base = bool(row.get("with_base"))
        declared_base = int(row.get("base") or 0) if with_base else int(row.get("amount") or 0)
        declared_tax = int(row.get("amount") or 0) if with_base else 0
        book_base, book_tax = _euros(totals[line]["base_cents"]), _euros(totals[line]["tax_cents"])
        out.append({"line": line, "label": row.get("label", SALES_CATEGORIES[line]), "book_base": book_base,
                    "book_tax": book_tax, "return_base": declared_base, "return_tax": declared_tax,
                    "ok": (book_base, book_tax) == (declared_base, declared_tax)})
    return {"form": vr.CA12A, "validated": vr.return_for(start, vr.CA12A) is not None, "lines": out,
            "ok": all(l["ok"] for l in out)}


# ------------------------------------------------------------------ livre des achats

def _group_of(code: str) -> str | None:
    if code.startswith(FIXED_ASSETS):
        return "assets"
    if code.startswith(PURCHASES) and not code.startswith("603"):
        return "other"
    return None


def purchases_book(start: date, end: date) -> dict:
    rows = (db.session.query(JournalLine, Account.code)
            .join(Account, Account.id == JournalLine.account_id)
            .filter(JournalLine.entry_id.in_(_entries(start, end).with_entities(JournalEntry.id)))
            .order_by(JournalLine.entry_id, JournalLine.id).all())
    by_entry: dict[int, list] = {}
    for line, code in rows:
        by_entry.setdefault(line.entry_id, []).append((line, code or ""))
    purchase_entries = {eid: lines for eid, lines in by_entry.items() if any(_group_of(code) for _, code in lines)}
    entries = {e.id: e for e in JournalEntry.query.filter(JournalEntry.id.in_(list(purchase_entries)))} if purchase_entries else {}
    names = _names(line.entity_id for lines in purchase_entries.values() for line, _ in lines)
    items = []
    totals = {g: {"ht_cents": 0, "deductible_cents": 0, "reverse_charge_cents": 0, "non_deductible_ht_cents": 0}
              for g in GROUPS}
    for entry_id, lines in purchase_entries.items():
        entry = entries[entry_id]
        parts = {g: {"ht": 0, "deductible": 0, "reverse": 0, "codes": set()} for g in GROUPS}
        for line, code in lines:
            group = _group_of(code)
            if group:
                parts[group]["ht"] += line.debit_cents - line.credit_cents
                if line.vat_code:
                    parts[group]["codes"].add(line.vat_code)
            role = vr._role(code)
            if role == "deductible":
                target = "assets" if code.startswith("44562") else "other"
                parts[target]["deductible"] += line.debit_cents - line.credit_cents
                if line.vat_code:
                    parts[target]["codes"].add(line.vat_code)
            elif role == "due":
                target = "other" if not parts["assets"]["ht"] else "assets"
                parts[target]["reverse"] += line.credit_cents - line.debit_cents
        supplier = sorted({names[l.entity_id] for l, _ in lines if l.entity_id in names})
        for group, part in parts.items():
            if not part["ht"] and not part["deductible"]:
                continue
            totals[group]["ht_cents"] += part["ht"]
            totals[group]["deductible_cents"] += part["deductible"]
            totals[group]["reverse_charge_cents"] += part["reverse"]
            if not part["deductible"]:
                totals[group]["non_deductible_ht_cents"] += part["ht"]
            items.append({"date": entry.entry_date, "entry_id": entry.id, "reference": entry.reference,
                          "label": entry.description or "", "entity": ", ".join(supplier), "group": group,
                          "group_label": GROUPS[group], "codes": sorted(part["codes"]), "ht_cents": part["ht"],
                          "deductible_cents": part["deductible"], "reverse_charge_cents": part["reverse"],
                          "non_deductible": not part["deductible"]})
    items.sort(key=lambda i: (i["date"], i["entry_id"], i["group"]))
    return {"start": start, "end": end, "items": items,
            "totals": [{"group": g, "label": GROUPS[g], **t} for g, t in totals.items()],
            "control": _purchases_control(start, end, totals)}


def _purchases_control(start, end, totals) -> dict | None:
    rows = _ca12a_rows(start, end)
    if rows is None:
        return None
    amount = lambda line: int(rows.get(line, {}).get("amount") or 0)  # noqa: E731
    book_assets = _euros(totals["assets"]["deductible_cents"])
    book_other = _euros(totals["other"]["deductible_cents"])
    declared = amount("17") + amount("18") - amount("14")
    return {"form": vr.CA12A, "validated": vr.return_for(start, vr.CA12A) is not None,
            "book_assets": book_assets, "book_other": book_other, "book_total": book_assets + book_other,
            "return_17": amount("17"), "return_18": amount("18"), "return_14": amount("14"), "return_total": declared,
            "ok": book_assets + book_other == declared}
