"""Écritures : liste, fiche, saisie (formulaire de la SPA et îlot du rapprochement),
suppression."""
from datetime import date

from flask import g, jsonify, request, url_for
from flask_login import login_required

from app.extensions import db
from app.models import BankTransaction, FiscalYear, Journal, JournalEntry
from app.services.ledger import (
    MANAGED_SOURCES, LedgerError, delete_entries, entry_is_reconciled, post_validated_entry, update_entry,
    validate_entry_payload,
)
from app.utils.list_filters import (
    apply_date_sort, apply_month_filter, month_options_for_fy, parse_month, parse_sort,
)

from . import ApiError, bp, json_body, notice

PER_PAGE_MAX = 200
MANAGED_MESSAGE = "Écriture gérée par l'assistant de clôture : modifiez-la depuis l'assistant."


def api_base_url():
    """Base de l'API (/api/v1), déduite d'une de ses routes."""
    return url_for("api.session_info").rsplit("/", 1)[0]


def entry_form_options():
    """Exercices ouverts, journaux et portée des comptes récents du formulaire de saisie."""
    fiscal_years = FiscalYear.query.filter_by(closed=False).order_by(FiscalYear.start_date.desc()).all()
    instance = getattr(g, "current_instance", None)
    return {
        "fiscalYears": [{"id": fy.id, "label": fy.label, "start_date": fy.start_date.isoformat(),
                         "end_date": fy.end_date.isoformat()} for fy in fiscal_years],
        "journals": [{"id": j.id, "code": j.code, "label": j.label}
                     for j in Journal.query.order_by(Journal.code).all()],
        "recentsScope": instance.slug if instance else "default",
    }


def serialize_entry(entry):
    return {
        "id": entry.id,
        "reference": entry.reference,
        "fiscal_year_id": entry.fiscal_year_id,
        "fiscal_year": entry.fiscal_year.label,
        "journal_id": entry.journal_id,
        "journal": f"{entry.journal.code} — {entry.journal.label}",
        "entry_date": entry.entry_date.isoformat(),
        "description": entry.description or "",
        "source": entry.source,
        "source_ref": entry.source_ref,
        "is_balanced": entry.is_balanced,
        "total_debit_cents": entry.total_debit,
        "total_credit_cents": entry.total_credit,
        "reconciled": entry_is_reconciled(entry),
        "editable": not entry.fiscal_year.closed and entry.source not in MANAGED_SOURCES,
        "managed": entry.source in MANAGED_SOURCES,
        "url": url_for("entries.detail", entry_id=entry.id),
        "lines": [
            {"id": l.id, "account_id": l.account_id, "account_code": l.account.code,
             "account_label": l.account.label, "label": l.label or "",
             "debit_cents": l.debit_cents, "credit_cents": l.credit_cents}
            for l in entry.lines
        ],
    }


def _validated(data):
    clean, errors = validate_entry_payload(data)
    if errors:
        raise ApiError("validation_error", "L'écriture contient des erreurs.", 422, errors)
    return clean


def _get_entry(entry_id):
    entry = db.session.get(JournalEntry, entry_id)
    if entry is None:
        raise ApiError("not_found", "Écriture introuvable.", 404)
    return entry


@bp.route("/entries/validate", methods=["POST"])
@login_required
def entries_validate():
    """Dry run: errors by field, nothing is saved."""
    _clean, errors = validate_entry_payload(json_body())
    return jsonify(errors=errors)


@bp.route("/entries", methods=["POST"])
@login_required
def entries_create():
    data = json_body()
    clean = _validated(data)

    bank_transaction = None
    bt_id = data.get("bank_transaction_id")
    if bt_id is not None:
        bank_transaction = db.session.get(BankTransaction, bt_id) if isinstance(bt_id, int) else None
        if bank_transaction is None:
            raise ApiError("not_found", "Transaction bancaire introuvable.", 404)

    try:
        entry = post_validated_entry(clean, bank_transaction=bank_transaction)
    except LedgerError as e:
        raise ApiError("conflict", str(e), 409)

    body = serialize_entry(entry)
    return jsonify(body), 201, {"Location": body["url"]}


@bp.route("/entries/<int:entry_id>")
@login_required
def entries_get(entry_id):
    return jsonify(serialize_entry(_get_entry(entry_id)))


@bp.route("/entries/<int:entry_id>", methods=["PUT"])
@login_required
def entries_update(entry_id):
    entry = _get_entry(entry_id)
    if entry.source in MANAGED_SOURCES:
        raise ApiError("conflict", MANAGED_MESSAGE, 409)
    clean = _validated(json_body())
    try:
        update_entry(entry, clean)
    except LedgerError as e:
        raise ApiError("conflict", str(e), 409)
    return jsonify(serialize_entry(entry))


