"""États financiers (balance, grand livre, bilan, compte de résultat) et tableau de bord.
Les exports CSV / ODS du compte de résultat restent des fichiers servis par Flask."""
from flask import jsonify, request, url_for

from app.models import Account, FiscalYear
from app.queries.dashboard import dashboard_data
from app.services.ledger import general_ledger, trial_balance
from app.services.reports import build_bilan, build_compte_resultat, compte_resultat_rows

from . import ApiError, bp


def current_chart():
    from app.tenant import current_chart as chart  # import tardif : app.tenant importe l'API

    return chart()


def _fiscal_years():
    return FiscalYear.query.order_by(FiscalYear.start_date.desc()).all()


def _selected(years, default_open=True):
    """Exercice demandé (`fy_id`), sinon le plus récent ouvert (ou le plus récent)."""
    fy_id = request.args.get("fy_id", type=int)
    if fy_id:
        fy = next((f for f in years if f.id == fy_id), None)
        if fy is None:
            raise ApiError("not_found", "Exercice introuvable.", 404)
        return fy
    if default_open:
        return next((f for f in years if not f.closed), None)
    return years[0] if years else None


def _previous(fy):
    if fy is None:
        return None
    return (FiscalYear.query.filter(FiscalYear.start_date < fy.start_date)
            .order_by(FiscalYear.start_date.desc()).first())


def _fy(fy):
    return {"id": fy.id, "label": fy.label, "start_date": fy.start_date.isoformat(),
            "end_date": fy.end_date.isoformat()} if fy else None


def _meta(years, fy, prev=None):
    return {"fiscal_years": [{"value": str(f.id), "label": f.label} for f in years],
            "fiscal_year": _fy(fy), "previous": _fy(prev)}


@bp.route("/reports/balance")
def report_balance():
    years = _fiscal_years()
    fy = _selected(years)
    rows, _ = trial_balance(fy.id) if fy else ([], None)
    return jsonify(items=[{
        "account_id": r["account"].id, "code": r["account"].code, "label": r["account"].label,
        "debit_cents": r["debit_cents"], "credit_cents": r["credit_cents"],
        "balance_debit_cents": r["balance_debit"], "balance_credit_cents": r["balance_credit"],
    } for r in rows], meta=_meta(years, fy))


@bp.route("/reports/grand-livre")
def report_general_ledger():
    years = _fiscal_years()
    fy = _selected(years)
    account_id = request.args.get("account_id", type=int)
    account, rows = general_ledger(account_id, fy.id) if account_id and fy else (None, [])
    return jsonify(
        account={"id": account.id, "code": account.code, "label": account.label} if account else None,
        items=[{"entry_id": r["entry"].id, "url": url_for("entries.detail", entry_id=r["entry"].id),
                "date": r["entry"].entry_date.isoformat(), "reference": r["entry"].reference,
                "journal": r["entry"].journal.code, "label": r["line"].label or r["entry"].description,
                "debit_cents": r["line"].debit_cents, "credit_cents": r["line"].credit_cents,
                "running_cents": r["running_cents"]} for r in rows],
        meta={**_meta(years, fy), "accounts": [
            {"value": str(a.id), "label": f"{a.code} — {a.label}"}
            for a in Account.query.filter_by(is_header=False).order_by(Account.code)]},
    )


@bp.route("/reports/bilan")
def report_bilan():
    years = _fiscal_years()
    fy = _selected(years)
    prev = _previous(fy)
    data = build_bilan(fy, prev, current_chart()) if fy else {"actif": [], "passif": []}
    return jsonify(actif=data["actif"], passif=data["passif"], meta=_meta(years, fy, prev))


@bp.route("/reports/compte-de-resultat")
def report_compte_resultat():
    years = _fiscal_years()
    fy = _selected(years)
    prev = _previous(fy)
    chart = current_chart()
    rows = []
    if fy:
        for kind, label, n, p in compte_resultat_rows(build_compte_resultat(fy, prev, chart), chart):
            indent = (len(label) - len(label.lstrip())) // 2
            rows.append({"kind": kind, "label": label.strip(), "indent": indent, "n": n, "p": p})
    exports = ({"csv": url_for("reports.compte_resultat_csv", fy_id=fy.id),
                "ods": url_for("reports.compte_resultat_ods", fy_id=fy.id)} if fy else None)
    return jsonify(items=rows, meta={**_meta(years, fy, prev), "export_urls": exports})


@bp.route("/dashboard")
def dashboard():
    """Indicateurs et séries de l'exercice demandé (le plus récent par défaut)."""
    years = _fiscal_years()
    fy = _selected(years, default_open=False)
    if fy is None:
        return jsonify(stats=None, monthly=[], recent_entries=[], meta=_meta(years, None))
    data = dashboard_data(fy)
    from app.services import sale_settlement
    return jsonify(
        stats=data["stats"], monthly=data["monthly"],
        # Ventes : CA facturé de l'exercice, encours clients, échues (tuiles seulement s'il y a des factures).
        sales=sale_settlement.receivables_summary(fy.start_date, fy.end_date),
        recent_entries=[{"id": e.id, "url": url_for("entries.detail", entry_id=e.id),
                         "reference": e.reference, "date": e.entry_date.isoformat(),
                         "description": e.description or "", "total_cents": e.total_debit}
                        for e in data["recent_entries"]],
        meta=_meta(years, fy),
    )
