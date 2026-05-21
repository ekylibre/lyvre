from datetime import date
from flask import Blueprint, render_template, request
from flask_login import login_required
from sqlalchemy import func, extract
from echarts import Echart, Bar, Line, Axis, Legend
from app.extensions import db
from app.models import (
    FiscalYear, BankTransaction, JournalEntry, JournalLine, Account,
    Order, OrderLine, CustomerInvoice, Payout, HelloAssoOrder, HelloAssoItem,
)
from app.services.reports import build_compte_resultat

bp = Blueprint("dashboard", __name__)


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

    Aggregated from build_compte_resultat to stay aligned with the official PCA report.
    """
    data = build_compte_resultat(fy)
    p_expl = sum(v[0] for v in data["produits_exploitation"].values())
    c_expl = sum(v[0] for v in data["charges_exploitation"].values())
    p_fin = sum(v[0] for v in data["produits_financiers"].values())
    c_fin = sum(v[0] for v in data["charges_financieres"].values())
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


def _build_charts(fy):
    """Returns dict of ECharts JSON options for dashboard charts."""
    res_labels, produits, charges, nets = _monthly_result(fy)
    sales_labels, sales, pos_sales, inv_sales = _monthly_sales(fy)
    bank_labels, balances = _bank_balance_evolution(fy)

    # Résultat (produits/charges/net)
    cdr = Echart("Résultat mensuel", f"Exercice {fy.label}")
    cdr.use(Bar("Produits", produits))
    cdr.use(Bar("Charges", charges))
    cdr.use(Line("Net", nets))
    cdr.use(Legend(["Produits", "Charges", "Net"]))
    cdr.use(Axis("category", "bottom", data=res_labels))
    cdr.use(Axis("value", "left"))

    # Ventes
    ventes = Echart("Ventes mensuelles")
    ventes.use(Bar("Ventes (70x)", sales))
    ventes.use(Bar("Commandes POS", pos_sales))
    ventes.use(Bar("Factures Odoo", inv_sales))
    ventes.use(Legend(["Ventes (70x)", "Commandes POS", "Factures Odoo"]))
    ventes.use(Axis("category", "bottom", data=sales_labels))
    ventes.use(Axis("value", "left"))

    # Solde bancaire
    solde = Echart("Solde bancaire", "Cumulé fin de mois")
    solde.use(Line("Solde", balances))
    solde.use(Legend(["Solde"]))
    solde.use(Axis("category", "bottom", data=bank_labels))
    solde.use(Axis("value", "left"))

    # Adapt to ECharts 5+ (xAxis/yAxis as objects, area on lines, tooltip)
    def adapt(opt, *, area_lines=False, color_series=None):
        opt = dict(opt)
        if isinstance(opt.get("xAxis"), list) and opt["xAxis"]:
            opt["xAxis"] = opt["xAxis"][0]
        if isinstance(opt.get("yAxis"), list) and opt["yAxis"]:
            opt["yAxis"] = opt["yAxis"][0]
        if not opt.get("yAxis") or opt["yAxis"] == {}:
            opt["yAxis"] = {"type": "value", "axisLabel": {"formatter": "{value} €"}}
        else:
            opt["yAxis"]["axisLabel"] = {"formatter": "{value} €"}
        opt["tooltip"] = {"trigger": "axis",
                          "valueFormatter": "FMT_EUR"}
        opt["grid"] = {"left": 60, "right": 30, "top": 70, "bottom": 40}
        opt.setdefault("legend", {})
        opt["legend"]["top"] = 28
        opt["toolbox"] = {
            "show": True,
            "right": 20,
            "top": 8,
            "feature": {
                "dataView": {"title": "Données", "readOnly": True,
                             "lang": ["Données", "Fermer", "Rafraîchir"]},
                "saveAsImage": {"title": "Exporter en image", "name": opt.get("title", {}).get("text", "chart"),
                                "type": "png", "pixelRatio": 2},
            },
        }
        for i, s in enumerate(opt.get("series", [])):
            if area_lines and s.get("type") == "line":
                s["areaStyle"] = {"opacity": 0.15}
                s["smooth"] = True
            if s.get("type") == "line":
                s["smooth"] = True
                s["symbol"] = "circle"
                s["symbolSize"] = 6
            if color_series and i < len(color_series):
                s["itemStyle"] = {"color": color_series[i]}
                s["lineStyle"] = {"color": color_series[i]}
        return opt

    return {
        "resultat": adapt(cdr.json, color_series=["#1abc9c", "#e74c3c", "#34495e"]),
        "ventes": adapt(ventes.json, color_series=["#3498db", "#f39c12", "#27ae60"]),
        "solde": adapt(solde.json, area_lines=True, color_series=["#9b59b6"]),
    }


@bp.route("/")
@login_required
def index():
    fiscal_years = FiscalYear.query.order_by(FiscalYear.start_date.desc()).all()

    fy_id = request.args.get("fy_id", type=int)
    selected_fy = None
    if fy_id:
        selected_fy = next((fy for fy in fiscal_years if fy.id == fy_id), None)
    if selected_fy is None and fiscal_years:
        selected_fy = fiscal_years[0]  # ordered desc by start_date → latest

    stats = {}
    charts = None
    if selected_fy:
        stats["total_sales_cents"] = _total_sales_cents(selected_fy)
        stats["new_members"] = _new_members_count(selected_fy)
        stats["resultat_courant_cents"] = _resultat_courant_cents(selected_fy)
        stats["total_payouts_cents"] = _total_payouts_cents(selected_fy)
        stats["recent_entries"] = (
            JournalEntry.query.filter_by(fiscal_year_id=selected_fy.id)
            .order_by(JournalEntry.entry_date.desc())
            .limit(10)
            .all()
        )
        charts = _build_charts(selected_fy)

    return render_template(
        "dashboard/index.html",
        fiscal_years=fiscal_years,
        active_fy=selected_fy,
        stats=stats,
        charts=charts,
    )
