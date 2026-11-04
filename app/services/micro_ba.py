"""Micro-BA d'une exploitation tenue en comptabilité simplifiée (lot AG1.d, claudedocs/design_compta_agricole.md
§ 6.1) : livre des recettes et récapitulatif des recettes de N, N-1 et N-2 avec le bénéfice forfaitaire.

- **Livre des recettes** (CGI art. 64 bis IV) : une ligne par encaissement de l'année civile (comptes de classe 7
  des recettes saisies ou catégorisées), les ventes au détail d'au plus ``ba.micro.receipts_book.grouping_cents``
  regroupées par jour sur option ; totaux par trimestre et pour l'année ; recettes exclues du micro-BA repérées
  par leur catégorie (``SimpleCategory.excluded_from_micro``).
- **Récapitulatif** : recettes retenues de l'année et des deux précédentes (écritures de Lyvre, ou saisie des années
  antérieures, ``MicroReceiptsYear``, qui l'emporte), moyenne, abattement et minimum (paramètres réglementaires
  datés), comparaison au seuil du micro-BA. Les montants sont ceux des encaissements : une exploitation au micro-BA
  relève en général du remboursement forfaitaire (pas de TVA).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from app.extensions import db
from app.models import Account, Entity, JournalEntry, JournalLine, MicroReceiptsYear, SimpleCategory
from app.services import reg_params


class MicroError(Exception):
    def __init__(self, message, field=None, status=422):
        super().__init__(message)
        self.message, self.field, self.status = message, field, status


def _quarter(day: date) -> int:
    return (day.month - 1) // 3 + 1


def _receipt_lines(year: int):
    """(date, montant, compte, catégorie, tiers, libellé) des recettes de l'année civile (crédit − débit des
    comptes de produits ; une écriture d'annulation vient en déduction)."""
    categories = {c.account_id: c for c in SimpleCategory.query.filter_by(kind="income")}
    rows = (db.session.query(JournalEntry.entry_date, JournalLine.credit_cents - JournalLine.debit_cents, Account,
                             JournalLine.label, JournalEntry.description, JournalLine.entity_id)
            .join(JournalLine, JournalLine.entry_id == JournalEntry.id)
            .join(Account, Account.id == JournalLine.account_id)
            .filter(Account.code.like("7%"), JournalEntry.entry_date.between(date(year, 1, 1), date(year, 12, 31)))
            .order_by(JournalEntry.entry_date, JournalEntry.id).all())
    entity_ids = {row[5] for row in rows if row[5]}
    names = {e.id: e.name for e in Entity.query.filter(Entity.id.in_(entity_ids))} if entity_ids else {}
    for day, amount, account, line_label, description, line_entity in rows:
        category = categories.get(account.id)
        yield {"date": day, "amount_cents": amount, "account": account.code,
               "category": category.label if category else account.label,
               "excluded": bool(category and category.excluded_from_micro),
               "entity": names.get(line_entity), "label": line_label or description or ""}


def receipts_book(year: int, group_small: bool = True) -> dict:
    threshold = reg_params.value("ba.micro.receipts_book.grouping_cents", date(year, 12, 31), default=None)
    items = list(_receipt_lines(year))
    if group_small and threshold:
        kept, grouped = [], defaultdict(lambda: {"amount_cents": 0, "count": 0})
        for item in items:
            if 0 < item["amount_cents"] <= threshold and not item["excluded"]:
                bucket = grouped[(item["date"], item["category"])]
                bucket["amount_cents"] += item["amount_cents"]
                bucket["count"] += 1
            else:
                kept.append(item)
        for (day, category), bucket in grouped.items():
            kept.append({"date": day, "amount_cents": bucket["amount_cents"], "account": None, "category": category,
                         "excluded": False, "entity": None, "grouped": bucket["count"],
                         "label": f"Ventes au détail du jour ({bucket['count']})"})
        items = sorted(kept, key=lambda i: (i["date"], i["label"]))
    quarters = {q: {"retained_cents": 0, "excluded_cents": 0} for q in (1, 2, 3, 4)}
    for item in items:
        quarters[_quarter(item["date"])]["excluded_cents" if item["excluded"] else "retained_cents"] += item["amount_cents"]
    retained = sum(q["retained_cents"] for q in quarters.values())
    excluded = sum(q["excluded_cents"] for q in quarters.values())
    return {"year": year, "grouping_cents": threshold if group_small else None,
            "items": [{**i, "date": i["date"].isoformat()} for i in items],
            "quarters": [{"quarter": q, **v} for q, v in quarters.items()],
            "total": {"retained_cents": retained, "excluded_cents": excluded, "receipts_cents": retained + excluded}}


