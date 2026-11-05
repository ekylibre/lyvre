"""Exports tableur du lot C.3 (tous les rôles) : suivi budgétaire et compte de résultat d'un
projet. Écrans : SPA (Compta › Budget › Suivi, fiche projet) ; données : app/api/budgets.py,
app/api/projects.py."""
from datetime import date
from io import BytesIO

from flask import Blueprint, Response, abort, render_template, request
from flask_login import login_required
from openpyxl import Workbook
from openpyxl.styles import Font

from app.extensions import db
from app.models import FiscalYear, Project
from app.services import budget, projects

bp = Blueprint("exports", __name__)

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
EURO = '#,##0.00 "€";-#,##0.00 "€"'


def _date(value):
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        abort(400)


def _sheet(wb, title, header, rows, money_cols):
    ws = wb.create_sheet(title[:31])
    ws.append(header)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append(row)
    for col in money_cols:
        for cell in ws.iter_cols(min_col=col, max_col=col, min_row=2):
            for c in cell:
                c.number_format = EURO
    for column in ws.columns:
        ws.column_dimensions[column[0].column_letter].width = max(12, min(48, max(len(str(c.value or "")) for c in column) + 2))
    return ws


def _response(wb, filename):
    buf = BytesIO()
    wb.save(buf)
    response = Response(buf.getvalue(), mimetype=XLSX)
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@bp.route("/budget/tracking.xlsx")
@login_required
def budget_tracking_xlsx():
    fy = db.session.get(FiscalYear, request.args.get("fiscal_year_id", type=int) or 0) or abort(404)
    try:
        project = budget.project_or_error(request.args.get("project_id"))
    except budget.BudgetError:
        abort(404)
    data = budget.tracking(fy, project, _date(request.args.get("as_of")))
    wb = Workbook()
    wb.remove(wb.active)
    rows = [[{"expense": "Charges", "income": "Produits"}[r["kind"]], r["code"], r["label"] + (" (hors budget)" if r["unbudgeted"] else ""),
             r["planned_cents"] / 100, r["planned_to_date_cents"] / 100, r["actual_cents"] / 100, r["gap_cents"] / 100,
             r["rate"] / 100 if r["rate"] is not None else None] for r in data["rows"]]
    s = data["summary"]
    rows += [[], ["Total", "", "Charges", *(s["expense"][k] / 100 for k in ("planned_cents", "planned_to_date_cents", "actual_cents", "gap_cents"))],
             ["Total", "", "Produits", *(s["income"][k] / 100 for k in ("planned_cents", "planned_to_date_cents", "actual_cents", "gap_cents"))],
             ["Résultat", "", "", *(s["result"][k] / 100 for k in ("planned_cents", "planned_to_date_cents", "actual_cents"))]]
    ws = _sheet(wb, f"Suivi {fy.label}", ["Nature", "Compte", "Poste", "Prévu (année)", f"Prévu au {data['as_of']}",
                                          "Réalisé", "Écart", "Réalisé / prévu"], rows, (4, 5, 6, 7))
    for cell in ws.iter_cols(min_col=8, max_col=8, min_row=2):
        for c in cell:
            c.number_format = "0.0%"
    scope = f"-{project.name}" if project else ""
    return _response(wb, f"suivi-budget-{fy.label}{scope}.xlsx".replace(" ", "-"))


@bp.route("/projects/<int:project_id>/statement.xlsx")
@login_required
def project_statement_xlsx(project_id):
    project = db.session.get(Project, project_id) or abort(404)
    start, end = projects.default_period(project)
    data = projects.statement(project, _date(request.args.get("start")) or start, _date(request.args.get("end")) or end)
    wb = Workbook()
    wb.remove(wb.active)
    kinds = {"expense": "Charges", "income": "Produits"}
    t = data["totals"]
    _sheet(wb, "Compte de résultat", ["Nature", "Compte", "Libellé", "Montant"],
           [[kinds[a["kind"]], a["code"], a["label"], a["amount_cents"] / 100] for a in data["accounts"]]
           + [[], ["Total charges", "", "", t["expense_cents"] / 100], ["Total produits", "", "", t["income_cents"] / 100],
              ["Résultat", "", "", t["result_cents"] / 100]], (4,))
    _sheet(wb, "Détail", ["Date", "Pièce", "Libellé", "Compte", "Nature", "Montant", "Justificatif"],
           [[l["date"], l["reference"], l["label"], l["account"], kinds[l["kind"]], l["amount_cents"] / 100,
             request.host_url.rstrip("/") + l["document_url"] if l["document_url"] else ""] for l in data["lines"]], (6,))
    return _response(wb, f"projet-{project.name}-{data['start']}-{data['end']}.xlsx".replace(" ", "-"))


