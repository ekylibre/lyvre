"""Régimes des bénéfices agricoles (lot AG6.e, claudedocs/design_fiscalite_ba.md § 7, AGD23 ; audit § 1.2, § 1.3, § 3.2, § 3.5).

- **Recettes par année civile** : produits 70 et 74 (hors quote-part de subventions d'investissement 747) des écritures
  de Lyvre, ou saisie d'une année antérieure (`BaHistoryYear`, qui l'emporte). Les comptes repérés « façon » comptent
  × 3 pour les seuils (art. 69) ; les comptes repérés « accessoire » sont mis à part (art. 75). Le montant TTC ajoute
  la TVA collectée (4457) de la même écriture au prorata des produits.
- **Moyenne triennale et régime** (art. 69, 71) : moyenne des 3 années civiles closes à la fin de l'exercice, seuils
  datés `ba.micro.*` / `ba.normal.*`, GAEC : × associés (60 % au-delà de `ba.gaec.threshold_cents`) ; régime de plein
  droit de l'exercice suivant comparé au régime en cours (Structure › Fiscalité), alerte de changement.
- **Passage du micro au réel** (art. 72 E bis) : créances du bilan d'ouverture (41, 441) × (1 − abattement micro),
  réintégrées le premier exercice au réel.
- **Simulation micro ou réel** : bénéfice forfaitaire (moyenne × (1 − 87 %), minimum 305 €) contre résultat réel.
- **Revenus accessoires** (art. 75) : moyenne TTC des 3 années civiles précédant l'ouverture de l'exercice (l'année
  précédente seule les 3 premières années), ≤ 50 % des recettes agricoles et ≤ 100 000 € (× associés en GAEC, 4 au
  plus) ; dépassement en société civile : IS de plein droit (art. 206-2).
- **Étalement 75-0 A** : revenu exceptionnel proposé (bénéfice au-delà de 25 000 € ou de la moyenne des 3 exercices
  précédents si elle est supérieure, quand il dépasse 1,5 × cette moyenne), rattaché par septièmes ; exclu avec le
  blocage 72 B bis, et pour le 1-a avec la moyenne triennale 75-0 B.
- **Historique 75-0 B** : bénéfices des exercices par associé ; l'option se déclare au niveau du foyer (Q-F8).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func

from app.extensions import db
from app.models import (Account, Associate, BaHistoryYear, FiscalYear, IncomeSpread, JournalEntry, JournalLine,
                        TaxOption)
from app.models.journal_entry import SOURCE_OPENING
from app.models.tax_result import ACCOUNT_INCOME_CLASSES, SPREAD_KINDS
from app.services import reg_params
from app.services.tax_result import TaxResultError

REGIME_ORDER = {"micro": 0, "simplified": 1, "normal": 2}
REGIME_LABELS = {"micro": "Micro-BA", "simplified": "Réel simplifié", "normal": "Réel normal"}
CIVIL_FORMS = {"EARL", "EARL_U", "GAEC", "SCEA", "GFA"}


def _p(key: str, on: date, default=None):
    return reg_params.value(key, on, default=default)


def _form() -> str | None:
    from app.services import organization
    return organization.get().legal_form_code


def _option(code: str, on: date) -> bool:
    return any(o.start_date <= on and (o.renounced_on is None or on < o.renounced_on)
               for o in TaxOption.query.filter_by(code=code))


def _associates_count(operators_only: bool = True) -> int:
    query = Associate.query.filter_by(is_operator=True) if operators_only else Associate.query
    return query.count()


# ------------------------------------------------------------------ recettes par année civile

def _is_receipt(code: str) -> bool:
    return (code.startswith("70") or code.startswith("74")) and not code.startswith("747")


def lyvre_receipts(year: int) -> dict | None:
    """Recettes de l'année civile tirées des écritures (None si Lyvre n'a aucune écriture cette année-là)."""
    start, end = date(year, 1, 1), date(year, 12, 31)
    if not db.session.query(JournalEntry.query.filter(JournalEntry.entry_date.between(start, end),
                                                      JournalEntry.source != SOURCE_OPENING).exists()).scalar():
        return None
    rows = (db.session.query(JournalLine.entry_id, Account.code, Account.ba_income_class,
                             JournalLine.credit_cents - JournalLine.debit_cents)
            .join(Account, Account.id == JournalLine.account_id)
            .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
            .filter(JournalEntry.entry_date.between(start, end), JournalEntry.source != SOURCE_OPENING,
                    db.or_(Account.code.like("70%"), Account.code.like("74%"), Account.code.like("4457%")))
            .all())
    by_entry = defaultdict(lambda: {"agricultural": 0, "custom_work": 0, "accessory": 0, "vat": 0})
    for entry_id, code, klass, amount in rows:
        bucket = by_entry[entry_id]
        if code.startswith("4457"):
            bucket["vat"] += amount
        elif _is_receipt(code):
            bucket[klass if klass in ACCOUNT_INCOME_CLASSES else "agricultural"] += amount
    out = {"agricultural_ht": 0, "custom_work_ht": 0, "accessory_ht": 0, "agricultural_ttc": 0, "accessory_ttc": 0}
    for bucket in by_entry.values():
        products = bucket["agricultural"] + bucket["custom_work"] + bucket["accessory"]
        rate = bucket["vat"] / products if products > 0 and bucket["vat"] > 0 else 0
        out["agricultural_ht"] += bucket["agricultural"]
        out["custom_work_ht"] += bucket["custom_work"]
        out["accessory_ht"] += bucket["accessory"]
        out["agricultural_ttc"] += round((bucket["agricultural"] + bucket["custom_work"]) * (1 + rate))
        out["accessory_ttc"] += round(bucket["accessory"] * (1 + rate))
    return out


def year_receipts(year: int) -> dict:
    """Recettes retenues d'une année : seuils (HT, façon × 3) et revenus accessoires (TTC). La saisie l'emporte."""
    saved = BaHistoryYear.query.filter_by(year=year).first()
    lyvre = lyvre_receipts(year)
    row = {"year": year, "threshold_cents": None, "agricultural_ttc_cents": None, "accessory_ttc_cents": None,
           "source": "missing"}
    if lyvre is not None:
        row.update(threshold_cents=lyvre["agricultural_ht"] + 3 * lyvre["custom_work_ht"],
                   agricultural_ttc_cents=lyvre["agricultural_ttc"], accessory_ttc_cents=lyvre["accessory_ttc"],
                   source="lyvre", custom_work_ht_cents=lyvre["custom_work_ht"], accessory_ht_cents=lyvre["accessory_ht"])
    if saved is not None:
        if saved.agricultural_receipts_cents is not None:
            row.update(threshold_cents=saved.agricultural_receipts_cents, source="entered")
            if row["agricultural_ttc_cents"] is None or lyvre is None:
                row["agricultural_ttc_cents"] = saved.agricultural_receipts_cents
        if saved.accessory_receipts_cents is not None:
            row.update(accessory_ttc_cents=saved.accessory_receipts_cents, source="entered")
        row["note"] = saved.note
    return row


def _average(values: list[int | None]) -> int | None:
    known = [v for v in values if v is not None]
    return round(sum(known) / len(known)) if known else None


# ------------------------------------------------------------------ régime (art. 69, 71)

def micro_allowed(on: date) -> tuple[bool, str | None]:
    from app.services import organization
    form = _form()
    if _option("is_option", on):
        return False, "Option pour l'IS."
    if form in CIVIL_FORMS and form != "EARL_U":
        created = organization.get().created_on
        cutoff = _p("ba.micro.company_cutoff_date", on)
        if created is None or cutoff is None or created >= date.fromisoformat(cutoff):
            return False, "Société créée depuis le 01/01/1997 : réel obligatoire (art. 69 D)."
    return True, None


def thresholds(on: date, average: int | None) -> dict:
    micro, normal = _p("ba.micro.threshold_cents", on), _p("ba.normal.threshold_cents", on)
    detail = None
    if _form() == "GAEC" and micro is not None and normal is not None:
        n = max(_associates_count(operators_only=False), 1)
        gaec_cap = _p("ba.gaec.threshold_cents", on)
        ratio = 10000 if average is None or gaec_cap is None or average <= gaec_cap else _p("ba.gaec.reduced_ratio_bp", on, 10000)
        micro, normal = round(micro * n * ratio / 10000), round(normal * n * ratio / 10000)
        detail = f"GAEC : seuils × {n} associés" + (f" × {ratio / 100:.0f} %" if ratio != 10000 else "")
    return {"micro_cents": micro, "normal_cents": normal, "detail": detail}


def regime(fy: FiscalYear) -> dict:
    """Moyenne triennale des recettes et régime de plein droit de l'exercice suivant."""
    from app.services import tax_profile
    year = fy.end_date.year
    years = [year_receipts(y) for y in (year - 2, year - 1, year)]
    average = _average([y["threshold_cents"] for y in years])
    limits = thresholds(fy.end_date, average)
    current = tax_profile.current_value("ba_regime", fy.end_date)
    next_start = fy.end_date + timedelta(days=1)
    allowed, why = micro_allowed(next_start)
    by_law = None
    if average is not None and limits["micro_cents"] is not None:
        by_law = ("micro" if average <= limits["micro_cents"] and allowed
                  else "simplified" if average <= limits["normal_cents"] else "normal")
    floor = "normal" if _option("ba_normal_option", next_start) else "simplified" if _option("ba_simplified_option", next_start) else None
    expected = by_law
    if expected and floor and REGIME_ORDER[floor] > REGIME_ORDER[expected]:
        expected = floor
    warnings = []
    if any(y["threshold_cents"] is None for y in years):
        warnings.append("Recettes d'une année inconnues : saisissez-les (années antérieures à Lyvre) pour la moyenne.")
    if (fy.end_date - fy.start_date).days < 360 or fy.end_date.month != 12:
        warnings.append("Exercice décalé ou incomplet : moyenne calculée sur les années civiles, à vérifier.")
    change = None
    if expected and current and expected != current:
        if REGIME_ORDER[expected] > REGIME_ORDER[current]:
            change = {"direction": "up", "label": f"{REGIME_LABELS[expected]} de plein droit à compter du "
                                                  f"{next_start:%d/%m/%Y} (moyenne au-dessus du seuil)."}
        else:
            change = {"direction": "down", "label": f"Moyenne sous le seuil : retour au {REGIME_LABELS[expected].lower()} "
                                                    "possible, conditions et option à vérifier."}
    if current is None:
        warnings.append("Régime des bénéfices agricoles non renseigné (Structure › Fiscalité).")
    return {"years": years, "average_cents": average, "thresholds": limits, "current": current,
            "current_label": REGIME_LABELS.get(current), "by_law": by_law, "expected": expected,
            "expected_label": REGIME_LABELS.get(expected), "next_start": next_start.isoformat(),
            "micro_allowed": allowed, "micro_reason": why, "change": change, "warnings": warnings}


