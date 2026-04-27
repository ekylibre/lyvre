import csv
from io import StringIO
from flask import Blueprint, render_template, request, Response, abort
from flask_login import login_required
from app.models import FiscalYear, Account, JournalEntry, JournalLine
from app.extensions import db
from app.services.ledger import trial_balance, general_ledger
from app.services.reports import build_bilan, build_compte_resultat

bp = Blueprint("reports", __name__, url_prefix="/reports")


def _get_fy():
    fy_id = request.args.get("fy_id", type=int)
    if fy_id:
        return FiscalYear.query.get_or_404(fy_id)
    return FiscalYear.query.filter_by(closed=False).order_by(FiscalYear.start_date.desc()).first()


@bp.route("/balance")
@login_required
def balance():
    fiscal_years = FiscalYear.query.order_by(FiscalYear.start_date.desc()).all()
    fy = _get_fy()
    rows, _ = trial_balance(fy.id) if fy else ([], None)
    return render_template("reports/balance.html", rows=rows, fy=fy, fiscal_years=fiscal_years)


@bp.route("/grand-livre")
@login_required
def grand_livre():
    fiscal_years = FiscalYear.query.order_by(FiscalYear.start_date.desc()).all()
    fy = _get_fy()
    account_id = request.args.get("account_id", type=int)
    account, rows = general_ledger(account_id, fy.id) if account_id and fy else (None, [])
    accounts = Account.query.filter_by(is_header=False).order_by(Account.code).all()
    return render_template(
        "reports/grand_livre.html",
        account=account,
        rows=rows,
        fy=fy,
        fiscal_years=fiscal_years,
        accounts=accounts,
        selected_account_id=account_id,
    )


@bp.route("/bilan")
@login_required
def bilan():
    fiscal_years = FiscalYear.query.order_by(FiscalYear.start_date.desc()).all()
    fy = _get_fy()
    fy_prev = None
    if fy:
        fy_prev = (
            FiscalYear.query
            .filter(FiscalYear.start_date < fy.start_date)
            .order_by(FiscalYear.start_date.desc())
            .first()
        )
    data = build_bilan(fy, fy_prev) if fy else None
    return render_template("reports/bilan.html", data=data, fy=fy, fy_prev=fy_prev, fiscal_years=fiscal_years)


@bp.route("/compte-de-resultat")
@login_required
def compte_resultat():
    from datetime import date
    fiscal_years = FiscalYear.query.order_by(FiscalYear.start_date.desc()).all()
    fy = _get_fy()
    fy_prev = None
    if fy:
        fy_prev = (
            FiscalYear.query
            .filter(FiscalYear.start_date < fy.start_date)
            .order_by(FiscalYear.start_date.desc())
            .first()
        )
    data = build_compte_resultat(fy, fy_prev) if fy else None
    return render_template(
        "reports/compte_resultat.html", data=data, fy=fy, fy_prev=fy_prev,
        fiscal_years=fiscal_years, now_date=date.today(),
    )


def _euros_csv(cents):
    if cents is None:
        return ""
    return f"{cents / 100:.2f}".replace(".", ",")


