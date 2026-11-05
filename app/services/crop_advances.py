"""Avances aux cultures (lot AG4.c, claudedocs/design_inventaire_agricole.md § 5, AGD21 Q-S6).

- **Fiche** : culture en terre à la clôture (production, surface, implantation, cycle) ; elle crée et alimente sa ligne
  d'inventaire 31151 (cycle court) ou 31141 (cycle long), méthode « fiche d'avance aux cultures ».
- **Coût standard** (méthode du guide CEGARA) : barème de l'exploitation par ha et par mois calendaire, en trois
  composantes ; cumul du mois d'implantation au mois de clôture inclus, × surface. Variantes :
  F = approvisionnements + mécanisation + main-d'œuvre ; M1 = mécanisation + main-d'œuvre ; M2 = mécanisation ;
  en M1 et M2, les approvisionnements sont pris au coût réel (charges cochées).
- **Coût réel** (art. 72 A, liste fermée) : charges de l'exercice cochées par rubrique, avec une quote-part ; une même
  ligne d'écriture ne se répartit pas au-delà de 100 % entre les cultures.
- Le prix de détail est interdit (PCG 618-14) ; la dépréciation se saisit sur la ligne d'inventaire.
"""
from __future__ import annotations

import csv
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy import func

from app.extensions import db
from app.models import (
    Account, CropAdvance, CropAdvanceCost, CropStandard, CropStandardRow, FiscalYear, JournalEntry, JournalLine, StockLine,
)
from app.models.journal_entry import CLOSING_SOURCES, SOURCE_INVENTORY
from app.models.stock import CROP_COMPONENTS, CROP_METHODS, CROP_RUBRICS, CROP_SUPPLY_RUBRICS
from app.services.stock_inventory import StockError, _editable, classify

ACCOUNTS = {"short": "31151", "long": "31141"}
# Comptes proposés par rubrique de l'art. 72 A (charges de l'exercice) ; fermage, assurance, frais généraux exclus.
RUBRIC_ACCOUNTS = {"seeds": ("60112",), "fertilizers": ("60111",), "treatments": ("60113",), "labour": ("641",),
                   "machinery": ("6051", "60614", "615", "6132", "6811")}
COMPONENTS_BY_METHOD = {"standard_f": ("supplies", "machinery", "labour"), "standard_m1": ("machinery", "labour"),
                        "standard_m2": ("machinery",), "actual": ()}
MONTHS = {"janvier": 1, "janv": 1, "février": 2, "fevrier": 2, "févr": 2, "fevr": 2, "mars": 3, "avril": 4, "avr": 4,
          "mai": 5, "juin": 6, "juillet": 7, "juil": 7, "août": 8, "aout": 8, "septembre": 9, "sept": 9, "octobre": 10,
          "oct": 10, "novembre": 11, "nov": 11, "décembre": 12, "decembre": 12, "déc": 12, "dec": 12}
COMPONENT_NAMES = {"approvisionnements": "supplies", "approvisionnement": "supplies", "appro": "supplies",
                   "mécanisation": "machinery", "mecanisation": "machinery", "méca": "machinery",
                   "main-d'œuvre": "labour", "main d'œuvre": "labour", "main-d'oeuvre": "labour", "main d'oeuvre": "labour",
                   "mo": "labour", **{k: k for k in CROP_COMPONENTS}}


# ------------------------------------------------------------------ calcul

def months(planted_on: date, end: date) -> list[tuple[int, int]]:
    """Mois (année, mois) de l'implantation à la clôture inclus."""
    out, year, month = [], planted_on.year, planted_on.month
    while (year, month) <= (end.year, end.month):
        out.append((year, month))
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return out


def _times(surface: Decimal, cents: int) -> int:
    return int((Decimal(surface) * cents).quantize(Decimal(1), ROUND_HALF_UP))


