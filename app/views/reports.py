"""Exports du compte de résultat (CSV, ODS). Les états financiers sont des pages de la SPA
(app/spa_routes.json) alimentées par app/api/reports.py."""
import csv
from io import StringIO
from flask import Blueprint, request, Response, abort
from flask_login import login_required
from app.models import FiscalYear
from app.services.reports import build_compte_resultat, compte_resultat_rows
from app.tenant import current_chart

bp = Blueprint("reports", __name__, url_prefix="/reports")


def _get_fy():
    fy_id = request.args.get("fy_id", type=int)
    if fy_id:
        return FiscalYear.query.get_or_404(fy_id)
    return FiscalYear.query.filter_by(closed=False).order_by(FiscalYear.start_date.desc()).first()


def _get_prev_fy(fy):
    if fy is None:
        return None
    return (
        FiscalYear.query
        .filter(FiscalYear.start_date < fy.start_date)
        .order_by(FiscalYear.start_date.desc())
        .first()
    )


def _euros_csv(cents):
    if cents is None:
        return ""
    return f"{cents / 100:.2f}".replace(".", ",")


@bp.route("/compte-de-resultat.csv")
@login_required
def compte_resultat_csv():
    fy = _get_fy()
    if fy is None:
        abort(404, "Aucun exercice ouvert.")
    fy_prev = _get_prev_fy(fy)
    chart = current_chart()
    data = build_compte_resultat(fy, fy_prev, chart)

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

    for kind, label, n_val, p_val in compte_resultat_rows(data, chart):
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


def _build_cdr_ods(data, fy, fy_prev, chart="asso"):
    """Build an ODS spreadsheet with embedded formulas.

    Section totals sum their child rows ("dont" sub-lines excluded).
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

    # Process the flat row sequence from compte_resultat_rows, building formulas dynamically
    pending = []  # spreadsheet rows summed by the current section total

    def reset_pending():
        pending.clear()

    def track_data(row_num):
        pending.append(row_num)

    def sum_formulas():
        # Explicit cell list: "dont" sub-lines sit between summed rows.
        if not pending:
            return None, None
        return ("=" + "+".join(f"[.B{r}]" for r in pending),
                "=" + "+".join(f"[.C{r}]" for r in pending))

    section_total_label_to_key = {
        "TOTAL I —": "I", "TOTAL II —": "II", "TOTAL III —": "III",
        "TOTAL IV —": "IV", "TOTAL V —": "V", "TOTAL VI —": "VI",
    }

    for kind, label, n_val, p_val in compte_resultat_rows(data, chart):
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
            if not label.strip().startswith("dont "):
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
                    n_formula, p_formula = sum_formulas()
                    r = emit_data(label, n_val, p_val, value_style=total_style,
                                  label_style=total_style,
                                  n_formula=n_formula, p_formula=p_formula)
                    state["totals"][key] = r
                    reset_pending()
                    break
            else:
                # Non-section totals: "Total des produits", "Total des charges",
                # contributions totals
                if label.startswith("Montant net du chiffre d'affaires"):
                    # Sous-total agricole (AG1.c) : somme des ventes, sans clore la section (TOTAL I).
                    n_formula, p_formula = sum_formulas()
                    emit_data(label, n_val, p_val, value_style=total_style, label_style=total_style,
                              n_formula=n_formula, p_formula=p_formula)
                elif "Total des produits" in label:
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
                    n_formula, p_formula = sum_formulas()
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
            elif label in ("EXCÉDENT", "DÉFICIT", "BÉNÉFICE", "PERTE"):
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
    fy_prev = _get_prev_fy(fy)
    chart = current_chart()
    data = build_compte_resultat(fy, fy_prev, chart)
    ods_bytes = _build_cdr_ods(data, fy, fy_prev, chart)
    response = Response(
        ods_bytes,
        mimetype="application/vnd.oasis.opendocument.spreadsheet",
    )
    response.headers["Content-Disposition"] = (
        f'attachment; filename="compte-de-resultat-{fy.label}.ods"'
    )
    return response