@bp.route("/simple/reports/receipts-book.xlsx")
@login_required
def receipts_book_xlsx():
    """Livre des recettes du micro-BA (lot AG1.d) : une ligne par recette, totaux par trimestre et pour l'année."""
    from app.services import micro_ba
    from app.tenant import current_chart

    if current_chart() != "agri":
        abort(404)
    year = request.args.get("year", type=int) or date.today().year
    book = micro_ba.receipts_book(year, group_small=request.args.get("group_small", "1") != "0")
    wb = Workbook()
    wb.remove(wb.active)
    rows = [[i["date"], i["label"], i["entity"] or "", i["category"], "Exclue" if i["excluded"] else "",
             i["amount_cents"] / 100] for i in book["items"]]
    rows += [[]] + [[f"Trimestre {q['quarter']}", "", "", "Recettes retenues", "", q["retained_cents"] / 100]
                    for q in book["quarters"]]
    rows += [["Année", "", "", "Recettes retenues", "", book["total"]["retained_cents"] / 100],
             ["Année", "", "", "Recettes exclues du micro-BA", "", book["total"]["excluded_cents"] / 100]]
    _sheet(wb, f"Livre des recettes {year}", ["Date", "Libellé", "Client", "Catégorie", "Micro-BA", "Montant"], rows, (6,))
    return _response(wb, f"livre-des-recettes-{year}.xlsx")


@bp.route("/reports/agri-statements.xlsx")
@login_required
def agri_statements_xlsx():
    """Soldes intermédiaires de gestion et tableau des biens vivants d'une exploitation (lot AG1.c)."""
    from app.services import agri_reports
    from app.tenant import current_chart

    if current_chart() != "agri":
        abort(404)
    fy = db.session.get(FiscalYear, request.args.get("fy_id", type=int) or 0) or abort(404)
    prev = (FiscalYear.query.filter(FiscalYear.start_date < fy.start_date)
            .order_by(FiscalYear.start_date.desc()).first())
    wb = Workbook()
    wb.remove(wb.active)
    euros = lambda cents: None if cents is None else cents / 100  # noqa: E731
    _sheet(wb, "Soldes intermédiaires", ["Solde", fy.label, prev.label if prev else "N-1"],
           [[r["label"], euros(r["n"]), euros(r["p"])] for r in agri_reports.sig(fy, prev)], (2, 3))
    table = agri_reports.living_assets_table(fy, prev)
    rows = []
    for group in table["groups"]:
        rows.append([group["label"], None, None])
        rows += [[f"  {r['label']}", euros(r["opening"]), euros(r["closing"])] for r in group["rows"]]
        rows.append([f"Total {group['label'].lower()}", euros(group["total"]["opening"]), euros(group["total"]["closing"])])
    rows.append(["TOTAL GÉNÉRAL", euros(table["total"]["opening"]), euros(table["total"]["closing"])])
    _sheet(wb, "Biens vivants", ["Nature", "Valeur nette à l'ouverture", "Valeur nette à la clôture"], rows, (2, 3))
    return _response(wb, f"etats-agricoles-{fy.label}.xlsx".replace(" ", "-"))


@bp.route("/receipts/signature")
@login_required
def receipts_signature():
    """Image de la signature des reçus (aperçu dans les paramètres)."""
    from flask import send_file

    from app.services import receipts
    path = receipts.signature_file()
    if path is None:
        abort(404)
    return send_file(path, max_age=0)


@bp.route("/receipts/<int:receipt_id>.pdf")
@login_required
def receipt_pdf(receipt_id):
    """PDF figé à l'émission (empreinte vérifiée)."""
    import hashlib

    from flask import send_file

    from app.models import DonationReceipt
    from app.services import receipts
    receipt = db.session.get(DonationReceipt, receipt_id) or abort(404)
    path = receipts.receipt_file(receipt)
    if path is None:
        abort(404)
    if hashlib.sha256(path.read_bytes()).hexdigest() != receipt.pdf_sha256:
        abort(409)
    return send_file(path, mimetype="application/pdf", download_name=f"recu-{receipt.number}.pdf", max_age=0)


