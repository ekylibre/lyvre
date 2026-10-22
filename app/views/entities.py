"""Exports des adhérents (fichiers CSV / XLSX). Les écrans des tiers et des adhérents
sont des pages de la SPA (app/spa_routes.json), leurs données passent par l'API
(app/api/entities.py, app/api/members.py)."""
import csv
from io import BytesIO, StringIO

from flask import Blueprint, Response, redirect, request, url_for
from flask_login import login_required

from app.queries.entities import member_rows

bp = Blueprint("entities", __name__, url_prefix="/entities")

EXPORT_HEADERS = [
    "Nom", "Email", "Adhérent", "Bénévole",
    "Dernière adhésion HelloAsso", "Dernière adhésion POS",
    "Date anniversaire", "Statut", "Couleur", "Notes",
]


def _export_record(row):
    """Transforme une row enrichie en liste de valeurs prêtes à exporter."""
    ha = row["last_ha"]
    pos = row["last_pos"]
    return [
        row["name"],
        row["email"] or "",
        "Oui" if row["is_member"] else "Non",
        "Oui" if row["is_benevole"] else "Non",
        ha.strftime("%d/%m/%Y") if ha else "",
        pos.strftime("%d/%m/%Y") if pos else "",
        row["birthday"].strftime("%d/%m/%Y"),
        row["status"],
        row["color"],
        row["notes"] or "",
    ]


def _render_members_csv(rows):
    output = StringIO()
    writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(EXPORT_HEADERS)
    for row in rows:
        writer.writerow(_export_record(row))
    csv_bytes = output.getvalue().encode("utf-8-sig")
    response = Response(csv_bytes, mimetype="text/csv")
    response.headers["Content-Disposition"] = 'attachment; filename="adherents.csv"'
    return response


def _render_members_xlsx(rows):
    import pandas as pd
    from openpyxl.styles import PatternFill

    records = [_export_record(row) for row in rows]
    df = pd.DataFrame(records, columns=EXPORT_HEADERS)
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Adhérents")
        ws = writer.sheets["Adhérents"]
        # Colore la cellule "Statut" (colonne 8) selon la couleur d'échéance.
        status_col = EXPORT_HEADERS.index("Statut") + 1
        fills = {
            "red": PatternFill("solid", fgColor="F8D7DA"),
            "orange": PatternFill("solid", fgColor="FFF3CD"),
            "green": PatternFill("solid", fgColor="D1E7DD"),
        }
        for i, row in enumerate(rows, start=2):  # ligne 1 = en-têtes
            fill = fills.get(row["color"])
            if fill:
                ws.cell(row=i, column=status_col).fill = fill

    response = Response(
        buf.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response.headers["Content-Disposition"] = 'attachment; filename="adherents.xlsx"'
    return response


@bp.route("/members/export")
@login_required
def members_export():
    fmt = (request.args.get("format") or "csv").strip().lower()
    if fmt == "xls":  # alias legacy -> xlsx
        fmt = "xlsx"
    rows = member_rows(request.args)
    if fmt == "xlsx":
        return _render_members_xlsx(rows)
    return _render_members_csv(rows)


@bp.route("/members.csv")
@login_required
def members_csv():
    """Compat : ancien lien d'export CSV."""
    args = request.args.to_dict()
    args["format"] = "csv"
    return redirect(url_for("entities.members_export", **args))