# ------------------------------------------------------------------ passage micro → réel (art. 72 E bis)

def _first_real_year(fy: FiscalYear) -> bool:
    from app.services import tax_profile
    now = tax_profile.current_value("ba_regime", fy.start_date)
    before = tax_profile.current_value("ba_regime", fy.start_date - timedelta(days=1))
    return now in ("simplified", "normal") and before == "micro"


def opening_receivables(fy: FiscalYear) -> int:
    rows = (db.session.query(Account.code, func.sum(JournalLine.debit_cents - JournalLine.credit_cents))
            .join(JournalLine, JournalLine.account_id == Account.id)
            .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
            .filter(JournalEntry.fiscal_year_id == fy.id, JournalEntry.source == SOURCE_OPENING,
                    db.or_(Account.code.like("41%"), Account.code.like("441%")))
            .group_by(Account.code).all())
    return sum(max(int(total or 0), 0) for _, total in rows)


def micro_to_real_lines(fy: FiscalYear) -> list[dict]:
    if not _first_real_year(fy):
        return []
    receivables = opening_receivables(fy)
    allowance = _p("ba.micro.allowance_bp", fy.end_date)
    if not receivables or allowance is None:
        return []
    return [{"key": "micro_to_real", "source": "ba_regime", "link": "/configuration/organization/?tab=tax",
             "amount_cents": round(receivables * (10000 - allowance) / 10000),
             "label": f"Passage du micro-BA au réel : créances d'ouverture (41, 441) après abattement de "
                      f"{allowance / 100:.0f} % (art. 72 E bis)"}]