def value(advance: CropAdvance, fy: FiscalYear) -> tuple[int | None, dict, list[str]]:
    """(valeur, détail par composante et par rubrique, avertissements) de l'avance à la clôture."""
    warnings: list[str] = []
    detail = {"components": {}, "costs": {}, "months": 0}
    if advance.planted_on > fy.end_date:
        return 0, detail, ["Implantée après la clôture : pas d'avance aux cultures."]
    span = months(advance.planted_on, fy.end_date)
    detail["months"] = len(span)
    total = 0
    components = COMPONENTS_BY_METHOD[advance.method]
    if components:
        standard = advance.standard
        if standard is None:
            return None, detail, ["Barème de coût standard à choisir."]
        if len(span) > 12:
            warnings.append("Plus de 12 mois depuis l'implantation : le barème n'est cumulé que sur 12 mois (cycle long ?).")
            span = span[-12:]
        wanted = {m for _, m in span}
        per_ha = {c: sum(r.amount_cents for r in standard.rows if r.component == c and r.month in wanted) for c in components}
        for component, cents in per_ha.items():
            detail["components"][component] = _times(advance.surface_ha, cents)
        total += sum(detail["components"].values())
        if not any(per_ha.values()):
            warnings.append("Barème vide pour ces mois.")
        if standard.labour_assumption and "labour" in components:
            detail["labour_assumption"] = standard.labour_assumption
    rubrics = tuple(CROP_RUBRICS) if advance.method == "actual" else CROP_SUPPLY_RUBRICS if advance.method != "standard_f" else ()
    for cost in advance.costs:
        if cost.rubric in rubrics:
            detail["costs"][cost.rubric] = detail["costs"].get(cost.rubric, 0) + cost.amount_cents
    total += sum(detail["costs"].values())
    ignored = [c for c in advance.costs if c.rubric not in rubrics]
    if ignored:
        warnings.append(f"{len(ignored)} charge(s) non prises par la méthode choisie (comptées dans le barème).")
    if advance.method == "actual" and not advance.costs:
        warnings.append("Aucune charge cochée.")
    return total, detail, warnings


# ------------------------------------------------------------------ fiche

def _decimal(value, field, label, limit=Decimal(100000)) -> Decimal:
    try:
        number = Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError):
        raise StockError(f"{label} : nombre attendu.", field) from None
    if not Decimal(0) < number < limit:
        raise StockError(f"{label} : nombre positif attendu.", field)
    return number.quantize(Decimal("0.0001"))


def _account(cycle: str) -> tuple[Account, Account]:
    code = ACCOUNTS[cycle]
    account = Account.query.filter_by(code=code, is_header=False).first()
    variation_code = classify(code)[1]["variation"]
    variation = Account.query.filter_by(code=variation_code, is_header=False).first()
    if account is None or variation is None:
        raise StockError(f"Comptes {code} / {variation_code} absents du plan.", "cycle")
    return account, variation


def _apply(advance: CropAdvance, data: dict, creating: bool) -> None:
    unknown = set(data) - {"activity_id", "production", "surface_ha", "planted_on", "campaign", "cycle", "plots", "method",
                           "crop_standard_id", "notes"}
    if unknown:
        raise StockError(f"Champ inconnu : {sorted(unknown)[0]}.", sorted(unknown)[0])
    from app.services import analytic                     # lot AG8.c
    analytic.apply_activity(advance, data, StockError)
    if creating or "production" in data:
        production = str(data.get("production") or "").strip()[:120]
        if not production:
            raise StockError("Production obligatoire.", "production")
        advance.production = production
    if creating or "surface_ha" in data:
        advance.surface_ha = _decimal(data.get("surface_ha"), "surface_ha", "Surface (ha)")
    if creating or "planted_on" in data:
        try:
            advance.planted_on = date.fromisoformat(str(data.get("planted_on") or "")[:10])
        except ValueError:
            raise StockError("Date d'implantation : AAAA-MM-JJ.", "planted_on") from None
    if "campaign" in data:
        campaign = data["campaign"]
        if campaign is not None and (isinstance(campaign, bool) or not isinstance(campaign, int) or not 2000 <= campaign <= 2100):
            raise StockError("Campagne de récolte : année attendue.", "campaign")
        advance.campaign = campaign
    if creating or "cycle" in data:
        cycle = data.get("cycle") or "short"
        if cycle not in ACCOUNTS:
            raise StockError("Cycle court ou long.", "cycle")
        advance.cycle = cycle
    if creating or "method" in data:
        method = data.get("method") or "actual"
        if method not in CROP_METHODS:
            raise StockError("Méthode inconnue.", "method")
        advance.method = method
    if "crop_standard_id" in data:
        sid = data["crop_standard_id"]
        if sid is not None and (not isinstance(sid, int) or db.session.get(CropStandard, sid) is None):
            raise StockError("Barème introuvable.", "crop_standard_id")
        advance.crop_standard_id = sid
    for field, limit in (("plots", 300), ("notes", 5000)):
        if field in data:
            setattr(advance, field, str(data[field] or "").strip()[:limit] or None)


def line_of(advance: CropAdvance) -> StockLine | None:
    return StockLine.query.filter_by(crop_advance_id=advance.id).first() if advance.id else None