def _cdr_rows(data):
    """Yields tuples (kind, label, n_value, p_value).

    kind: 'section' (en-tête de section), 'row' (ligne détail),
          'subhead' (en-tête de sous-groupe sans valeur), 'total' (total intermédiaire),
          'result' (résultat encadré).
    """
    pe = data["produits_exploitation"]
    ce = data["charges_exploitation"]
    pf = data["produits_financiers"]
    cf = data["charges_financieres"]
    px = data["produits_exceptionnels"]
    cx = data["charges_exceptionnelles"]
    cprod = data["contributions_produits"]
    ccharges = data["contributions_charges"]

    total_I = sum(v[0] for v in pe.values())
    total_I_p = sum((v[1] or 0) for v in pe.values()) if any(v[1] is not None for v in pe.values()) else None
    total_II = sum(v[0] for v in ce.values())
    total_II_p = sum((v[1] or 0) for v in ce.values()) if any(v[1] is not None for v in ce.values()) else None
    total_III = sum(v[0] for v in pf.values())
    total_III_p = sum((v[1] or 0) for v in pf.values()) if any(v[1] is not None for v in pf.values()) else None
    total_IV = sum(v[0] for v in cf.values())
    total_IV_p = sum((v[1] or 0) for v in cf.values()) if any(v[1] is not None for v in cf.values()) else None
    total_V = sum(v[0] for v in px.values())
    total_V_p = sum((v[1] or 0) for v in px.values()) if any(v[1] is not None for v in px.values()) else None
    total_VI = sum(v[0] for v in cx.values())
    total_VI_p = sum((v[1] or 0) for v in cx.values()) if any(v[1] is not None for v in cx.values()) else None

    yield ("section", "PRODUITS D'EXPLOITATION", None, None)
    yield ("row", "Cotisations", *pe["cotisations"])
    yield ("subhead", "Ventes de biens et services", None, None)
    yield ("row", "  Ventes de biens", *pe["ventes_biens"])
    yield ("row", "    dont ventes de dons en nature", *pe["dont_ventes_dons_nature"])
    yield ("row", "  Ventes de prestations de services", *pe["ventes_prestations"])
    yield ("row", "    dont parrainages", *pe["dont_parrainages"])
    yield ("subhead", "Produits de tiers financeurs", None, None)
    yield ("row", "  Concours publics et subventions d'exploitation", *pe["concours_publics_subventions"])
    yield ("row", "  Versements des fondateurs / dotation consomptible", *pe["versements_fondateurs_dotation"])
    yield ("subhead", "  Ressources liées à la générosité du public", None, None)
    yield ("row", "    Dons manuels", *pe["dons_manuels"])
    yield ("row", "    Mécénats", *pe["mecenat"])
    yield ("row", "    Legs, donations et assurances-vie", *pe["legs_donations"])
    yield ("row", "  Contributions financières", *pe["contributions_financieres"])
    yield ("row", "Reprises sur amortissements, dépréciations, provisions", *pe["reprises_amort_provisions"])
    yield ("row", "Utilisations des fonds dédiés", *pe["utilisations_fonds_dedies"])
    yield ("row", "Autres produits", *pe["autres_produits"])
    yield ("total", "TOTAL I — Produits d'exploitation", total_I, total_I_p)

    yield ("section", "CHARGES D'EXPLOITATION", None, None)
    yield ("row", "Achats de marchandises", *ce["achats_marchandises"])
    yield ("row", "Variation de stocks", *ce["variation_stocks"])
    yield ("row", "Autres achats et charges externes", *ce["autres_achats_charges_externes"])
    yield ("row", "Aides financières", *ce["aides_financieres"])
    yield ("row", "Impôts, taxes et versements assimilés", *ce["impots_taxes"])
    yield ("row", "Salaires et traitements", *ce["salaires_traitements"])
    yield ("row", "Charges sociales", *ce["charges_sociales"])
    yield ("row", "Dotations aux amortissements et aux dépréciations", *ce["dotations_amort_depreciations"])
    yield ("row", "Dotations aux provisions", *ce["dotations_provisions"])
    yield ("row", "Reports en fonds dédiés", *ce["reports_fonds_dedies"])
    yield ("row", "Autres charges", *ce["autres_charges"])
    yield ("total", "TOTAL II — Charges d'exploitation", total_II, total_II_p)
    yield ("result", "1 — RÉSULTAT D'EXPLOITATION (I - II)",
           total_I - total_II,
           (total_I_p - total_II_p) if total_I_p is not None and total_II_p is not None else None)

    yield ("section", "PRODUITS FINANCIERS", None, None)
    yield ("row", "De participations", *pf["de_participations"])
    yield ("row", "Autres intérêts et produits assimilés", *pf["autres_interets"])
    yield ("row", "Produits nets sur cessions de VMP", *pf["produits_nets_cessions_vmp"])
    yield ("total", "TOTAL III — Produits financiers", total_III, total_III_p)

    yield ("section", "CHARGES FINANCIÈRES", None, None)
    yield ("row", "Intérêts et charges assimilées", *cf["interets_charges"])
    yield ("total", "TOTAL IV — Charges financières", total_IV, total_IV_p)
    yield ("result", "2 — RÉSULTAT FINANCIER (III - IV)",
           total_III - total_IV,
           (total_III_p - total_IV_p) if total_III_p is not None and total_IV_p is not None else None)
    yield ("result", "3 — RÉSULTAT COURANT avant impôts",
           total_I - total_II + total_III - total_IV,
           ((total_I_p - total_II_p + total_III_p - total_IV_p)
            if None not in (total_I_p, total_II_p, total_III_p, total_IV_p) else None))

    yield ("section", "PRODUITS EXCEPTIONNELS", None, None)
    yield ("row", "Sur opérations de gestion", *px["sur_operations_gestion"])
    yield ("row", "Sur opérations en capital", *px["sur_operations_capital"])
    yield ("row", "Reprises sur provisions", *px["reprises_provisions"])
    yield ("total", "TOTAL V — Produits exceptionnels", total_V, total_V_p)

    yield ("section", "CHARGES EXCEPTIONNELLES", None, None)
    yield ("row", "Sur opérations de gestion", *cx["sur_operations_gestion"])
    yield ("row", "Sur opérations en capital", *cx["sur_operations_capital"])
    yield ("row", "Dotations aux amortissements", *cx["dotations_amort"])
    yield ("total", "TOTAL VI — Charges exceptionnelles", total_VI, total_VI_p)
    yield ("result", "4 — RÉSULTAT EXCEPTIONNEL (V - VI)",
           total_V - total_VI,
           (total_V_p - total_VI_p) if total_V_p is not None and total_VI_p is not None else None)

    ps = data["participation_salaries"]
    ib = data["impots_benefices"]
    yield ("row", "Participation des salariés aux résultats (VII)", *ps)
    yield ("row", "Impôts sur les bénéfices (VIII)", *ib)

    total_produits = total_I + total_III + total_V
    total_charges = total_II + total_IV + total_VI + ps[0] + ib[0]
    yield ("total", "Total des produits (I+III+V)", total_produits, None)
    yield ("total", "Total des charges (II+IV+VI+VII+VIII)", total_charges, None)
    excedent = total_produits - total_charges
    yield ("result", "EXCÉDENT" if excedent >= 0 else "DÉFICIT", excedent, None)

    yield ("section", "CONTRIBUTIONS VOLONTAIRES EN NATURE", None, None)
    yield ("row", "Dons en nature", *cprod["dons_nature"])
    yield ("row", "Prestations en nature", *cprod["prestations_nature"])
    yield ("row", "Bénévolat", *cprod["benevolat"])
    total_cvn = sum(v[0] for v in cprod.values())
    yield ("total", "Total contributions volontaires (produits)", total_cvn, None)

    yield ("section", "CHARGES DES CONTRIBUTIONS VOLONTAIRES", None, None)
    yield ("row", "Secours en nature", *ccharges["secours_nature"])
    yield ("row", "Mise à disposition gratuite de biens", *ccharges["mise_dispo_biens"])
    yield ("row", "Prestations en nature", *ccharges["prestations_nature"])
    yield ("row", "Personnel bénévole", *ccharges["personnel_benevole"])
    total_cvn_c = sum(v[0] for v in ccharges.values())
    yield ("total", "Total contributions volontaires (charges)", total_cvn_c, None)