# ------------------------------------------------------------------ simulation micro ou réel

def micro_profit(average: int | None, on: date) -> int | None:
    """Bénéfice micro-BA : moyenne des recettes moins l'abattement, au moins le minimum (paramètres datés).
    Règle unique, partagée avec la calculette 08 (lot AG12.a)."""
    allowance, minimum = _p("ba.micro.allowance_bp", on), _p("ba.micro.minimum_cents", on, 0)
    if average is None or allowance is None:
        return None
    return max(round(average * (10000 - allowance) / 10000), minimum or 0)


def simulation(fy: FiscalYear) -> dict:
    from app.services import closing, tax_result
    year = fy.end_date.year
    allowed, why = micro_allowed(fy.end_date)
    receipts = []
    for y in (year - 2, year - 1, year):
        data = lyvre_receipts(y)
        saved = BaHistoryYear.query.filter_by(year=y).first()
        value = saved.agricultural_receipts_cents if saved and saved.agricultural_receipts_cents is not None else (
            data["agricultural_ht"] + data["custom_work_ht"] if data else None)
        receipts.append({"year": y, "receipts_cents": value})
    average = _average([r["receipts_cents"] for r in receipts])
    allowance = _p("ba.micro.allowance_bp", fy.end_date)
    micro = micro_profit(average, fy.end_date)
    if tax_result.enabled():
        real, basis = tax_result.compute(fy)["fiscal_result_cents"], "résultat fiscal (après abattement JA et DEP)"
    else:
        real, basis = closing.result(fy)["result_cents"], "résultat de trésorerie, sans stocks ni créances : estimation"
    best = None
    if allowed and micro is not None:
        best = "micro" if micro <= real else "real"
    return {"micro_allowed": allowed, "micro_reason": why, "receipts": receipts, "average_cents": average,
            "allowance_bp": allowance, "micro_profit_cents": micro, "real_result_cents": real, "real_basis": basis,
            "best": best,
            "deadline": "Option pour le réel : dans le délai de déclaration des revenus de l'année précédente (art. 69 IV) ; "
                        "elle vaut un an, reconduite tacitement.",
            "notes": ["Le micro-BA ne donne droit ni à l'abattement JA, ni à la DEP ; les plus-values se calculent comme au réel.",
                      "Recettes micro : encaissements ; Lyvre retient les produits 70 et 74 hors 747 (estimation)."]}


