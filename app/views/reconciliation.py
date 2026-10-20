from flask import Blueprint, render_template, request
from flask_login import login_required

from app.models import BankAccount, Journal
from app.utils.list_filters import month_options_for_fy
from app.views.entries import api_base_url, entry_form_options

bp = Blueprint("reconciliation", __name__, url_prefix="/reconciliation")


@bp.route("/")
@login_required
def index():
    """Espace de rapprochement (îlot React ReconcileWorkspace, actions via /api/v1)."""
    bank_accounts = BankAccount.query.order_by(BankAccount.label).all()
    selected_id = request.args.get("bank_account_id", type=int)
    if selected_id not in {ba.id for ba in bank_accounts}:
        selected_id = bank_accounts[0].id if bank_accounts else None

    options = entry_form_options()
    bq = Journal.query.filter_by(code="BQ").first()
    props = {
        "bankAccounts": [
            {"id": ba.id, "label": ba.label,
             "account": {"id": ba.account.id, "code": ba.account.code, "label": ba.account.label}}
            for ba in bank_accounts
        ],
        "bankAccountId": selected_id,
        "month": request.args.get("month") or "",
        "monthOptions": month_options_for_fy(),
        "urls": {"api": api_base_url(), "page": request.path},
        "entryForm": {
            "fiscalYears": options["fiscalYears"],
            "journals": options["journals"],
            "defaultJournalId": bq.id if bq else None,
            "recentsScope": options["recentsScope"],
        },
    }
    return render_template("reconciliation/index.html", props=props, has_accounts=bool(bank_accounts))
