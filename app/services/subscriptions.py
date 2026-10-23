"""Abonnements d'achat (lot S6, décision V17) : contrats récurrents et échéances attendues.

À chaque échéance (mensuelle, trimestrielle, annuelle, au jour choisi), une période « attendue »
est créée — jusqu'à aujourd'hui, une seule fois par échéance. Elle se rattache automatiquement :
- à la **facture d'achat** du fournisseur la plus proche dans la fenêtre de l'échéance (montant égal
  si l'abonnement est à montant fixe, à ±30 % s'il est estimé) ;
- au **prélèvement** bancaire de ce montant (celui de la facture s'il est connu), du même tiers ou
  dont le libellé cite le fournisseur, sur le compte prélevé s'il est indiqué.
Une échéance passée de plus de 10 jours sans facture ni prélèvement est « manquante » ; elle peut
être rattachée à la main ou ignorée. Aucune écriture : la facture réelle se comptabilise comme
toute facture d'achat.

Suivi des contrats : coût mensuel et annuel, total par catégorie, prochaine reconduction (tacite,
d'année en année) et date limite de résiliation (reconduction − préavis), signalée 45 jours avant.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.extensions import db
from app.models import BankTransaction, Entity, Product, Purchase, Subscription, SubscriptionPeriod
from app.models.subscription import CATEGORIES
from app.services import recurrence
from app.services.sale_entry import SaleError, parse_date, parse_decimal

FREQUENCIES = {"monthly": 1, "quarterly": 3, "yearly": 12}
WINDOW_DAYS = {"monthly": 20, "quarterly": 35, "yearly": 45}
GRACE_DAYS = 10
NOTICE_ALERT_DAYS = 45
TOLERANCE = 0.30


# ------------------------------------------------------------------ saisie

def _apply(sub: Subscription, data: dict) -> None:
    label = str(data.get("label", sub.label) or "").strip()[:200]
    if not label:
        raise SaleError("Désignation obligatoire.", "label")
    sub.label = label
    entity_id = data.get("entity_id", sub.entity_id)
    entity = db.session.get(Entity, int(entity_id)) if str(entity_id or "").isdigit() else None
    if entity is None:
        raise SaleError("Choisissez le fournisseur.", "entity_id")
    sub.entity = entity
    category = data.get("category", sub.category) or "other"
    if category not in CATEGORIES:
        raise SaleError("Catégorie inconnue.", "category")
    sub.category = category
    if "product_id" in data:
        product_id = data.get("product_id")
        sub.product = db.session.get(Product, int(product_id)) if str(product_id or "").isdigit() else None
    if "amount" in data or sub.amount_cents is None:
        amount = parse_decimal(data.get("amount"), "Montant", "amount", minimum=0)
        if not amount:
            raise SaleError("Montant TTC attendu obligatoire.", "amount")
        sub.amount_cents = int(amount * 100)
    if "amount_fixed" in data:
        sub.amount_fixed = bool(data.get("amount_fixed"))
    frequency = data.get("frequency", sub.frequency) or "monthly"
    if frequency not in FREQUENCIES:
        raise SaleError("Périodicité inconnue.", "frequency")
    sub.frequency = frequency
    try:
        due_day = int(data.get("due_day", sub.due_day) or 1)
    except (TypeError, ValueError):
        due_day = 0
    if not 1 <= due_day <= 28:
        raise SaleError("Jour d'échéance : de 1 à 28.", "due_day")
    sub.due_day = due_day
    if "bank_account_id" in data:
        sub.bank_account_id = int(data["bank_account_id"]) if str(data.get("bank_account_id") or "").isdigit() else None
    sub.start_date = parse_date(data.get("start_date"), "Début", "start_date") or sub.start_date or date.today()
    for key, label_ in (("end_date", "Fin"), ("renewal_date", "Reconduction")):
        if key in data:
            setattr(sub, key, parse_date(data.get(key), label_, key))
    if sub.end_date and sub.end_date < sub.start_date:
        raise SaleError("La fin précède le début.", "end_date")
    if "notice_days" in data:
        value = str(data.get("notice_days") or "").strip()
        sub.notice_days = int(value) if value.isdigit() else None
    if "notes" in data:
        sub.notes = str(data.get("notes") or "").strip() or None
    if "active" in data:
        sub.active = bool(data.get("active"))


def create(data: dict) -> Subscription:
    sub = Subscription()
    try:
        _apply(sub, data)
        db.session.add(sub)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    refresh([sub])
    return sub


def update(sub: Subscription, data: dict) -> Subscription:
    try:
        _apply(sub, data)
        # Échéances encore attendues : montant et dates recalculés ; celles rattachées restent.
        for period in list(sub.periods):
            if period.status in ("expected", "missing") and not period.purchase_id and not period.bank_transaction_id:
                db.session.delete(period)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    refresh([sub])
    return sub


# ------------------------------------------------------------------ échéances

def due_dates(sub: Subscription, until: date) -> list[date]:
    days, due = [], recurrence.first_due(sub.start_date, sub.due_day)
    end = min(until, sub.end_date) if sub.end_date else until
    while due <= end:
        days.append(due)
        due = recurrence.add_months(due, FREQUENCIES[sub.frequency], sub.due_day)
    return days


def _amount_ok(sub: Subscription, expected: int, actual: int) -> bool:
    if sub.amount_fixed:
        return actual == expected
    return abs(actual - expected) <= expected * TOLERANCE


def _match_purchase(sub: Subscription, period: SubscriptionPeriod, taken: set[int]) -> Purchase | None:
    window = timedelta(days=WINDOW_DAYS[sub.frequency])
    rows = Purchase.query.filter(Purchase.entity_id == sub.entity_id, Purchase.is_credit_note.is_(False),
                                 Purchase.is_hidden.is_(False),
                                 Purchase.issue_date.between(period.due_date - window, period.due_date + window)).all()
    rows = [p for p in rows if p.id not in taken and _amount_ok(sub, period.expected_cents, p.total_cents)]
    return min(rows, key=lambda p: (abs((p.issue_date - period.due_date).days), p.id), default=None)


def _match_debit(sub: Subscription, period: SubscriptionPeriod, taken: set[int]) -> BankTransaction | None:
    window = timedelta(days=WINDOW_DAYS[sub.frequency])
    amount = period.purchase.total_cents if period.purchase else None
    query = BankTransaction.query.filter(BankTransaction.amount_cents < 0, BankTransaction.is_reversed.is_(False),
                                         BankTransaction.transaction_date.between(period.due_date - window,
                                                                                  period.due_date + window))
    if sub.bank_account_id:
        query = query.filter(BankTransaction.bank_account_id == sub.bank_account_id)
    name = (sub.entity.name or "").split()[0].upper() if sub.entity.name else ""
    rows = []
    for txn in query.all():
        if txn.id in taken:
            continue
        ok_amount = (-txn.amount_cents == amount) if amount is not None else _amount_ok(sub, period.expected_cents, -txn.amount_cents)
        same_party = txn.entity_id == sub.entity_id or (len(name) >= 3 and name in (txn.label or "").upper())
        if ok_amount and same_party:
            rows.append(txn)
    return min(rows, key=lambda t: (abs((t.transaction_date - period.due_date).days), t.id), default=None)


def _status(period: SubscriptionPeriod, today: date) -> str:
    if period.status == "skipped":
        return "skipped"
    # Relations (et non identifiants) : un lien posé dans la session n'est pas encore écrit.
    if period.bank_transaction is not None or (period.purchase is not None and period.purchase.payments):
        return "paid"
    if period.purchase is not None:
        return "invoiced"
    return "missing" if period.due_date + timedelta(days=GRACE_DAYS) < today else "expected"


def refresh(subs=None, today: date | None = None) -> dict:
    """Crée les échéances arrivées et rattache factures et prélèvements ; idempotent."""
    today = today or date.today()
    subs = subs if subs is not None else Subscription.query.filter_by(active=True).all()
    taken_purchases = {p for (p,) in db.session.query(SubscriptionPeriod.purchase_id).filter(SubscriptionPeriod.purchase_id.isnot(None))}
    taken_debits = {t for (t,) in db.session.query(SubscriptionPeriod.bank_transaction_id)
                    .filter(SubscriptionPeriod.bank_transaction_id.isnot(None))}
    created = linked = 0
    for sub in subs:
        known = {p.due_date for p in sub.periods}
        for due in due_dates(sub, today):
            if due not in known:
                sub.periods.append(SubscriptionPeriod(due_date=due, expected_cents=sub.amount_cents))
                created += 1
        db.session.flush()
        for period in sub.periods:
            if period.status == "skipped":
                continue
            if period.purchase_id is None:
                purchase = _match_purchase(sub, period, taken_purchases)
                if purchase is not None:
                    period.purchase = purchase
                    taken_purchases.add(purchase.id)
                    linked += 1
            if period.bank_transaction_id is None:
                txn = _match_debit(sub, period, taken_debits)
                if txn is not None:
                    period.bank_transaction = txn
                    taken_debits.add(txn.id)
                    linked += 1
            period.status = _status(period, today)
    db.session.commit()
    return {"created": created, "linked": linked}


def link(period: SubscriptionPeriod, purchase_id=None, bank_transaction_id=None) -> SubscriptionPeriod:
    if purchase_id is not None:
        purchase = db.session.get(Purchase, purchase_id)
        if purchase is None:
            raise SaleError("Facture introuvable.", "purchase_id")
        if SubscriptionPeriod.query.filter(SubscriptionPeriod.purchase_id == purchase.id, SubscriptionPeriod.id != period.id).first():
            raise SaleError("Facture déjà rattachée à une autre échéance.", status=409)
        period.purchase = purchase
    if bank_transaction_id is not None:
        txn = db.session.get(BankTransaction, bank_transaction_id)
        if txn is None:
            raise SaleError("Transaction introuvable.", "bank_transaction_id")
        if SubscriptionPeriod.query.filter(SubscriptionPeriod.bank_transaction_id == txn.id, SubscriptionPeriod.id != period.id).first():
            raise SaleError("Prélèvement déjà rattaché à une autre échéance.", status=409)
        period.bank_transaction = txn
    if period.status == "skipped":
        period.status = "expected"
    db.session.flush()
    period.status = _status(period, date.today())
    db.session.commit()
    return period


def skip(period: SubscriptionPeriod, skipped: bool = True) -> SubscriptionPeriod:
    period.status = "skipped" if skipped else "expected"
    if not skipped:
        period.status = _status(period, date.today())
    db.session.commit()
    return period


def candidates(period: SubscriptionPeriod) -> dict:
    """Factures du fournisseur et débits proches, pour un rattachement à la main."""
    sub = period.subscription
    window = timedelta(days=WINDOW_DAYS[sub.frequency] * 2)
    purchases = Purchase.query.filter(Purchase.entity_id == sub.entity_id, Purchase.is_credit_note.is_(False),
                                      Purchase.issue_date.between(period.due_date - window, period.due_date + window)
                                      ).order_by(Purchase.issue_date).all()
    debits = BankTransaction.query.filter(BankTransaction.amount_cents < 0,
                                          BankTransaction.transaction_date.between(period.due_date - window, period.due_date + window)
                                          ).order_by(BankTransaction.transaction_date).limit(200).all()
    near = sorted(debits, key=lambda t: (abs(-t.amount_cents - period.expected_cents), t.transaction_date))[:20]
    return {"purchases": purchases, "debits": near}


# ------------------------------------------------------------------ suivi

def monthly_cents(sub: Subscription) -> int:
    return round(sub.amount_cents / FREQUENCIES[sub.frequency])


def next_renewal(sub: Subscription, today: date | None = None) -> date | None:
    """Prochaine reconduction tacite (d'année en année à partir de la date saisie)."""
    if sub.renewal_date is None:
        return None
    today = today or date.today()
    renewal = sub.renewal_date
    while renewal < today:
        renewal = recurrence.add_months(renewal, 12, renewal.day if renewal.day <= 28 else 28)
    return renewal


def notice_deadline(sub: Subscription, today: date | None = None) -> date | None:
    renewal = next_renewal(sub, today)
    if renewal is None or sub.notice_days is None:
        return None
    return renewal - timedelta(days=sub.notice_days)


def notice_alert(sub: Subscription, today: date | None = None) -> bool:
    today = today or date.today()
    deadline = notice_deadline(sub, today)
    return bool(sub.active and deadline and today <= deadline <= today + timedelta(days=NOTICE_ALERT_DAYS))


def summary(subs) -> dict:
    active = [s for s in subs if s.active]
    by_category: dict[str, int] = {}
    for sub in active:
        by_category[sub.category] = by_category.get(sub.category, 0) + monthly_cents(sub)
    missing = SubscriptionPeriod.query.filter_by(status="missing").count()
    return {"monthly_cents": sum(monthly_cents(s) for s in active), "yearly_cents": sum(monthly_cents(s) for s in active) * 12,
            "by_category": [{"category": c, "label": CATEGORIES[c], "monthly_cents": v}
                            for c, v in sorted(by_category.items(), key=lambda kv: -kv[1])],
            "missing": missing, "notice_alerts": sum(1 for s in active if notice_alert(s))}