def _sync_line(advance: CropAdvance, fy: FiscalYear) -> StockLine:
    from app.services import stock_inventory

    account, variation = _account(advance.cycle)
    line = line_of(advance)
    if line is None:
        position = (db.session.query(func.max(StockLine.position)).filter_by(fiscal_year_id=fy.id).scalar() or 0) + 1
        line = StockLine(fiscal_year_id=fy.id, category="crop_advances", method="crop_advance", position=position,
                         crop_advance_id=advance.id, variation_account_id=variation.id)
        db.session.add(line)
    elif line.account_id != account.id:
        line.variation_account_id = variation.id
    line.account_id, line.unit = account.id, "ha"
    line.label = f"Avance aux cultures — {advance.production}"[:200]
    line.production, line.quantity = advance.production, advance.surface_ha
    db.session.flush()
    db.session.refresh(line)
    stock_inventory.recompute(line, fy)
    db.session.flush()
    return line


def create(fy: FiscalYear, data: dict) -> CropAdvance:
    _editable(fy)
    advance = CropAdvance(fiscal_year_id=fy.id)
    _apply(advance, data, creating=True)
    db.session.add(advance)
    db.session.flush()
    _sync_line(advance, fy)
    return advance


def update(advance: CropAdvance, data: dict) -> CropAdvance:
    fy = db.session.get(FiscalYear, advance.fiscal_year_id)
    _editable(fy)
    _apply(advance, data, creating=False)
    db.session.flush()
    _sync_line(advance, fy)
    return advance


def delete(advance: CropAdvance) -> None:
    fy = db.session.get(FiscalYear, advance.fiscal_year_id)
    _editable(fy)
    line = line_of(advance)
    if line is not None:
        db.session.delete(line)
    db.session.delete(advance)
    db.session.flush()


def refresh_line(advance: CropAdvance) -> None:
    from app.services import stock_inventory

    line = line_of(advance)
    if line is not None:
        stock_inventory.recompute(line, db.session.get(FiscalYear, advance.fiscal_year_id))
        db.session.flush()


# ------------------------------------------------------------------ charges (art. 72 A)

def _rubric_of(code: str) -> str | None:
    best = None
    for rubric, prefixes in RUBRIC_ACCOUNTS.items():
        for prefix in prefixes:
            if code.startswith(prefix) and (best is None or len(prefix) > best[1]):
                best = (rubric, len(prefix))
    return best[0] if best else None


def _line_amount(line: JournalLine) -> int:
    return line.debit_cents - line.credit_cents


def _shares_used(journal_line_id: int, exclude_cost_id: int | None = None) -> int:
    query = db.session.query(func.coalesce(func.sum(CropAdvanceCost.share_bp), 0)).filter(
        CropAdvanceCost.journal_line_id == journal_line_id)
    if exclude_cost_id:
        query = query.filter(CropAdvanceCost.id != exclude_cost_id)
    return int(query.scalar() or 0)


def proposals(advance: CropAdvance) -> list[dict]:
    """Lignes d'écriture de l'exercice sur les comptes des rubriques de l'art. 72 A, hors clôture et à-nouveaux."""
    fy = db.session.get(FiscalYear, advance.fiscal_year_id)
    prefixes = [p for values in RUBRIC_ACCOUNTS.values() for p in values]
    rows = (JournalLine.query.join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
            .join(Account, Account.id == JournalLine.account_id)
            .filter(JournalEntry.fiscal_year_id == fy.id, db.or_(*[Account.code.like(f"{p}%") for p in prefixes]),
                    db.or_(JournalEntry.source.is_(None), JournalEntry.source.notin_((*CLOSING_SOURCES, SOURCE_INVENTORY))))
            .order_by(JournalEntry.entry_date, JournalLine.id).all())
    mine = {c.journal_line_id: c for c in advance.costs if c.journal_line_id}
    out = []
    for line in rows:
        amount = _line_amount(line)
        if amount <= 0:
            continue
        used = _shares_used(line.id)
        out.append({"journal_line_id": line.id, "date": line.entry.entry_date.isoformat(), "account": line.account.code,
                    "label": line.label or line.entry.description or "", "amount_cents": amount,
                    "rubric": _rubric_of(line.account.code), "rubric_label": CROP_RUBRICS[_rubric_of(line.account.code)],
                    "selected": line.id in mine, "cost_id": mine[line.id].id if line.id in mine else None,
                    "share_used_bp": used, "share_free_bp": max(10000 - used, 0)})
    return out