@bp.route("/receipts/summary.xlsx")
@login_required
def receipts_summary_xlsx():
    """État annuel des reçus fiscaux : synthèse et liste des reçus (émis et annulés)."""
    import json as _json

    from app.models import DonationReceipt
    from app.services import receipts
    year = request.args.get("year", type=int) or abort(400)
    data = receipts.annual_summary(year)
    wb = Workbook()
    wb.remove(wb.active)
    kinds = {"individual": "Particuliers", "company": "Entreprises"}
    _sheet(wb, f"État {year}", ["Rubrique", "Nombre", "Montant"], [
        ["Reçus émis", data["issued"]["count"], data["issued"]["amount_cents"] / 100],
        *[[f"  dont {kinds[k]}", v["count"], v["amount_cents"] / 100] for k, v in data["by_kind"].items()],
        ["Reçus annulés", data["cancelled"]["count"], data["cancelled"]["amount_cents"] / 100],
        [],
        ["Dons comptabilisés de l'année", "", data["booked_donations_cents"] / 100],
        ["  dont repris sur un reçu émis", "", data["receipted_donations_cents"] / 100],
        ["  dont encore à reprendre", "", data["pending_donations_cents"] / 100],
    ], (3,))
    rows = []
    for r in DonationReceipt.query.filter_by(year=year).order_by(DonationReceipt.number):
        donor = _json.loads(r.donor_json)
        rows.append([r.number, r.issued_at.date().isoformat(), donor["name"], kinds.get(r.person_kind, r.person_kind),
                     "Annuel" if r.mode == "annual" else "Par don", r.total_cents / 100,
                     "Émis" if r.status == "issued" else "Annulé", r.cancel_reason or "",
                     r.sent_at.date().isoformat() if r.sent_at else ""])
    _sheet(wb, "Reçus", ["Numéro", "Émis le", "Donateur", "Type", "Mode", "Montant", "Statut", "Motif d'annulation",
                         "Envoyé le"], rows, (6,))
    return _response(wb, f"recus-fiscaux-{year}.xlsx")


# ------------------------------------------------------------------ déclarations de TVA (lot T3)

