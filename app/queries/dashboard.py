"""Tableau de bord : indicateurs et séries mensuelles d'un exercice (extraits de l'ancienne
vue Jinja ; les graphiques sont dessinés par la SPA)."""
from datetime import date

from sqlalchemy import extract, func

from app.extensions import db
from app.models import (
    BankTransaction, CustomerInvoice, HelloAssoItem, HelloAssoOrder, JournalEntry, JournalLine,
    Account, Order, OrderLine, Payout,
)
from app.services.reports import build_compte_resultat, section_total
from app.tenant import is_association


def _months_in_fy(fy):
    """Returns list of (year, month) tuples covered by the fiscal year."""
    months = []
    d = date(fy.start_date.year, fy.start_date.month, 1)
    while d <= fy.end_date:
        months.append((d.year, d.month))
        d = date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)
    return months


def _month_label(y, m):
    return f"{m:02d}/{y}"


def _monthly_result(fy):
    """Monthly produits (7x) and charges (6x) for the fiscal year."""
    months = _months_in_fy(fy)
    rows = (
        db.session.query(
            extract('year', JournalEntry.entry_date).label('y'),
            extract('month', JournalEntry.entry_date).label('m'),
            func.substr(Account.code, 1, 1).label('prefix'),
            func.coalesce(func.sum(JournalLine.debit_cents), 0),
            func.coalesce(func.sum(JournalLine.credit_cents), 0),
        )
        .select_from(JournalEntry)
        .join(JournalLine, JournalLine.entry_id == JournalEntry.id)
        .join(Account, Account.id == JournalLine.account_id)
        .filter(JournalEntry.fiscal_year_id == fy.id)
        .filter(func.substr(Account.code, 1, 1).in_(['6', '7']))
        .group_by('y', 'm', 'prefix')
        .all()
    )
    bucket = {(y, m): {'6': 0, '7': 0} for y, m in months}
    for y, m, prefix, debit, credit in rows:
        key = (int(y), int(m))
        if key not in bucket:
            continue
        if prefix == '6':
            bucket[key]['6'] = (debit - credit) / 100
        elif prefix == '7':
            bucket[key]['7'] = (credit - debit) / 100

    labels = [_month_label(y, m) for y, m in months]
    produits = [round(bucket[k]['7'], 2) for k in months]
    charges = [round(bucket[k]['6'], 2) for k in months]
    nets = [round(p - c, 2) for p, c in zip(produits, charges)]
    return labels, produits, charges, nets


def _monthly_sales(fy):
    """Monthly net credit on 70x accounts + POS Odoo orders + non-POS Odoo invoices."""
    months = _months_in_fy(fy)
    rows = (
        db.session.query(
            extract('year', JournalEntry.entry_date).label('y'),
            extract('month', JournalEntry.entry_date).label('m'),
            func.coalesce(
                func.sum(JournalLine.credit_cents - JournalLine.debit_cents), 0
            ),
        )
        .select_from(JournalEntry)
        .join(JournalLine, JournalLine.entry_id == JournalEntry.id)
        .join(Account, Account.id == JournalLine.account_id)
        .filter(JournalEntry.fiscal_year_id == fy.id)
        .filter(Account.code.like("70%"))
        .group_by('y', 'm')
        .all()
    )
    bucket = {(int(y), int(m)): val / 100 for y, m, val in rows}

    pos_rows = (
        db.session.query(
            extract('year', Order.date_order).label('y'),
            extract('month', Order.date_order).label('m'),
            func.coalesce(func.sum(Order.amount_total_cents), 0),
        )
        .filter(Order.date_order >= fy.start_date)
        .filter(Order.date_order <= fy.end_date)
        .filter(Order.state.in_(("paid", "done", "invoiced")))
        .group_by('y', 'm')
        .all()
    )
    pos_bucket = {(int(y), int(m)): val / 100 for y, m, val in pos_rows}

    inv_rows = (
        db.session.query(
            extract('year', CustomerInvoice.invoice_date).label('y'),
            extract('month', CustomerInvoice.invoice_date).label('m'),
            func.coalesce(func.sum(CustomerInvoice.amount_total_cents), 0),
        )
        .filter(CustomerInvoice.invoice_date >= fy.start_date)
        .filter(CustomerInvoice.invoice_date <= fy.end_date)
        .filter(CustomerInvoice.state == "posted")
        .filter(CustomerInvoice.ref == None)  # exclude POS orders which are also recorded as invoices")
        .group_by('y', 'm')
        .all()
    )
    inv_bucket = {(int(y), int(m)): val / 100 for y, m, val in inv_rows}

    labels = [_month_label(y, m) for y, m in months]
    values = [round(bucket.get(k, 0), 2) for k in months]
    pos_values = [round(pos_bucket.get(k, 0), 2) for k in months]
    inv_values = [round(inv_bucket.get(k, 0), 2) for k in months]
    return labels, values, pos_values, inv_values