def add_cost(advance: CropAdvance, data: dict) -> CropAdvanceCost:
    _editable(db.session.get(FiscalYear, advance.fiscal_year_id))
    unknown = set(data) - {"journal_line_id", "share_bp", "rubric", "label", "amount_cents"}
    if unknown:
        raise StockError(f"Champ inconnu : {sorted(unknown)[0]}.", sorted(unknown)[0])
    if data.get("journal_line_id") is not None:
        line = db.session.get(JournalLine, data["journal_line_id"]) if isinstance(data["journal_line_id"], int) else None
        proposal = next((p for p in proposals(advance) if line is not None and p["journal_line_id"] == line.id), None)
        if proposal is None:
            raise StockError("Charge introuvable parmi celles de l'art. 72 A pour l'exercice (fermage, assurance et frais "
                             "généraux sont exclus).", "journal_line_id")
        if proposal["selected"]:
            raise StockError("Charge déjà rattachée à cette culture.", "journal_line_id", 409)
        share = data.get("share_bp", 10000)
        if isinstance(share, bool) or not isinstance(share, int) or not 0 < share <= 10000:
            raise StockError("Quote-part entre 0,01 % et 100 %.", "share_bp")
        if share > proposal["share_free_bp"]:
            raise StockError(f"Quote-part restante sur cette charge : {proposal['share_free_bp'] / 100:.2f} %."
                             .replace(".", ","), "share_bp")
        cost = CropAdvanceCost(advance=advance, rubric=data.get("rubric") or proposal["rubric"], journal_line_id=line.id,
                               label=proposal["label"][:300] or proposal["account"], base_cents=proposal["amount_cents"],
                               share_bp=share, amount_cents=round(proposal["amount_cents"] * share / 10000))
    else:
        rubric = data.get("rubric")
        if rubric not in CROP_RUBRICS:
            raise StockError("Rubrique de l'art. 72 A à choisir.", "rubric")
        label = str(data.get("label") or "").strip()[:300]
        if not label:
            raise StockError("Libellé obligatoire.", "label")
        amount = data.get("amount_cents")
        if isinstance(amount, bool) or not isinstance(amount, int) or not 0 < amount <= 10 ** 11:
            raise StockError("Montant positif attendu.", "amount_cents")
        cost = CropAdvanceCost(advance=advance, rubric=rubric, label=label, base_cents=amount, share_bp=10000,
                               amount_cents=amount)
    if cost.rubric not in CROP_RUBRICS:
        raise StockError("Rubrique inconnue.", "rubric")
    db.session.add(cost)
    db.session.flush()
    refresh_line(advance)
    return cost


def delete_cost(advance: CropAdvance, cost: CropAdvanceCost) -> None:
    _editable(db.session.get(FiscalYear, advance.fiscal_year_id))
    if cost.crop_advance_id != advance.id:
        raise StockError("Charge introuvable.", status=404)
    db.session.delete(cost)
    db.session.flush()
    db.session.expire(advance)
    refresh_line(advance)


# ------------------------------------------------------------------ barèmes

def save_standard(row: CropStandard | None, data: dict) -> CropStandard:
    row = row or CropStandard()
    production = str(data.get("production", row.production) or "").strip()[:120]
    if not production:
        raise StockError("Production obligatoire.", "production")
    year = data.get("year", row.year)
    if isinstance(year, bool) or not isinstance(year, int) or not 2000 <= year <= 2100:
        raise StockError("Année attendue.", "year")
    duplicate = CropStandard.query.filter_by(production=production, year=year)
    if row.id is not None:
        duplicate = duplicate.filter(CropStandard.id != row.id)
    if duplicate.first() is not None:
        raise StockError("Un barème existe déjà pour cette production et cette année.", "production", 409)
    row.production, row.year = production, year
    row.source = str(data.get("source", row.source) or "").strip()[:300] or None
    row.labour_assumption = str(data.get("labour_assumption", row.labour_assumption) or "").strip()[:200] or None
    if row.id is None:
        db.session.add(row)
    db.session.flush()
    if "rows" in data:
        set_rows(row, data["rows"])
    return row


def set_rows(standard: CropStandard, rows) -> None:
    if not isinstance(rows, list):
        raise StockError("Lignes du barème attendues.", "rows")
    clean: dict[tuple[str, int], int] = {}
    for item in rows:
        if not isinstance(item, dict):
            raise StockError("Ligne de barème invalide.", "rows")
        component, month, amount = item.get("component"), item.get("month"), item.get("amount_cents")
        if component not in CROP_COMPONENTS or isinstance(month, bool) or not isinstance(month, int) or not 1 <= month <= 12:
            raise StockError("Composante et mois (1 à 12) attendus.", "rows")
        if isinstance(amount, bool) or not isinstance(amount, int) or not 0 <= amount <= 10 ** 9:
            raise StockError("Montant par ha positif attendu.", "rows")
        clean[(component, month)] = amount
    standard.rows.clear()
    db.session.flush()
    for (component, month), amount in sorted(clean.items(), key=lambda x: (x[0][1], x[0][0])):
        if amount:
            standard.rows.append(CropStandardRow(component=component, month=month, amount_cents=amount))
    db.session.flush()
    for advance in CropAdvance.query.filter_by(crop_standard_id=standard.id):
        refresh_line(advance)