def _vat_return(period):
    """Déclaration du mois `AAAA-MM` : figée si validée, sinon calculée (projet)."""
    from app.services import organization, vat_return

    try:
        start, end = vat_return.parse_period(period)
    except vat_return.VatReturnError:
        abort(404)
    ret = vat_return.return_for(start)
    form = "3310-CA3-SD"
    if ret is not None:
        detail = ret.detail
        form = detail.get("form", form)
        rows, form_year, due, credit, deadline = (detail["rows"], detail["form_year"], ret.due_cents // 100,
                                                  ret.credit_cents // 100, ret.deadline)
    else:
        result = vat_return.compute(start, end)
        form = result["form"]
        rows, form_year, due, credit, deadline = (result["rows"], result["form_year"], result["due_cents"] // 100,
                                                  result["credit_cents"] // 100, vat_return.deadline(end))
    return {"org": organization.get(), "period": vat_return.period_key(start, end), "start": f"{start:%d/%m/%Y}",
            "end": f"{end:%d/%m/%Y}", "form": form, "form_year": form_year, "rows": rows, "due": due,
            "credit": credit, "deadline": f"{deadline:%d/%m/%Y}", "validated": ret is not None,
            "declared_on": f"{ret.declared_on:%d/%m/%Y}" if ret is not None and ret.declared_on else None,
            "reference": ret.declared_reference if ret is not None else None}


@bp.route("/bank-statements/<int:statement_id>.pdf")
@login_required
def bank_statement_pdf(statement_id):
    """Relevé de compte stocké (lot RQ1), affiché dans le navigateur ; tous les rôles de l'instance."""
    from flask import send_file

    from app.models import BankStatement
    from app.services import bank_statements

    statement = db.session.get(BankStatement, statement_id)
    if statement is None:
        abort(404)
    try:
        path = bank_statements.path_for(statement)
    except bank_statements.StatementError:
        abort(404)
    if not path.is_file():
        abort(404)
    name = statement.file_name or f"releve-{statement.period:%Y-%m}.pdf"
    return send_file(path, mimetype="application/pdf", download_name=name, as_attachment=False)


@bp.route("/vat-returns/<period>.xlsx")
@login_required
def vat_return_xlsx(period):
    data = _vat_return(period)
    wb = Workbook()
    wb.remove(wb.active)
    rows = [[row.get("line", ""), row.get("code") or "", row["label"],
             row["base"] if row.get("with_base") else None, row.get("amount"), row.get("note") or ""]
            if row["kind"] != "section" else ["", "", row["label"], None, None, ""] for row in data["rows"]]
    ws = _sheet(wb, f"CA3 {data['period']}", ["Ligne", "Code", "Libellé", "Base HT (€)", "Montant (€)", "Remarque"],
                rows, [4, 5])
    if not data["validated"]:
        ws.append([])
        ws.append(["", "", "Projet non validé : les montants peuvent encore changer."])
    return _response(wb, f"CA3-{data['period']}.xlsx")


@bp.route("/vat-returns/<period>.pdf")
@login_required
def vat_return_pdf(period):
    from weasyprint import HTML

    data = _vat_return(period)
    html = render_template("vat_returns/ca3.html", euros=lambda v: f"{int(v or 0):,}".replace(",", "\u202f"), **data)
    response = Response(HTML(string=html).write_pdf(), mimetype="application/pdf")
    response.headers["Content-Disposition"] = f'inline; filename="CA3-{data["period"]}.pdf"'
    return response



# ------------------------------------------------------------------ livres de TVA (lot AG2.d)

def _vat_book(kind):
    from app.services import organization, vat_books

    if kind not in ("sales", "purchases"):
        abort(404)
    try:
        start, end = vat_books.parse_bounds(request.args.get("start"), request.args.get("end"), request.args.get("period"))
    except vat_books.BookError:
        abort(400)
    book = vat_books.sales_book(start, end) if kind == "sales" else vat_books.purchases_book(start, end)
    title = "Livre des ventes" if kind == "sales" else "Livre des achats"
    return book, title, organization.get(), f"{'livre-des-ventes' if kind == 'sales' else 'livre-des-achats'}-{start}-{end}"


@bp.route("/vat-books/<kind>.xlsx")
@login_required
def vat_book_xlsx(kind):
    book, title, _, name = _vat_book(kind)
    wb = Workbook()
    wb.remove(wb.active)
    if kind == "sales":
        rows = [[i["date"], i["reference"] or "", i["label"], i["entity"], i["code"], i["line"] or "", i["category"],
                 i["base_cents"] / 100, i["tax_cents"] / 100] for i in book["items"]]
        _sheet(wb, title, ["Date", "Pièce", "Libellé", "Client", "Code TVA", "Ligne CA12A", "Catégorie", "Base HT",
                           "TVA"], rows, (8, 9))
        _sheet(wb, "Totaux", ["Ligne CA12A", "Catégorie", "Base HT", "TVA"],
               [[t["line"] or "", t["category"], t["base_cents"] / 100, t["tax_cents"] / 100] for t in book["totals"]],
               (3, 4))
    else:
        rows = [[i["date"], i["reference"] or "", i["label"], i["entity"], i["group_label"], ", ".join(i["codes"]),
                 i["ht_cents"] / 100, i["deductible_cents"] / 100, i["reverse_charge_cents"] / 100,
                 "Non déductible" if i["non_deductible"] else ""] for i in book["items"]]
        _sheet(wb, title, ["Date", "Pièce", "Libellé", "Fournisseur", "Nature", "Codes TVA", "Montant HT",
                           "TVA déductible", "TVA autoliquidée", "Mention"], rows, (7, 8, 9))
        _sheet(wb, "Totaux", ["Nature", "Montant HT", "TVA déductible", "TVA autoliquidée", "HT sans TVA déductible"],
               [[t["label"], t["ht_cents"] / 100, t["deductible_cents"] / 100, t["reverse_charge_cents"] / 100,
                 t["non_deductible_ht_cents"] / 100] for t in book["totals"]], (2, 3, 4, 5))
    return _response(wb, f"{name}.xlsx")


@bp.route("/vat-books/<kind>.pdf")
@login_required
def vat_book_pdf(kind):
    from weasyprint import HTML

    book, title, org, name = _vat_book(kind)
    money = lambda cents: f"{(cents or 0) / 100:,.2f}".replace(",", " ").replace(".", ",")  # noqa: E731
    html = render_template("vat_returns/book.html", kind=kind, book=book, title=title, org=org, money=money)
    response = Response(HTML(string=html).write_pdf(), mimetype="application/pdf")
    response.headers["Content-Disposition"] = f'inline; filename="{name}.pdf"'
    return response


# ------------------------------------------------------------------ remboursement forfaitaire (lot AG2.e)

def _rfa(year):
    from app.services import organization, rfa
    from app.tenant import current_chart

    if current_chart() != "agri":
        abort(404)
    return rfa.compute(year), rfa, organization.get()


@bp.route("/fiscal-years/<int:fy_id>/tax-result.xlsx")
@login_required
def tax_result_xlsx(fy_id):
    """Tableau de passage du résultat comptable au résultat fiscal et répartition par associé (lot AG6.a)."""
    from app.models import FiscalYear
    from app.services import tax_result

    if not tax_result.enabled():
        abort(404)
    fy = db.session.get(FiscalYear, fy_id) or abort(404)
    data = tax_result.view(fy)
    wb = Workbook()
    wb.remove(wb.active)
    rows = [["Résultat comptable", data["accounting_result_cents"] / 100, ""]]
    rows += [[l["label"], l["amount_cents"] / 100, l.get("reason") or ""] for l in data["lines"]]
    rows.append(["Résultat fiscal", data["fiscal_result_cents"] / 100, "figé" if data["frozen"] else ""])
    _sheet(wb, f"Passage {fy.label}", ["Ligne", "Montant", "Motif"], rows, (2,))
    if data["associates"]:
        _sheet(wb, "Associés", ["Associé", "Exploitant", "Quote-part (%)", "Base", "Résultat fiscal"],
               [[a["name"], "oui" if a["is_operator"] else "non", a["share_bp"] / 100, a["basis"],
                 a["fiscal_result_cents"] / 100] for a in data["associates"]], (3, 5))
    return _response(wb, f"resultat-fiscal-{fy.label}.xlsx")


def _liasse(fy_id):
    from app.models import FiscalYear
    from app.services import liasse, organization, tax_result

    if not tax_result.enabled():
        abort(404)
    fy = db.session.get(FiscalYear, fy_id) or abort(404)
    try:
        data = liasse.compute(fy)
    except liasse.LiasseError:
        abort(404)
    if not data["form"]:
        abort(404)
    return data, organization.get()


@bp.route("/fiscal-years/<int:fy_id>/liasse.xlsx")
@login_required
def liasse_xlsx(fy_id):
    """Aide à la liasse 2139 / 2143 : une feuille par tableau, case → montant (lot AG6.f)."""
    data, _org = _liasse(fy_id)
    wb = Workbook()
    wb.remove(wb.active)
    for table in data["tables"]:
        rows = [[r["case"], ("    dont " if r["detail"] and not r["label"].startswith("dont") else "") + r["label"],
                 None if r["amount_cents"] is None else r["amount_cents"] / 100,
                 "à saisir" if r["kind"] == "manual" else ", ".join(r["accounts"] or []) if r["kind"] == "accounts"
                 else "résultat fiscal" if r["kind"] == "tax" else "total"] for r in table["rows"]]
        _sheet(wb, table["code"], ["Case", "Libellé", "Montant", "Origine"], rows, (3,))
    _sheet(wb, "Avertissements", ["Avertissement"], [[w] for w in data["warnings"] + data["not_covered"]], ())
    return _response(wb, f"liasse-{data['form']}-{data['fiscal_year']['label']}.xlsx")


@bp.route("/fiscal-years/<int:fy_id>/liasse.pdf")
@login_required
def liasse_pdf(fy_id):
    from weasyprint import HTML

    data, org = _liasse(fy_id)
    euros = lambda cents: "" if cents is None else f"{round(cents / 100):,}".replace(",", "\u202f")  # noqa: E731
    html = render_template("tax_result/liasse.html", data=data, org=org, euros=euros)
    response = Response(HTML(string=html).write_pdf(), mimetype="application/pdf")
    response.headers["Content-Disposition"] = f'inline; filename="liasse-{data["form"]}-{data["fiscal_year"]["label"]}.pdf"'
    return response


@bp.route("/fiscal-years/<int:fy_id>/stock.xlsx")
@login_required
def stock_xlsx(fy_id):
    """État d'inventaire de clôture (lot AG4.d) : lignes, méthodes, valeurs, dépréciations, total par catégorie."""
    from app.models import FiscalYear, StockLine
    from app.models.stock import STOCK_METHODS, STOCK_UNITS
    from app.models.stock import FISCAL_METHODS
    from app.services import stock_entry, stock_inventory as inv, stock_tax

    if not inv.enabled():
        abort(404)
    fy = db.session.get(FiscalYear, fy_id) or abort(404)
    discount_map = inv.discounts(fy)
    labels = {c["key"]: c["label"] for c in inv.categories()}
    wb = Workbook()
    wb.remove(wb.active)
    rows, totals = [], {}
    for line in StockLine.query.filter_by(fiscal_year_id=fy.id).order_by(StockLine.position, StockLine.id):
        unit, value, warnings = inv.evaluate(line, fy, discount_map)
        fiscal = stock_tax.fiscal_value(line, fy)
        rows.append([labels.get(line.category, line.category), line.account.code, line.variation_account.code, line.label,
                     line.production, float(line.quantity or 0), STOCK_UNITS.get(line.unit, line.unit),
                     STOCK_METHODS.get(line.method, line.method), (unit or 0) / 100 if unit is not None else None,
                     (value or 0) / 100 if value is not None else None, (line.depreciation_cents or 0) / 100 or None,
                     line.depreciation_reason, FISCAL_METHODS.get(fiscal["fiscal_method"], ""),
                     fiscal["fiscal_value_cents"] / 100 if fiscal["fiscal_value_cents"] is not None else None,
                     fiscal["gap_cents"] / 100 if fiscal["gap_cents"] is not None else None,
                     "; ".join([*warnings, *fiscal["warnings"]])])
        totals[line.category] = totals.get(line.category, 0) + (value or 0)
    _sheet(wb, f"Inventaire {fy.label}", ["Catégorie", "Compte", "Variation", "Libellé", "Production", "Quantité", "Unité",
                                          "Méthode", "Valeur unitaire", "Valeur", "Dépréciation", "Motif",
                                          "Méthode fiscale", "Valeur fiscale", "Écart fiscal", "Contrôles"],
           rows, (9, 10, 11, 14, 15))
    status = stock_entry.status(fy)
    summary = [[labels.get(k, k), v / 100] for k, v in totals.items()]
    summary += [["Stock final", status["final_cents"] / 100], ["Stock initial (avant écriture)", status["opening_cents"] / 100],
                ["Variation", status["variation_cents"] / 100], ["Dépréciations", status["depreciation_cents"] / 100]]
    tax = stock_tax.totals(fy)
    summary += [["Valeur fiscale des stocks", tax["fiscal_cents"] / 100],
                ["Écart fiscal (tableau de passage)", tax["gap_cents"] / 100]]
    _sheet(wb, "Totaux", ["Élément", "Montant"], summary, (2,))
    return _response(wb, f"inventaire-{fy.label}.xlsx")


@bp.route("/rfa/<int:year>.xlsx")
@login_required
def rfa_xlsx(year):
    data, rfa, _ = _rfa(year)
    wb = Workbook()
    wb.remove(wb.active)
    rows = [[c["name"], rfa.BUYERS.get(c["buyer"], "Inconnu"), "oui" if c["eligible"] else "non", c["high_cents"] / 100,
             c["low_cents"] / 100, c["excluded_cents"] / 100, c["unclassified_cents"] / 100,
             (c["attestation"] or {}).get("amount_cents", 0) / 100 if c["attestation"] else None, "; ".join(c["issues"])]
            for c in data["clients"]]
    _sheet(wb, f"Clients {year}", ["Client", "Type", "Éligible", "Taux 5,59 %", "Taux 4,43 %", "Exclues", "Sans classe",
                                   "Attesté", "Contrôles"], rows, (4, 5, 6, 7, 8))
    summary = [["Base au taux de 5,59 %", data["high_base_cents"] / 100],
               ["Base au taux de 4,43 %", data["low_base_cents"] / 100],
               ["Ventes exclues (classe)", data["excluded_cents"] / 100],
               ["Ventes à des non-assujettis", data["non_eligible_cents"] / 100],
               ["Remboursement forfaitaire", data["amount_cents"] / 100]]
    _sheet(wb, "Forfait", ["Élément", "Montant"], summary, (2,))
    return _response(wb, f"remboursement-forfaitaire-{year}.xlsx")


@bp.route("/rfa/<int:year>.pdf")
@login_required
def rfa_pdf(year):
    from weasyprint import HTML

    data, rfa, org = _rfa(year)
    money = lambda cents: f"{(cents or 0) / 100:,.2f}".replace(",", " ").replace(".", ",")  # noqa: E731
    html = render_template("vat_returns/rfa.html", data=data, org=org, money=money, buyers=rfa.BUYERS)
    response = Response(HTML(string=html).write_pdf(), mimetype="application/pdf")
    response.headers["Content-Disposition"] = f'inline; filename="remboursement-forfaitaire-{year}.pdf"'
    return response