# ------------------------------------------------------------------ revenus accessoires (art. 75)

def accessory(fy: FiscalYear) -> dict:
    from app.services import organization
    on = fy.end_date
    ratio, cap = _p("ba.accessory.ratio_bp", on), _p("ba.accessory.cap_cents", on)
    if ratio is None or cap is None:
        return {"applicable": False, "reason": "Régime des revenus accessoires non paramétré pour cet exercice (art. 75)."}
    start_year = fy.start_date.year
    created = organization.get().created_on
    young = created is not None and created > date(start_year - 3, fy.start_date.month, fy.start_date.day)
    span = [start_year - 1] if young else [start_year - 3, start_year - 2, start_year - 1]
    years = [year_receipts(y) for y in span]
    agri = _average([y["agricultural_ttc_cents"] for y in years])
    acc = _average([y["accessory_ttc_cents"] for y in years])
    multiplier = 1
    if _form() == "GAEC":
        multiplier = max(1, min(_associates_count(), _p("ba.associates.multiplier_cap", on, 4) or 4))
    limit_cap = cap * multiplier
    limit_ratio = round((agri or 0) * ratio / 10000)
    exceeded = acc is not None and acc > 0 and (acc > limit_ratio or acc > limit_cap)
    form = _form()
    consequence = None
    if exceeded:
        consequence = ("is" if form in CIVIL_FORMS else "bic")
    current = lyvre_receipts(fy.end_date.year) or {}
    total_ht = sum(current.get(k, 0) for k in ("agricultural_ht", "custom_work_ht", "accessory_ht"))
    share_bp = round(current.get("accessory_ht", 0) * 10000 / total_ht) if total_ht > 0 else 0
    return {"applicable": True, "years": years, "span": span, "young": young, "agricultural_avg_cents": agri,
            "accessory_avg_cents": acc, "ratio_bp": ratio, "limit_ratio_cents": limit_ratio, "limit_cap_cents": limit_cap,
            "multiplier": multiplier, "exceeded": exceeded, "consequence": consequence,
            "current_share_bp": share_bp, "current_accessory_ht_cents": current.get("accessory_ht", 0),
            "accounts": [{"id": a.id, "code": a.code, "label": a.label, "class": a.ba_income_class}
                         for a in Account.query.filter(Account.is_header.is_(False),
                                                       db.or_(Account.code.like("70%"), Account.code.like("74%")))
                         .order_by(Account.code)]}


