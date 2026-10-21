import io
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.services import purchase_settlement
from flask_login import login_required
from app.extensions import db
from app.models import BankAccount, OdooImportLine
from app.services.ofx_importer import import_ofx
from app.services.odoo_importer import import_odoo_csv
from app.utils.list_filters import (
    parse_sort, parse_month, apply_date_sort, apply_month_filter,
    sort_and_filter_context,
)

bp = Blueprint("imports", __name__, url_prefix="/imports")


@bp.route("/ofx", methods=["GET", "POST"])
@login_required
def ofx():
    bank_accounts = BankAccount.query.order_by(BankAccount.label).all()
    result = None

    if request.method == "POST":
        bank_account_id = request.form.get("bank_account_id", type=int)
        file = request.files.get("ofx_file")

        if not bank_account_id:
            flash("Veuillez sélectionner un compte bancaire.", "danger")
        elif not file or not file.filename:
            flash("Veuillez choisir un fichier OFX.", "danger")
        else:
            try:
                result = import_ofx(file.stream, bank_account_id)
                flash(
                    f"{result['imported']} transaction(s) importée(s), "
                    f"{result['duplicates']} doublon(s) ignoré(s).",
                    "success" if not result["errors"] else "warning",
                )
                if result["imported"]:
                    # Factures d'achat saisies en attente : débit unique de même montant → réglées.
                    matching = purchase_settlement.auto_match()
                    if matching["matched"]:
                        flash(f"{matching['matched']} facture(s) d'achat rattachée(s) à leur paiement, "
                              f"{matching['settled']} règlement(s) passé(s).", "success")
                    for error in matching["errors"]:
                        flash(error, "danger")
            except Exception as e:
                flash(f"Erreur lors de l'import OFX : {e}", "danger")

    return render_template("imports/ofx.html", bank_accounts=bank_accounts, result=result)


@bp.route("/odoo", methods=["GET", "POST"])
@login_required
def odoo():
    batches = (
        db.session.query(OdooImportLine.import_batch, db.func.count(OdooImportLine.id))
        .group_by(OdooImportLine.import_batch)
        .order_by(OdooImportLine.import_batch.desc())
        .all()
    )
    result = None

    if request.method == "POST":
        file = request.files.get("csv_file")
        batch_name = request.form.get("batch_name", "").strip()
        if not batch_name:
            batch_name = f"odoo-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        if not file or not file.filename:
            flash("Veuillez choisir un fichier CSV.", "danger")
        else:
            try:
                result = import_odoo_csv(file.stream, batch_name)
                flash(
                    f"{result['imported']} ligne(s) importée(s) dans le lot « {batch_name} ».",
                    "success" if not result["errors"] else "warning",
                )
            except Exception as e:
                flash(f"Erreur lors de l'import Odoo : {e}", "danger")

    return render_template("imports/odoo.html", batches=batches, result=result)


@bp.route("/odoo/batch/<batch_name>")
@login_required
def odoo_batch(batch_name):
    sort = parse_sort(request.args.get("sort"))
    month_arg = request.args.get("month")
    month_tuple = parse_month(month_arg)

    query = OdooImportLine.query.filter_by(import_batch=batch_name)
    query = apply_month_filter(query, OdooImportLine.invoice_date, month_tuple)
    query = apply_date_sort(query, OdooImportLine.invoice_date, sort)
    lines = query.order_by(OdooImportLine.id).all()
    return render_template(
        "imports/odoo_batch.html",
        lines=lines,
        batch_name=batch_name,
        **sort_and_filter_context(sort, month_arg),
    )