def _bank_balance_evolution(fy):
    """Cumulative end-of-month bank balance across all bank accounts."""
    months = _months_in_fy(fy)
    base = db.session.query(
        func.coalesce(func.sum(BankTransaction.amount_cents), 0)
    ).filter(BankTransaction.transaction_date < fy.start_date).scalar() or 0

    rows = (
        db.session.query(
            extract('year', BankTransaction.transaction_date).label('y'),
            extract('month', BankTransaction.transaction_date).label('m'),
            func.coalesce(func.sum(BankTransaction.amount_cents), 0),
        )
        .filter(BankTransaction.transaction_date >= fy.start_date)
        .filter(BankTransaction.transaction_date <= fy.end_date)
        .group_by('y', 'm')
        .all()
    )
    delta = {(int(y), int(m)): val for y, m, val in rows}
    labels = []
    balances = []
    cumul_cents = base
    for y, m in months:
        cumul_cents += delta.get((y, m), 0)
        labels.append(_month_label(y, m))
        balances.append(round(cumul_cents / 100, 2))
    return labels, balances


# ---------------------------------------------------------------------------
# Top-line KPIs
# ---------------------------------------------------------------------------


def _total_sales_cents(fy):
    """Total sales = POS orders (paid/done/invoiced) + posted Odoo invoices."""
    pos_total = db.session.query(
        func.coalesce(func.sum(Order.amount_total_cents), 0)
    ).filter(
        Order.date_order >= fy.start_date,
        Order.date_order <= fy.end_date,
        Order.state.in_(("paid", "done", "invoiced")),
    ).scalar() or 0
    inv_total = db.session.query(
        func.coalesce(func.sum(CustomerInvoice.amount_total_cents), 0)
    ).filter(
        CustomerInvoice.invoice_date >= fy.start_date,
        CustomerInvoice.invoice_date <= fy.end_date,
        CustomerInvoice.state == "posted",
        CustomerInvoice.ref == None,
    ).scalar() or 0
    return int(pos_total) + int(inv_total)


def _new_members_count(fy):
    """Distinct entities with at least one membership event in the fiscal year.

    Membership events:
      - HelloAsso item type='Membership' on an order dated in the FY
      - POS OrderLine matching '%adh%sion%' (product name) on an order in the FY
    """
    ha_ids = {
        row[0] for row in
        db.session.query(HelloAssoOrder.entity_id)
        .join(HelloAssoItem, HelloAssoItem.order_id == HelloAssoOrder.id)
        .filter(HelloAssoItem.type == "Membership")
        .filter(HelloAssoOrder.entity_id.isnot(None))
        .filter(HelloAssoOrder.date >= fy.start_date)
        .filter(HelloAssoOrder.date <= fy.end_date)
        .distinct()
        .all()
    }
    pos_ids = {
        row[0] for row in
        db.session.query(Order.entity_id)
        .join(OrderLine, OrderLine.order_id == Order.id)
        .filter(Order.entity_id.isnot(None))
        .filter(
            db.or_(
                db.func.lower(OrderLine.full_product_name).like("%adh%sion%"),
                db.func.lower(OrderLine.product_name).like("%adh%sion%"),
            )
        )
        .filter(Order.date_order >= fy.start_date)
        .filter(Order.date_order <= fy.end_date)
        .distinct()
        .all()
    }
    return len(ha_ids | pos_ids)


def _resultat_courant_cents(fy):
    """Résultat courant avant impôts = (produits expl + produits fin) - (charges expl + charges fin).

    Aggregated from build_compte_resultat to stay aligned with the official report of the instance chart.
    """
    from app.tenant import current_chart  # import tardif : app.tenant importe l'API

    data = build_compte_resultat(fy, chart=current_chart())
    p_expl = section_total(data["produits_exploitation"])[0]
    c_expl = section_total(data["charges_exploitation"])[0]
    p_fin = section_total(data["produits_financiers"])[0]
    c_fin = section_total(data["charges_financieres"])[0]
    return int(p_expl + p_fin - c_expl - c_fin)


def _total_payouts_cents(fy):
    """Sum of Stancer payouts whose date_payout falls within the fiscal year."""
    total = db.session.query(
        func.coalesce(func.sum(Payout.amount_cents), 0)
    ).filter(
        Payout.date_bank >= fy.start_date,
        Payout.date_bank <= fy.end_date,
    ).scalar() or 0
    return int(total)


def dashboard_data(fy):
    """Indicateurs et séries mensuelles (euros) de l'exercice."""
    labels, produits, charges, nets = _monthly_result(fy)
    _, sales, pos_sales, inv_sales = _monthly_sales(fy)
    _, balances = _bank_balance_evolution(fy)
    return {
        "stats": {
            "total_sales_cents": _total_sales_cents(fy),
            "new_members": _new_members_count(fy) if is_association() else None,
            "resultat_courant_cents": _resultat_courant_cents(fy),
            "total_payouts_cents": _total_payouts_cents(fy),
        },
        "monthly": [
            {"month": label, "produits": p, "charges": c, "net": n, "ventes": v, "pos": ps,
             "factures": inv, "solde": b}
            for label, p, c, n, v, ps, inv, b in zip(labels, produits, charges, nets, sales,
                                                     pos_sales, inv_sales, balances)
        ],
    }