# ------------------------------------------------------------------ résultats fiscaux antérieurs

def _years() -> list[FiscalYear]:
    return FiscalYear.query.order_by(FiscalYear.start_date).all()


def fiscal_result_of(fy: FiscalYear) -> int | None:
    """Résultat fiscal d'un exercice : saisi pour l'année de clôture (année antérieure à Lyvre) ou calculé."""
    from app.services import tax_result
    saved = BaHistoryYear.query.filter_by(year=fy.end_date.year).first()
    if saved is not None and saved.fiscal_result_cents is not None:
        return saved.fiscal_result_cents
    if not tax_result.enabled():
        return None
    return tax_result.view(fy)["fiscal_result_cents"]


def previous_results(fy: FiscalYear, count: int = 3) -> list[dict]:
    """Résultats des `count` exercices précédents (exercices de Lyvre, sinon années saisies)."""
    earlier = [y for y in _years() if y.end_date < fy.start_date]
    out = []
    year = fy.end_date.year
    for offset in range(1, count + 1):
        target = year - offset
        match = next((y for y in reversed(earlier) if y.end_date.year == target), None)
        if match is not None:
            out.append({"year": target, "label": match.label, "fiscal_result_cents": fiscal_result_of(match), "source": "lyvre"})
        else:
            saved = BaHistoryYear.query.filter_by(year=target).first()
            value = saved.fiscal_result_cents if saved else None
            out.append({"year": target, "label": str(target), "fiscal_result_cents": value,
                        "source": "entered" if value is not None else "missing"})
    return out


# ------------------------------------------------------------------ étalement 75-0 A

def _seventh(amount: int, index: int, parts: int) -> int:
    return round(amount * (index + 1) / parts) - round(amount * index / parts)


def spread_exclusion(fy: FiscalYear, kind: str) -> str | None:
    if _option("stock_freeze_72_b_bis", fy.end_date):
        return "Option de blocage des stocks (72 B bis) en vigueur : étalement 75-0 A exclu."
    if kind == "profit" and _option("averaging_75_0_b", fy.end_date):
        return "Moyenne triennale (75-0 B) en vigueur : exclusive de l'étalement du bénéfice exceptionnel (75-0 A, 1-a)."
    return None