@bp.route("/compte-de-resultat.csv")
@login_required
def compte_resultat_csv():
    fy = _get_fy()
    if fy is None:
        abort(404, "Aucun exercice ouvert.")
    fy_prev = (
        FiscalYear.query
        .filter(FiscalYear.start_date < fy.start_date)
        .order_by(FiscalYear.start_date.desc())
        .first()
    )
    data = build_compte_resultat(fy, fy_prev)

    output = StringIO()
    writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(["Compte de résultat"])
    writer.writerow(["Exercice N", fy.label,
                     fy.start_date.isoformat() + " → " + fy.end_date.isoformat()])
    if fy_prev:
        writer.writerow(["Exercice N-1", fy_prev.label,
                         fy_prev.start_date.isoformat() + " → " + fy_prev.end_date.isoformat()])
    writer.writerow([])
    writer.writerow([
        "Type",
        "Libellé",
        f"Exercice N ({fy.label}) en €",
        f"Exercice N-1 ({fy_prev.label}) en €" if fy_prev else "Exercice N-1 en €",
    ])

    for kind, label, n_val, p_val in _cdr_rows(data):
        writer.writerow([
            kind,
            label,
            _euros_csv(n_val) if n_val is not None else "",
            _euros_csv(p_val) if p_val is not None else "",
        ])

    csv_bytes = output.getvalue().encode("utf-8-sig")
    response = Response(csv_bytes, mimetype="text/csv")
    response.headers["Content-Disposition"] = (
        f'attachment; filename="compte-de-resultat-{fy.label}.csv"'
    )
    return response