@bp.route("/entries")
@login_required
def entries_list():
    """Écritures filtrées (exercice ouvert le plus récent par défaut), paginées côté serveur."""
    fiscal_years = FiscalYear.query.order_by(FiscalYear.start_date.desc()).all()
    fy_id = request.args.get("fy_id", type=int)
    if fy_id is None:
        active = next((fy for fy in fiscal_years if not fy.closed), None)
        fy_id = active.id if active else None
    query = JournalEntry.query
    if fy_id:
        query = query.filter_by(fiscal_year_id=fy_id)
    journal_id = request.args.get("journal_id", type=int)
    if journal_id:
        query = query.filter_by(journal_id=journal_id)
    q = (request.args.get("q") or "").strip()
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(JournalEntry.reference.ilike(like), JournalEntry.description.ilike(like)))
    query = apply_month_filter(query, JournalEntry.entry_date, parse_month(request.args.get("month")))
    query = apply_date_sort(query, JournalEntry.entry_date, parse_sort(request.args.get("sort")))
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = min(max(request.args.get("per_page", 50, type=int), 1), PER_PAGE_MAX)
    total = query.count()
    entries = query.order_by(JournalEntry.id.desc()).offset((page - 1) * per_page).limit(per_page).all()
    fy = next((f for f in fiscal_years if f.id == fy_id), None)
    return jsonify(
        items=[{"id": e.id, "reference": e.reference, "entry_date": e.entry_date.isoformat(),
                "journal": e.journal.code, "description": e.description or "",
                "total_debit_cents": e.total_debit, "is_balanced": e.is_balanced, "source": e.source}
               for e in entries],
        total=total, page=page, per_page=per_page,
        meta={"fy_id": fy_id,
              "fiscal_years": [{"value": str(f.id), "label": f.label} for f in fiscal_years],
              "journals": [{"value": str(j.id), "label": f"{j.code} — {j.label}"}
                           for j in Journal.query.order_by(Journal.code)],
              "months": month_options_for_fy(fy) if fy else []},
    )


@bp.route("/entries/<int:entry_id>", methods=["DELETE"])
@login_required
def entries_delete(entry_id):
    """Supprime l'écriture (rapprochements défaits) ; refusé dans un exercice clôturé."""
    _get_entry(entry_id)
    (result,) = delete_entries([entry_id])
    if result["status"] != "ok":
        raise ApiError("conflict", f"Impossible de supprimer l'écriture : {result['message']}", 409)
    return jsonify(notices=[notice(f"Écriture {result['reference']} supprimée.")])


def _account_json(account):
    return {"id": account.id, "code": account.code, "label": account.label}


def _default_fiscal_year(on_date):
    open_years = FiscalYear.query.filter_by(closed=False).order_by(FiscalYear.start_date.desc()).all()
    return next((fy for fy in open_years if fy.start_date <= on_date <= fy.end_date),
                open_years[0] if open_years else None)


@bp.route("/entries/form")
@login_required
def entries_form():
    """Préparation du formulaire de saisie : options, valeurs initiales.

    `?entry_id=` : modification (refusée si exercice clôturé ou écriture rapprochée) ;
    `?bt_id=` : création depuis une transaction bancaire (ligne banque préremplie) ;
    sinon : nouvelle écriture du jour.
    """
    options = entry_form_options()
    journals = Journal.query.order_by(Journal.code).all()
    entry_id = request.args.get("entry_id", type=int)
    bt_id = request.args.get("bt_id", type=int)
    if entry_id:
        entry = _get_entry(entry_id)
        if entry.fiscal_year.closed:
            raise ApiError("conflict", "Impossible de modifier une écriture d'un exercice clôturé.", 409)
        if entry_is_reconciled(entry):
            raise ApiError("conflict", "Cette écriture est rapprochée à une transaction bancaire. "
                           "Annulez le rapprochement avant de la modifier.", 409)
        return jsonify(mode="edit", entry_id=entry.id, reference=entry.reference, options=options, initial={
            "fiscal_year_id": entry.fiscal_year_id, "journal_id": entry.journal_id,
            "entry_date": entry.entry_date.isoformat(), "description": entry.description or "",
            "lines": [{"account": _account_json(l.account), "label": l.label or "",
                       "debit_cents": l.debit_cents, "credit_cents": l.credit_cents} for l in entry.lines]})
    if bt_id:
        bt = db.session.get(BankTransaction, bt_id)
        if bt is None:
            raise ApiError("not_found", "Transaction bancaire introuvable.", 404)
        if bt.reconciled:
            raise ApiError("conflict", "Cette transaction bancaire est déjà rapprochée.", 409)
        fy = _default_fiscal_year(bt.transaction_date)
        bq = next((j for j in journals if j.code == "BQ"), journals[0] if journals else None)
        amount, inflow = abs(bt.amount_cents), bt.amount_cents >= 0
        return jsonify(mode="create", options=options, initial={
            "fiscal_year_id": fy.id if fy else None, "journal_id": bq.id if bq else None,
            "entry_date": bt.transaction_date.isoformat(), "description": bt.label or "",
            "lines": [{"account": _account_json(bt.bank_account.account), "label": bt.label or "",
                       "debit_cents": amount if inflow else 0, "credit_cents": 0 if inflow else amount}]},
            bank_transaction={"id": bt.id, "date": bt.transaction_date.isoformat(), "label": bt.label or "",
                              "amount_cents": bt.amount_cents,
                              "return_url": url_for("reconciliation.index", bank_account_id=bt.bank_account_id)})
    fy = _default_fiscal_year(date.today())
    return jsonify(mode="create", options=options, initial={
        "fiscal_year_id": fy.id if fy else None, "journal_id": journals[0].id if journals else None,
        "entry_date": date.today().isoformat(), "description": "", "lines": []})