def spread_proposal(fy: FiscalYear) -> dict:
    from app.services import tax_result
    data = tax_result.compute(fy)
    base = data["fiscal_result_before_ja_cents"] - sum(
        l["amount_cents"] for l in data["lines"] if l["key"].startswith("spread_"))
    previous = previous_results(fy)
    known = [p["fiscal_result_cents"] for p in previous if p["fiscal_result_cents"] is not None]
    threshold, ratio = _p("ba.spread.threshold_cents", fy.end_date), _p("ba.spread.ratio_bp", fy.end_date)
    out = {"base_cents": base, "previous": previous, "average_cents": None, "floor_cents": None, "exceptional_cents": 0,
           "reason": spread_exclusion(fy, "profit")}
    if threshold is None or ratio is None:
        out["reason"] = out["reason"] or "Barème de l'étalement 75-0 A introuvable."
        return out
    if len(known) < 3:
        out["reason"] = out["reason"] or "Résultats des 3 exercices précédents incomplets : saisissez les années manquantes."
        return out
    average = round(sum(known) / 3)
    floor = max(threshold, average)
    out.update(average_cents=average, floor_cents=floor)
    if base > floor and base > round(average * ratio / 10000):
        out["exceptional_cents"] = base - floor
    return out


def spread_schedule(spread: IncomeSpread) -> list[dict]:
    parts = _p("ba.spread.parts", spread.fiscal_year.end_date, 7) or 7
    years = _years()
    index = next((i for i, y in enumerate(years) if y.id == spread.fiscal_year_id), 0)
    out = []
    for k in range(parts):
        fy = years[index + k] if index + k < len(years) else None
        label = fy.label if fy else str(spread.fiscal_year.end_date.year + k)
        out.append({"rank": k + 1, "fiscal_year_id": fy.id if fy else None, "label": label,
                    "amount_cents": _seventh(spread.amount_cents, k, parts)})
    return out


def add_spread(fy: FiscalYear, data: dict) -> IncomeSpread:
    if fy.status == "closed":
        raise TaxResultError("Exercice clôturé : le résultat fiscal est figé.", status=409)
    kind = data.get("kind")
    if kind not in SPREAD_KINDS:
        raise TaxResultError("Type d'étalement inconnu (bénéfice exceptionnel, indemnité d'abattage).", "kind")
    excluded = spread_exclusion(fy, kind)
    if excluded:
        raise TaxResultError(excluded, "kind")
    if IncomeSpread.query.filter_by(fiscal_year_id=fy.id, kind=kind).first():
        raise TaxResultError("Un étalement de ce type existe déjà pour l'exercice.", "kind", 409)
    amount = data.get("amount_cents")
    if isinstance(amount, bool) or not isinstance(amount, int) or not 0 < amount <= 10 ** 11:
        raise TaxResultError("Montant positif en centimes attendu.", "amount_cents")
    reason = (str(data.get("reason") or "").strip()[:300]) or None
    if kind == "profit":
        proposal = spread_proposal(fy)
        if amount > proposal["exceptional_cents"]:
            raise TaxResultError("Montant au-delà du bénéfice exceptionnel calculé "
                                 f"({proposal['exceptional_cents'] / 100:.2f} €).".replace(".", ","), "amount_cents")
    elif reason is None or len(reason) < 5:
        raise TaxResultError("Motif obligatoire : indemnité d'abattage moins la valeur des animaux abattus.", "reason")
    row = IncomeSpread(fiscal_year_id=fy.id, kind=kind, amount_cents=amount, reason=reason)
    db.session.add(row)
    db.session.flush()
    return row


