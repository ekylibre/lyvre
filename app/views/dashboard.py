from datetime import date
from flask import Blueprint, render_template, request
from flask_login import login_required
from sqlalchemy import func, extract
from echarts import Echart, Bar, Line, Axis, Legend
from app.extensions import db
from app.models import (
    FiscalYear, BankTransaction, JournalEntry, JournalLine, Account, Order,
)

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
    """Monthly net credit on 70x accounts (ventes) + monthly POS Odoo orders total."""
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

    labels = [_month_label(y, m) for y, m in months]
    values = [round(bucket.get(k, 0), 2) for k in months]
    pos_values = [round(pos_bucket.get(k, 0), 2) for k in months]
    return labels, values, pos_values


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


def _build_charts(fy):
    """Returns dict of ECharts JSON options for dashboard charts."""
    res_labels, produits, charges, nets = _monthly_result(fy)
    sales_labels, sales, pos_sales = _monthly_sales(fy)
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
    ventes = Echart("Ventes mensuelles", "Comptabilité 70x vs commandes POS Odoo")
    ventes.use(Bar("Ventes (70x)", sales))
    ventes.use(Bar("Commandes POS", pos_sales))
    ventes.use(Legend(["Ventes (70x)", "Commandes POS"]))
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
        "ventes": adapt(ventes.json, color_series=["#3498db", "#f39c12"]),
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
        stats["entries_count"] = JournalEntry.query.filter_by(fiscal_year_id=selected_fy.id).count()
        stats["unreconciled"] = (
            BankTransaction.query
            .filter_by(reconciled=False)
            .filter(BankTransaction.transaction_date >= selected_fy.start_date)
            .filter(BankTransaction.transaction_date <= selected_fy.end_date)
            .count()
        )
        stats["unbalanced"] = JournalEntry.query.filter_by(
            fiscal_year_id=selected_fy.id, is_balanced=False
        ).count()
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
