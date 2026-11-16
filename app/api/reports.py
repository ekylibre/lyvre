"""États financiers (balance, grand livre, bilan, compte de résultat) et tableau de bord.
Les exports CSV / ODS du compte de résultat restent des fichiers servis par Flask."""
from flask import jsonify, request, url_for

from app.models import Account, FiscalYear
from app.queries.dashboard import dashboard_data
from app.services.ledger import general_ledger, trial_balance
from app.services import agri_reports
from app.services.reports import bilan_layout_key, build_bilan, build_compte_resultat, compte_resultat_rows

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


# Page d'accueil des éditions comptables (lot NV3, claudedocs/design_navigation.md § 4) : une carte par état.
EDITIONS = [
    ("balance", "Balance", "scale", "reports.balance",
     "Mouvements et soldes de chaque compte sur l'exercice."),
    ("grand_livre", "Grand livre", "book-text", "reports.grand_livre",
     "Détail des écritures d'un compte, avec le solde progressif."),
    ("bilan", "Bilan", "landmark", "reports.bilan",
     "Actif et passif à la clôture, comparés à l'exercice précédent."),
    ("compte_resultat", "Compte de résultat", "chart-line", "reports.compte_resultat",
     "Produits et charges de l'exercice, jusqu'au résultat net."),
    ("sig", "Soldes intermédiaires de gestion", "chart-no-axes-column", "reports.sig",
     "Marge, valeur ajoutée, excédent brut d'exploitation et résultats successifs."),
]


@bp.route("/reports/")
def report_index():
    years = _fiscal_years()
    fy = _selected(years)
    chart = current_chart()
    items = []
    for key, title, icon, endpoint, summary in EDITIONS:
        exports = []
        if fy and key == "compte_resultat":
            exports = [{"label": "CSV", "url": url_for("reports.compte_resultat_csv", fy_id=fy.id)},
                       {"label": "ODS", "url": url_for("reports.compte_resultat_ods", fy_id=fy.id)}]
        if fy and chart == "agri" and key in ("bilan", "compte_resultat", "sig"):
            exports.append({"label": "Classeur des états agricoles",
                            "url": url_for("exports.agri_statements_xlsx", fy_id=fy.id)})
        items.append({"key": key, "title": title, "icon": icon, "summary": summary,
                      "url": url_for(endpoint), "exports": exports})
    return jsonify(items=items, meta=_meta(years, fy, _previous(fy)))


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
    layout = bilan_layout_key(current_chart())
    data = build_bilan(fy, prev, layout) if fy else {"actif": [], "passif": []}
    return jsonify(actif=data["actif"], passif=data["passif"], meta={**_meta(years, fy, prev), "layout": layout})


def _agri_only():
    if current_chart() != "agri":
        raise ApiError("not_found", "État réservé aux exploitations agricoles.", 404)


@bp.route("/reports/sig")
def report_sig():
    """Soldes intermédiaires de gestion (lot AG1.c ; tous les référentiels depuis le lot NV3, Q5)."""
    from app.services import sig

    chart = current_chart()
    years = _fiscal_years()
    fy = _selected(years)
    prev = _previous(fy)
    rows = sig.compute(fy, prev, chart) if fy else []
    export = url_for("exports.agri_statements_xlsx", fy_id=fy.id) if fy and chart == "agri" else None
    return jsonify(items=rows, meta={**_meta(years, fy, prev), "export_url": export,
                                     "method": None if chart == "agri" else sig.METHOD})


@bp.route("/reports/living-assets")
def report_living_assets():
    """Tableau des biens vivants et en-cours (annexe, art. 121-4 du titre 5)."""
    _agri_only()
    years = _fiscal_years()
    fy = _selected(years)
    prev = _previous(fy)
    data = agri_reports.living_assets_table(fy, prev) if fy else {"groups": [], "total": {"opening": 0, "closing": 0}}
    return jsonify(item=data, meta=_meta(years, fy, prev))


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
        return jsonify(stats=None, monthly=[], meta=_meta(years, None))
    data = dashboard_data(fy)
    from app.services import agent_review, sale_settlement, validation
    return jsonify(
        stats=data["stats"], monthly=data["monthly"],
        # Ventes : CA facturé de l'exercice, encours clients, échues (tuiles seulement s'il y a des factures).
        sales=sale_settlement.receivables_summary(fy.start_date, fy.end_date),
        # Écritures en brouillard des exercices ouverts (rappel au-delà de 3 mois, lot F1).
        drafts=validation.draft_counts(),
        # Saisies par clé d'API à vérifier (lot AK3).
        agent=agent_review.counts(),
        meta=_meta(years, fy),
    )