def delete_spread(fy: FiscalYear, spread_id) -> None:
    if fy.status == "closed":
        raise TaxResultError("Exercice clôturé : le résultat fiscal est figé.", status=409)
    row = db.session.get(IncomeSpread, spread_id) if isinstance(spread_id, int) else None
    if row is None or row.fiscal_year_id != fy.id:
        raise TaxResultError("Étalement introuvable.", status=404)
    db.session.delete(row)
    db.session.flush()


def spread_lines(fy: FiscalYear) -> list[dict]:
    lines = []
    for spread in IncomeSpread.query.order_by(IncomeSpread.id):
        for part in spread_schedule(spread):
            if part["fiscal_year_id"] != fy.id:
                continue
            what = SPREAD_KINDS[spread.kind]
            if part["rank"] == 1:
                lines.append({"key": f"spread_{spread.id}", "source": "ba_regime", "amount_cents": part["amount_cents"] - spread.amount_cents,
                              "label": f"{what} : 6/7 étalés sur les exercices suivants"})
            else:
                lines.append({"key": f"spread_{spread.id}_{part['rank']}", "source": "ba_regime", "amount_cents": part["amount_cents"],
                              "label": f"{what} de {spread.fiscal_year.label} : {part['rank']}e septième"})
    return lines


def tax_lines(fy: FiscalYear) -> list[dict]:
    return [*micro_to_real_lines(fy), *spread_lines(fy)]


def spreads_view(fy: FiscalYear) -> dict:
    register = [{"id": s.id, "origin": s.fiscal_year.label, "fiscal_year_id": s.fiscal_year_id, "kind": s.kind,
                 "kind_label": SPREAD_KINDS[s.kind], "amount_cents": s.amount_cents, "reason": s.reason,
                 "schedule": spread_schedule(s)}
                for s in IncomeSpread.query.order_by(IncomeSpread.id) if s.fiscal_year.end_date <= fy.end_date]
    return {"proposal": spread_proposal(fy), "register": register,
            "kinds": [{"value": k, "label": v} for k, v in SPREAD_KINDS.items()],
            "averaging": averaging_history(fy)}


# ------------------------------------------------------------------ historique pour la moyenne triennale (75-0 B)

def averaging_history(fy: FiscalYear) -> dict:
    """Bénéfices de l'exercice et des 2 précédents, total et par associé (exercices de Lyvre)."""
    from app.services import tax_result
    years = [y for y in _years() if y.end_date <= fy.end_date][-3:]
    columns = []
    for y in years:
        data = tax_result.view(y) if tax_result.enabled() else None
        saved = BaHistoryYear.query.filter_by(year=y.end_date.year).first()
        total = saved.fiscal_result_cents if saved and saved.fiscal_result_cents is not None else (
            data["fiscal_result_cents"] if data else None)
        columns.append({"label": y.label, "fiscal_result_cents": total,
                        "associates": {a["associate_id"]: a.get("fiscal_result_cents") for a in (data or {}).get("associates", [])}})
    missing = 3 - len(columns)
    for offset in range(missing, 0, -1):
        target = (years[0].end_date.year if years else fy.end_date.year + 1) - offset
        saved = BaHistoryYear.query.filter_by(year=target).first()
        columns.insert(0, {"label": str(target), "fiscal_result_cents": saved.fiscal_result_cents if saved else None,
                           "associates": {}})
    names = {a.id: a.name for a in Associate.query.order_by(Associate.id)}
    ids = sorted({i for c in columns for i in c["associates"]})
    rows = []
    for associate_id in ids:
        values = [c["associates"].get(associate_id) for c in columns]
        known = [v for v in values if v is not None]
        rows.append({"associate_id": associate_id, "name": names.get(associate_id, "?"), "values": values,
                     "average_cents": round(sum(max(v, 0) for v in known) / 3) if len(known) == 3 else None})
    totals = [c["fiscal_result_cents"] for c in columns]
    return {"labels": [c["label"] for c in columns], "totals": totals,
            "average_cents": round(sum(max(v, 0) for v in totals) / 3) if all(v is not None for v in totals) else None,
            "associates": rows, "option": _option("averaging_75_0_b", fy.end_date)}