def delete_standard(standard: CropStandard) -> None:
    for advance in CropAdvance.query.filter_by(crop_standard_id=standard.id):
        if db.session.get(FiscalYear, advance.fiscal_year_id).status != "open":
            raise StockError("Barème utilisé par l'inventaire d'un exercice clôturé.", status=409)
    db.session.delete(standard)
    db.session.flush()


def import_standards(content: bytes) -> int:
    """CSV « Production ; Année ; Composante ; Mois ; Montant par ha » (une ligne par composante et par mois) ;
    remplace les lignes des barèmes cités ; tout ou rien."""
    text = content.decode("utf-8-sig", errors="replace")
    delimiter = ";" if text.count(";") >= text.count(",") else ","
    rows = [r for r in csv.reader(text.splitlines(), delimiter=delimiter) if any(c.strip() for c in r)]
    if len(rows) < 2:
        raise StockError("Fichier vide : en-têtes puis une ligne par production, composante et mois.", "file")
    grouped: dict[tuple[str, int], list[dict]] = {}
    for number, row in enumerate(rows[1:], start=2):
        if len(row) < 5:
            raise StockError(f"Ligne {number} : 5 colonnes attendues.", "file")
        production, year, component, month, amount = (c.strip() for c in row[:5])
        try:
            year_int = int(year)
            month_int = int(month) if month.isdigit() else MONTHS[month.lower().rstrip(".")]
            cents = int((Decimal(amount.replace(" ", "").replace(",", ".")) * 100).quantize(Decimal(1), ROUND_HALF_UP))
        except (ValueError, KeyError, InvalidOperation):
            raise StockError(f"Ligne {number} : année, mois ou montant illisible.", "file") from None
        key = COMPONENT_NAMES.get(component.lower())
        if key is None:
            raise StockError(f"Ligne {number} : composante « {component} » inconnue.", "file")
        grouped.setdefault((production, year_int), []).append({"component": key, "month": month_int, "amount_cents": cents})
    for (production, year), items in grouped.items():
        standard = CropStandard.query.filter_by(production=production, year=year).first()
        standard = save_standard(standard, {"production": production, "year": year})
        set_rows(standard, items)
    return len(grouped)


# ------------------------------------------------------------------ restitution

def standard_payload(s: CropStandard) -> dict:
    return {"id": s.id, "production": s.production, "year": s.year, "source": s.source,
            "labour_assumption": s.labour_assumption,
            "rows": [{"component": r.component, "month": r.month, "amount_cents": r.amount_cents} for r in s.rows]}


def _activity(activity_id) -> dict:
    from app.services import analytic
    return analytic.activity_fields(activity_id)


def payload(advance: CropAdvance, with_proposals: bool = False) -> dict:
    fy = db.session.get(FiscalYear, advance.fiscal_year_id)
    total, detail, warnings = value(advance, fy)
    line = line_of(advance)
    data = {"id": advance.id, **_activity(advance.activity_id), "production": advance.production, "surface_ha": str(advance.surface_ha),
            "planted_on": advance.planted_on.isoformat(), "campaign": advance.campaign, "cycle": advance.cycle,
            "account_code": ACCOUNTS[advance.cycle], "plots": advance.plots, "method": advance.method,
            "method_label": CROP_METHODS[advance.method], "crop_standard_id": advance.crop_standard_id,
            "notes": advance.notes, "value_cents": total, "detail": detail, "warnings": warnings,
            "line_id": line.id if line is not None else None,
            "costs": [{"id": c.id, "rubric": c.rubric, "rubric_label": CROP_RUBRICS[c.rubric], "label": c.label,
                       "journal_line_id": c.journal_line_id, "base_cents": c.base_cents, "share_bp": c.share_bp,
                       "amount_cents": c.amount_cents} for c in advance.costs]}
    if with_proposals:
        data["proposals"] = proposals(advance)
    return data


def meta() -> dict:
    return {"methods": [{"value": k, "label": v} for k, v in CROP_METHODS.items()],
            "rubrics": [{"value": k, "label": v} for k, v in CROP_RUBRICS.items()],
            "components": [{"value": k, "label": v} for k, v in CROP_COMPONENTS.items()],
            "standards": [standard_payload(s) for s in CropStandard.query.order_by(CropStandard.production, CropStandard.year.desc())]}