def _lyvre_has_year(year: int) -> bool:
    return db.session.query(JournalEntry.query.filter(
        JournalEntry.entry_date.between(date(year, 1, 1), date(year, 12, 31))).exists()).scalar()


def retained_receipts(year: int) -> dict:
    """Recettes retenues d'une année : saisie des années antérieures, sinon écritures de Lyvre, sinon inconnues."""
    saved = MicroReceiptsYear.query.filter_by(year=year).first()
    if saved is not None:
        return {"year": year, "receipts_cents": saved.receipts_cents, "source": "entered", "note": saved.note}
    if _lyvre_has_year(year):
        return {"year": year, "receipts_cents": receipts_book(year, group_small=False)["total"]["retained_cents"],
                "source": "lyvre", "note": None}
    return {"year": year, "receipts_cents": None, "source": "missing", "note": None}


def _param(key, on):
    param = reg_params.get(key, on, default=None)
    return (param.value, param.reliability) if param else (None, None)


def summary(year: int) -> dict:
    """Récapitulatif du micro-BA de l'année (déclaration 2042 C PRO : recettes de N, N-1 et N-2)."""
    on = date(year, 12, 31)
    years = [retained_receipts(y) for y in (year, year - 1, year - 2)]
    known = [y["receipts_cents"] for y in years if y["receipts_cents"] is not None]
    allowance, allowance_rel = _param("ba.micro.allowance_bp", on)
    minimum, minimum_rel = _param("ba.micro.minimum_cents", on)
    threshold, threshold_rel = _param("ba.micro.threshold_cents", on)
    average = round(sum(known) / len(known)) if known else None
    profit = None
    if average is not None and allowance is not None:
        profit = max(round(average * (10000 - allowance) / 10000), minimum or 0)
    warnings = []
    if any(y["receipts_cents"] is None for y in years):
        warnings.append("Recettes d'une année antérieure inconnues : saisissez-les pour la moyenne triennale.")
    if average is not None and threshold is not None and average > threshold:
        warnings.append("Moyenne triennale au-dessus du seuil du micro-BA : passage au réel à compter de l'année "
                        "suivante (CGI art. 69).")
    if "I" in (allowance_rel, threshold_rel, minimum_rel):
        warnings.append("Un paramètre réglementaire utilisé est à valider (Administration › Paramètres réglementaires).")
    return {"year": year, "years": years, "average_cents": average, "allowance_bp": allowance,
            "minimum_cents": minimum, "profit_cents": profit, "threshold_cents": threshold,
            "reliability": {"allowance": allowance_rel, "minimum": minimum_rel, "threshold": threshold_rel},
            "warnings": warnings}


def save_carryover(year, receipts_cents, note=None) -> MicroReceiptsYear | None:
    """Recettes retenues d'une année antérieure ; montant vide : saisie retirée (retour au calcul de Lyvre)."""
    if not isinstance(year, int) or not 1990 <= year <= date.today().year:
        raise MicroError("Année invalide.", "year")
    row = MicroReceiptsYear.query.filter_by(year=year).first()
    if receipts_cents in (None, ""):
        if row is not None:
            db.session.delete(row)
            db.session.commit()
        return None
    if not isinstance(receipts_cents, int) or isinstance(receipts_cents, bool) or receipts_cents < 0:
        raise MicroError("Montant en centimes, positif ou nul.", "receipts_cents")
    if row is None:
        row = MicroReceiptsYear(year=year, receipts_cents=receipts_cents)
        db.session.add(row)
    row.receipts_cents, row.note = receipts_cents, (str(note or "").strip()[:300] or None)
    db.session.commit()
    return row