# ------------------------------------------------------------------ historique saisi et comptes repérés

def save_history(year, data: dict) -> BaHistoryYear | None:
    if isinstance(year, bool) or not isinstance(year, int) or not 1990 <= year <= date.today().year:
        raise TaxResultError("Année invalide.", "year")
    values = {}
    for field in ("agricultural_receipts_cents", "accessory_receipts_cents", "fiscal_result_cents"):
        value = data.get(field)
        if value in (None, ""):
            values[field] = None
            continue
        if isinstance(value, bool) or not isinstance(value, int) or abs(value) > 10 ** 12:
            raise TaxResultError("Montant en centimes attendu.", field)
        if field != "fiscal_result_cents" and value < 0:
            raise TaxResultError("Recettes positives ou nulles.", field)
        values[field] = value
    row = BaHistoryYear.query.filter_by(year=year).first()
    if all(v is None for v in values.values()):
        if row is not None:
            db.session.delete(row)
            db.session.flush()
        return None
    if row is None:
        row = BaHistoryYear(year=year)
        db.session.add(row)
    for field, value in values.items():
        setattr(row, field, value)
    row.note = (str(data.get("note") or "").strip()[:300]) or None
    db.session.flush()
    return row


def history_rows() -> list[dict]:
    return [{"year": r.year, "agricultural_receipts_cents": r.agricultural_receipts_cents,
             "accessory_receipts_cents": r.accessory_receipts_cents, "fiscal_result_cents": r.fiscal_result_cents,
             "note": r.note} for r in BaHistoryYear.query.order_by(BaHistoryYear.year)]


def set_income_class(account: Account, value) -> Account:
    if value not in (None, "", *ACCOUNT_INCOME_CLASSES):
        raise TaxResultError("Repérage inconnu (accessoire, façon ou aucun).", "ba_income_class")
    if account.is_header or not _is_receipt(account.code):
        raise TaxResultError("Repérage réservé aux comptes de produits 70 et 74 (hors 747).", "ba_income_class")
    account.ba_income_class = value or None
    db.session.flush()
    return account


def view(fy: FiscalYear) -> dict:
    return {"fiscal_year": {"id": fy.id, "label": fy.label, "end_date": fy.end_date.isoformat()},
            "regime": regime(fy), "simulation": simulation(fy), "accessory": accessory(fy), "history": history_rows(),
            "classes": [{"value": k, "label": v} for k, v in ACCOUNT_INCOME_CLASSES.items()]}


# ------------------------------------------------------------------ contrôles de clôture

def checks(fy: FiscalYear) -> list[tuple[str, str, int, str]]:
    from app.services import tax_result
    out = []
    reg = regime(fy)
    if reg["change"] and reg["change"]["direction"] == "up":
        out.append(("ba_regime_change", f"Régime BA : {reg['change']['label']}", 1, "info"))
    acc = accessory(fy)
    if acc.get("exceeded"):
        if acc["consequence"] == "is":
            out.append(("accessory_is", "Revenus accessoires au-delà des limites de l'art. 75 : société civile soumise "
                                        "à l'IS de plein droit (art. 206-2), à examiner", 1, "anomaly"))
        else:
            out.append(("accessory_bic", "Revenus accessoires au-delà des limites de l'art. 75 : imposition en BIC / BNC",
                        1, "info"))
    if tax_result.enabled() and not IncomeSpread.query.filter_by(fiscal_year_id=fy.id).first():
        proposal = spread_proposal(fy)
        if proposal["exceptional_cents"] > 0 and not proposal["reason"]:
            out.append(("income_spread", "Bénéfice exceptionnel : étalement 75-0 A possible (option)", 1, "info"))
    return out
