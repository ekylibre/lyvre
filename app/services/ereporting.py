"""E-reporting B2C (lot AG10.e, claudedocs/design_efacturation_agricole.md § 6, AGD27, Q-E4).

Ventes à des particuliers **sans facture** (vente directe, marchés, paniers), agrégées par jour, catégorie et taux,
dans la forme de `POST /v1.beta/b2c_transactions` de SUPER PDP (référence OpenAPI 1.39.0.beta, schémas
`b2c_transaction` et `b2c_transaction_subtotal`) :

    {"data": [{"date", "category_code", "currency", "role_code", "tax_exclusive_amount", "tax_total",
               "tax_subtotals": [{"tax_percent", "taxable_amount", "tax_total"}]}]}

Sources : lignes au crédit d'un compte 7 dans une écriture qui touche la trésorerie (5…),
- compte d'une catégorie de recette marquée « vente directe » (`simple_categories.direct_sale`) ;
- ou tout compte 70 d'une écriture du journal de caisse (CA).
Les ventes facturées (journal des ventes, décomptes) en sont exclues : une facture à un particulier part comme
facture, avec la note BAR = B2C, et la plateforme en tire l'e-reporting (pas de double envoi).

Catégorie : `TPS1` (prestations de services) pour un compte 706, `TLB1` (livraisons de biens) sinon. Taux : code de
TVA de la ligne, sinon celui de la TVA collectée de l'écriture s'il est unique, sinon 0. TVA d'un agrégat : base ×
taux, arrondie. Lyvre prépare et exporte ; il ne transmet pas (Q-E1) et ne recalcule pas le calendrier de la PA.
Les paiements (`b2c_payments`) ne concernent que les prestations de services hors option pour les débits : non
produits ici.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from app.extensions import db
from app.models import EreportingExport, Journal, JournalEntry, JournalLine, SimpleCategory
from app.models.journal_entry import SOURCE_COOP_STATEMENT, SOURCE_SALE
from app.services import vat_codes

GOODS, SERVICES = "TLB1", "TPS1"
CATEGORY_LABELS = {GOODS: "Livraisons de biens", SERVICES: "Prestations de services"}
EXCLUDED_SOURCES = (SOURCE_SALE, SOURCE_COOP_STATEMENT)
CASH_JOURNAL = "CA"


class EreportingError(ValueError):
    def __init__(self, message, field=None, status=422):
        super().__init__(message)
        self.message, self.field, self.status = message, field, status


def _rate_of(code: str | None) -> int | None:
    spec = vat_codes.codes().get(code or "")
    return spec["rate_bp"] if spec and spec.get("side") == "sale" and spec.get("on") == "tax" else None


def direct_accounts() -> set[int]:
    return {c.account_id for c in SimpleCategory.query.filter_by(kind="income", direct_sale=True)}


def lines(start: date, end: date) -> tuple[list[dict], list[str]]:
    """Lignes de vente directe de la période : {date, account, category, rate_bp, base_cents, entry}."""
    accounts = direct_accounts()
    cash = Journal.query.filter_by(code=CASH_JOURNAL).first()
    entries = (JournalEntry.query.filter(JournalEntry.entry_date.between(start, end),
                                         db.or_(JournalEntry.source.is_(None), JournalEntry.source.notin_(EXCLUDED_SOURCES)))
               .order_by(JournalEntry.entry_date, JournalEntry.id))
    out, untaxed = [], 0
    for entry in entries:
        codes = [l.account.code for l in entry.lines]
        if not any(c.startswith("5") for c in codes):
            continue
        in_cash = cash is not None and entry.journal_id == cash.id
        vat_rates = {_rate_of(l.vat_code) for l in entry.lines if l.account.code.startswith("4457") and l.vat_code}
        vat_rates.discard(None)
        for line in entry.lines:
            code = line.account.code
            if not code.startswith("7") or not line.credit_cents and not line.debit_cents:
                continue
            if line.account_id not in accounts and not (in_cash and code.startswith("70")):
                continue
            rate = _rate_of(line.vat_code)
            if rate is None:
                rate = next(iter(vat_rates)) if len(vat_rates) == 1 else 0
                if not rate and entry.fiscal_year.vat_liable:
                    untaxed += 1
            out.append({"date": entry.entry_date, "account": code, "category": SERVICES if code.startswith("706") else GOODS,
                        "rate_bp": rate, "base_cents": line.credit_cents - line.debit_cents,
                        "entry": {"id": entry.id, "reference": entry.reference}, "label": line.label or entry.description})
    warnings = []
    if untaxed:
        warnings.append(f"{untaxed} vente(s) sans taux de TVA dans un exercice soumis à la TVA : comptées à 0 %.")
    if not accounts and cash is None:
        warnings.append("Aucune catégorie de recette marquée « vente directe » et pas de journal de caisse : rien à déclarer.")
    return out, warnings


def _tax(base: int, rate_bp: int) -> int:
    return int((Decimal(base) * rate_bp / 10000).quantize(Decimal("1")))


def aggregate(start: date, end: date) -> dict:
    found, warnings = lines(start, end)
    groups: dict[tuple, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for row in found:
        groups[(row["date"], row["category"])][row["rate_bp"]] += row["base_cents"]
    days = []
    for (day, category), rates in sorted(groups.items()):
        subtotals = [{"rate_bp": rate, "base_cents": base, "tax_cents": _tax(base, rate)}
                     for rate, base in sorted(rates.items()) if base]
        if not subtotals:
            continue
        days.append({"date": day.isoformat(), "category": category, "category_label": CATEGORY_LABELS[category],
                     "base_cents": sum(s["base_cents"] for s in subtotals),
                     "tax_cents": sum(s["tax_cents"] for s in subtotals), "subtotals": subtotals,
                     "exported": exported(day)})
    if any(d["base_cents"] < 0 for d in days):
        warnings.append("Un jour a un total négatif (remboursements supérieurs aux ventes) : à vérifier avant l'export.")
    return {"start": start.isoformat(), "end": end.isoformat(), "days": days, "lines": [
        {**r, "date": r["date"].isoformat()} for r in found],
        "base_cents": sum(d["base_cents"] for d in days), "tax_cents": sum(d["tax_cents"] for d in days),
        "pending_days": sorted({d["date"] for d in days if not d["exported"]}), "warnings": warnings}


def _decimal(cents: int) -> str:
    return str((Decimal(cents) / 100).quantize(Decimal("0.01")))


def payload(start: date, end: date) -> dict:
    """Corps de `POST /v1.beta/b2c_transactions` (SUPER PDP) pour la période."""
    return {"data": [{"date": d["date"], "category_code": d["category"], "currency": "EUR", "role_code": "SE",
                      "tax_exclusive_amount": _decimal(d["base_cents"]), "tax_total": _decimal(d["tax_cents"]),
                      "tax_subtotals": [{"tax_percent": str((Decimal(s["rate_bp"]) / 100).quantize(Decimal("0.01"))),
                                         "taxable_amount": _decimal(s["base_cents"]), "tax_total": _decimal(s["tax_cents"])}
                                        for s in d["subtotals"]]}
                     for d in aggregate(start, end)["days"]]}


def exported(day: date) -> bool:
    return EreportingExport.query.filter(EreportingExport.start_date <= day, EreportingExport.end_date >= day).first() is not None


def record_export(start: date, end: date, user_id: int | None = None) -> tuple[dict, EreportingExport]:
    if end < start:
        raise EreportingError("Période invalide.", "end")
    body = payload(start, end)
    if not body["data"]:
        raise EreportingError("Aucune vente directe sur la période : rien à exporter.", status=409)
    row = EreportingExport(start_date=start, end_date=end, transactions=len(body["data"]),
                           base_cents=sum(int(Decimal(t["tax_exclusive_amount"]) * 100) for t in body["data"]),
                           tax_cents=sum(int(Decimal(t["tax_total"]) * 100) for t in body["data"]), user_id=user_id)
    db.session.add(row)
    db.session.commit()
    return body, row


def set_categories(ids: list[int]) -> None:
    for category in SimpleCategory.query.filter_by(kind="income"):
        category.direct_sale = category.id in ids
    db.session.commit()


def months_pending(start: date, end: date) -> list[date]:
    """Fin de chaque mois de la fenêtre qui a des jours de vente directe non exportés (rappel de l'échéancier)."""
    out, day = [], date(start.year, start.month, 1)
    while day <= end:
        last = (day.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        if start <= last <= end and aggregate(day, last)["pending_days"]:
            out.append(last)
        day = last + timedelta(days=1)
    return out


def agenda_occurrences(start: date, end: date) -> list[dict]:
    """Règle `lyvre` de source `ereporting_pending` : export à faire, en fin de mois, s'il reste des jours non exportés.
    Pas de date réglementaire : la plateforme tient le calendrier selon le régime de TVA."""
    return [{"date": last, "period": f"ventes directes de {last:%m/%Y}", "lyvre_status": None,
             "link": f"/ereporting/?start={last.replace(day=1).isoformat()}&end={last.isoformat()}"}
            for last in months_pending(start, end)]