def _build_cdr_ods(data, fy, fy_prev):
    """Build an ODS spreadsheet with embedded formulas.

    Section totals use =SUM(range) over their child rows.
    Result rows use explicit references to the totals' cells.
    Pre-computed values are also stored so the file opens directly.
    """
    from io import BytesIO
    from odf.opendocument import OpenDocumentSpreadsheet
    from odf.style import (
        Style, TableCellProperties, TableColumnProperties,
        TextProperties, ParagraphProperties,
    )
    from odf.number import (
        NumberStyle, Number, CurrencySymbol, CurrencyStyle, Text as NumberText,
    )
    from odf.table import Table, TableRow, TableCell, TableColumn
    from odf.text import P

    doc = OpenDocumentSpreadsheet()

    # ----- Number format for euros: #,##0.00 €
    eur_fmt = CurrencyStyle(name="EUR", volatile="true")
    eur_fmt.addElement(Number(decimalplaces="2", minintegerdigits="1", grouping="true"))
    eur_fmt.addElement(NumberText(text=" "))
    eur_fmt.addElement(CurrencySymbol(language="fr", country="FR", text="€"))
    doc.styles.addElement(eur_fmt)

    def make_style(name, **props):
        s = Style(name=name, family="table-cell", datastylename="EUR")
        cell_props = {k: v for k, v in props.items() if k.startswith(("backgroundcolor", "border"))}
        text_props = {k: v for k, v in props.items() if k in ("fontweight", "fontsize", "color")}
        if cell_props:
            s.addElement(TableCellProperties(**cell_props))
        if text_props:
            s.addElement(TextProperties(**text_props))
        doc.automaticstyles.addElement(s)
        return s

    title_style = make_style("Title", fontweight="bold", fontsize="14pt")
    subtitle_style = make_style("Subtitle", fontsize="10pt", color="#444444")
    header_style = make_style("Header", fontweight="bold", backgroundcolor="#1c2530",
                              color="#ffffff", border="0.5pt solid #000000")
    section_style = make_style("Section", fontweight="bold", backgroundcolor="#d8e1ea",
                               border="0.5pt solid #1c2530")
    subhead_style = make_style("Subhead", fontweight="bold", backgroundcolor="#f3f3f3")
    total_style = make_style("Total", fontweight="bold", backgroundcolor="#eaeaea",
                             border="0.5pt solid #1c2530")
    result_style = make_style("Result", fontweight="bold", backgroundcolor="#cfe2f3",
                              border="0.7pt solid #1c2530")
    money_style = make_style("Money")

    # Column widths
    col_label = Style(name="ColLabel", family="table-column")
    col_label.addElement(TableColumnProperties(columnwidth="11cm"))
    col_money = Style(name="ColMoney", family="table-column")
    col_money.addElement(TableColumnProperties(columnwidth="3.5cm"))
    doc.automaticstyles.addElement(col_label)
    doc.automaticstyles.addElement(col_money)

    table = Table(name="Compte de résultat")
    table.addElement(TableColumn(stylename=col_label))
    table.addElement(TableColumn(stylename=col_money, numbercolumnsrepeated="2"))

    state = {"row": 0, "data_start": None, "totals": {}, "vii": None, "viii": None}

    def text_cell(text, style=None, span=1):
        cell = TableCell(numbercolumnsspanned=str(span)) if span > 1 else TableCell()
        if style is not None:
            cell.setAttribute("stylename", style.getAttribute("name"))
        cell.addElement(P(text=text or ""))
        return cell

    def covered():
        return TableCell()  # placeholder for spanned cells

    def number_cell(cents, style=None, formula=None):
        attrs = {"valuetype": "float"}
        value_str = ""
        if cents is not None:
            value_str = f"{cents / 100:.2f}"
        if formula is not None:
            attrs["formula"] = "of:" + formula
        if value_str:
            attrs["value"] = value_str
        cell = TableCell(**attrs)
        if style is not None:
            cell.setAttribute("stylename", style.getAttribute("name"))
        if value_str:
            cell.addElement(P(text=value_str.replace(".", ",") + " €"))
        return cell

    def emit_blank():
        state["row"] += 1
        table.addElement(TableRow())

    def emit_full(text, style):
        state["row"] += 1
        tr = TableRow()
        tr.addElement(text_cell(text, style=style, span=3))
        tr.addElement(covered())
        tr.addElement(covered())
        table.addElement(tr)

    def emit_header_row():
        state["row"] += 1
        tr = TableRow()
        tr.addElement(text_cell("", style=header_style))
        tr.addElement(text_cell(f"Exercice N ({fy.label})", style=header_style))
        tr.addElement(text_cell(
            f"Exercice N-1 ({fy_prev.label})" if fy_prev else "Exercice N-1",
            style=header_style,
        ))
        table.addElement(tr)

    def emit_data(label, n_val, p_val, label_style=None, value_style=None,
                  n_formula=None, p_formula=None):
        state["row"] += 1
        tr = TableRow()
        tr.addElement(text_cell(label, style=label_style))
        tr.addElement(number_cell(n_val, style=value_style or money_style, formula=n_formula))
        tr.addElement(number_cell(p_val, style=value_style or money_style, formula=p_formula))
        table.addElement(tr)
        return state["row"]

    # ---------- Render ----------
    emit_full("COMPTE DE RÉSULTAT", title_style)
    emit_full(
        f"Exercice N : {fy.label} ({fy.start_date.strftime('%d/%m/%Y')} → "
        f"{fy.end_date.strftime('%d/%m/%Y')})",
        subtitle_style,
    )
    if fy_prev:
        emit_full(
            f"Exercice N-1 : {fy_prev.label} ({fy_prev.start_date.strftime('%d/%m/%Y')} → "
            f"{fy_prev.end_date.strftime('%d/%m/%Y')})",
            subtitle_style,
        )
    emit_blank()
    emit_header_row()

    # Process the flat row sequence from _cdr_rows, building formulas dynamically
    pending_first = None  # spreadsheet row of first data row in current section
    pending_last = None

    def reset_pending():
        nonlocal pending_first, pending_last
        pending_first = None
        pending_last = None

    def track_data(row_num):
        nonlocal pending_first, pending_last
        if pending_first is None:
            pending_first = row_num
        pending_last = row_num

    section_total_label_to_key = {
        "TOTAL I —": "I", "TOTAL II —": "II", "TOTAL III —": "III",
        "TOTAL IV —": "IV", "TOTAL V —": "V", "TOTAL VI —": "VI",
    }

    for kind, label, n_val, p_val in _cdr_rows(data):
        if kind == "section":
            reset_pending()
            emit_full(label, section_style)
            continue

        if kind == "subhead":
            r = emit_data(label, None, None, label_style=subhead_style)
            continue

        if kind == "row":
            r = emit_data(label, n_val, p_val)
            # "dont" sub-lines and subheads are not summed; only proper rows
            track_data(r)
            if "(VII)" in label:
                state["vii"] = r
            elif "(VIII)" in label:
                state["viii"] = r
            continue

        if kind == "total":
            n_formula = p_formula = None
            for key_prefix, key in section_total_label_to_key.items():
                if label.startswith(key_prefix):
                    if pending_first and pending_last and pending_last >= pending_first:
                        n_formula = f"=SUM([.B{pending_first}:.B{pending_last}])"
                        p_formula = f"=SUM([.C{pending_first}:.C{pending_last}])"
                    r = emit_data(label, n_val, p_val, value_style=total_style,
                                  label_style=total_style,
                                  n_formula=n_formula, p_formula=p_formula)
                    state["totals"][key] = r
                    reset_pending()
                    break
            else:
                # Non-section totals: "Total des produits", "Total des charges",
                # contributions totals
                if "Total des produits" in label:
                    n_formula = (
                        f"=[.B{state['totals']['I']}]+[.B{state['totals']['III']}]"
                        f"+[.B{state['totals']['V']}]"
                    )
                    r = emit_data(label, n_val, p_val, value_style=total_style,
                                  label_style=total_style, n_formula=n_formula)
                    state["total_produits"] = r
                elif "Total des charges" in label:
                    n_formula = (
                        f"=[.B{state['totals']['II']}]+[.B{state['totals']['IV']}]"
                        f"+[.B{state['totals']['VI']}]"
                        f"+[.B{state['vii']}]+[.B{state['viii']}]"
                    )
                    r = emit_data(label, n_val, p_val, value_style=total_style,
                                  label_style=total_style, n_formula=n_formula)
                    state["total_charges"] = r
                else:
                    # Contributions totals — straight SUM of pending rows
                    if pending_first and pending_last and pending_last >= pending_first:
                        n_formula = f"=SUM([.B{pending_first}:.B{pending_last}])"
                        p_formula = f"=SUM([.C{pending_first}:.C{pending_last}])"
                    r = emit_data(label, n_val, p_val, value_style=total_style,
                                  label_style=total_style,
                                  n_formula=n_formula, p_formula=p_formula)
                    reset_pending()
            continue

        if kind == "result":
            n_formula = p_formula = None
            t = state["totals"]
            if "RÉSULTAT D'EXPLOITATION" in label:
                n_formula = f"=[.B{t['I']}]-[.B{t['II']}]"
                if "I" in t and "II" in t and "I_p" not in t:
                    p_formula = f"=[.C{t['I']}]-[.C{t['II']}]"
            elif "RÉSULTAT FINANCIER" in label:
                n_formula = f"=[.B{t['III']}]-[.B{t['IV']}]"
                p_formula = f"=[.C{t['III']}]-[.C{t['IV']}]"
            elif "RÉSULTAT COURANT" in label:
                n_formula = (
                    f"=[.B{t['I']}]-[.B{t['II']}]"
                    f"+[.B{t['III']}]-[.B{t['IV']}]"
                )
            elif "RÉSULTAT EXCEPTIONNEL" in label:
                n_formula = f"=[.B{t['V']}]-[.B{t['VI']}]"
                p_formula = f"=[.C{t['V']}]-[.C{t['VI']}]"
            elif "EXCÉDENT" in label or "DÉFICIT" in label:
                n_formula = (
                    f"=[.B{state.get('total_produits')}]"
                    f"-[.B{state.get('total_charges')}]"
                )
            emit_data(label, n_val, p_val, value_style=result_style,
                      label_style=result_style,
                      n_formula=n_formula, p_formula=p_formula)
            continue

    doc.spreadsheet.addElement(table)

    buf = BytesIO()
    doc.write(buf)
    return buf.getvalue()


@bp.route("/compte-de-resultat.ods")
@login_required
def compte_resultat_ods():
    fy = _get_fy()
    if fy is None:
        abort(404, "Aucun exercice ouvert.")
    fy_prev = (
        FiscalYear.query
        .filter(FiscalYear.start_date < fy.start_date)
        .order_by(FiscalYear.start_date.desc())
        .first()
    )
    data = build_compte_resultat(fy, fy_prev)
    ods_bytes = _build_cdr_ods(data, fy, fy_prev)
    response = Response(
        ods_bytes,
        mimetype="application/vnd.oasis.opendocument.spreadsheet",
    )
    response.headers["Content-Disposition"] = (
        f'attachment; filename="compte-de-resultat-{fy.label}.ods"'
    )
    return response
