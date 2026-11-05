"""Écritures : liste, fiche, saisie (formulaire de la SPA et îlot du rapprochement),
suppression."""
from datetime import date

from flask import g, jsonify, request, url_for
from flask_login import login_required

from app.extensions import db
from app.models import Account, BankTransaction, FiscalYear, Journal, JournalEntry
import json

from flask_login import current_user

from app.access import instance_admin_required
from app.models import EntryEvent
from app.models.journal_entry import SALE_LOCKED_MESSAGE, SOURCE_CANCELLATION, SOURCE_SALE
from app.services import projects, validation, vat_codes
from app.services.ledger import (
    MANAGED_SOURCES, VALIDATED_MESSAGE, LedgerError, delete_entries, entry_is_reconciled, post_validated_entry,
    period_locked, reversal_of, reverse, update_entry, validate_entry_payload,
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


def _analytic_targets():
    from app.services import analytic
    if not analytic.enabled():
        return []
    from app.services.analytic_allocation import targets_options
    return targets_options()


def _line_analytic(line):
    from app.services.analytic_allocation import line_target, target_label
    target = line_target(line)
    return target, target_label(target)


def entry_form_options(project_ids=()):
    """Exercices ouverts, journaux, projets et portée des comptes récents du formulaire de saisie."""
    fiscal_years = FiscalYear.query.filter_by(closed=False).order_by(FiscalYear.start_date.desc()).all()
    instance = getattr(g, "current_instance", None)
    return {
        "fiscalYears": [{"id": fy.id, "label": fy.label, "start_date": fy.start_date.isoformat(),
                         "end_date": fy.end_date.isoformat()} for fy in fiscal_years],
        "journals": [{"id": j.id, "code": j.code, "label": j.label}
                     for j in Journal.query.order_by(Journal.code).all()],
        "recentsScope": instance.slug if instance else "default",
        "projects": projects.options(project_ids),
        "analyticTargets": _analytic_targets(),                       # lot AG8.c : activités et clés (agricole)
        # Lot T2 : codes de TVA des lignes 445… (saisie manuelle).
        "vatCodes": [{"value": code, "label": f"{code} — {spec['label']}", "on": spec["on"], "rate_bp": spec["rate_bp"]}
                     for code, spec in vat_codes.codes().items()],
    }


def _link(entry):
    return {"id": entry.id, "reference": entry.reference} if entry is not None else None


def _locked(entry):
    """Date de verrouillage si l'écriture est dans la période verrouillée (lot F2), sinon None."""
    fy = entry.fiscal_year
    return fy.locked_until.isoformat() if fy.locked_until and entry.entry_date <= fy.locked_until else None


def serialize_entry(entry):
    reversal = reversal_of(entry)
    reverses = db.session.get(JournalEntry, entry.reverses_entry_id) if entry.reverses_entry_id else None
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
        "editable": not entry.fiscal_year.closed and not entry.is_validated and not _locked(entry)
        and entry.source not in (*MANAGED_SOURCES, SOURCE_SALE),
        "locked_until": _locked(entry),
        "managed": entry.source in MANAGED_SOURCES,
        "validated": entry.is_validated,
        "fiscal_year_closed": entry.fiscal_year.closed,
        "validation_number": entry.validation_number,
        "validated_at": entry.validated_at.isoformat() if entry.validated_at else None,
        "reversal": _link(reversal),
        "reverses": _link(reverses) if entry.source == SOURCE_CANCELLATION else None,
        "reversible": reversal is None and entry.source not in (*MANAGED_SOURCES, SOURCE_SALE, SOURCE_CANCELLATION),
        "url": url_for("entries.detail", entry_id=entry.id),
        "lines": [
            {"id": l.id, "account_id": l.account_id, "account_code": l.account.code,
             "account_label": l.account.label, "label": l.label or "",
             "debit_cents": l.debit_cents, "credit_cents": l.credit_cents,
             "project_id": l.project_id, "project": l.project.name if l.project else None,
             "analytic": _line_analytic(l)[0], "analytic_label": _line_analytic(l)[1],
             "service_start": l.service_start.isoformat() if l.service_start else None,
             "service_end": l.service_end.isoformat() if l.service_end else None,
             "vat_code": l.vat_code, "vat_label": vat_codes.label(l.vat_code) or None,
             "vat_base_cents": l.vat_base_cents,
             "reconciled": l.bank_transaction is not None}
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
    if entry.source == SOURCE_SALE:
        raise ApiError("conflict", SALE_LOCKED_MESSAGE, 409)
    if entry.is_validated:
        raise ApiError("entry_validated", VALIDATED_MESSAGE, 409)
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
    state = request.args.get("state")
    if state == "draft":
        query = query.filter(JournalEntry.validation_number.is_(None))
    elif state == "validated":
        query = query.filter(JournalEntry.validation_number.isnot(None))
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
                "total_debit_cents": e.total_debit, "is_balanced": e.is_balanced, "source": e.source,
                "validation_number": e.validation_number}
               for e in entries],
        total=total, page=page, per_page=per_page,
        meta={"fy_id": fy_id,
              "fiscal_years": [{"value": str(f.id), "label": f.label} for f in fiscal_years],
              "journals": [{"value": str(j.id), "label": f"{j.code} — {j.label}"}
                           for j in Journal.query.order_by(Journal.code)],
              "months": month_options_for_fy(fy) if fy else [],
              "drafts": validation.draft_counts(fy) if fy else None,
              "fiscal_year_open": bool(fy and not fy.closed),
              "locked_until": fy.locked_until.isoformat() if fy and fy.locked_until else None},
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
    entry_id = request.args.get("entry_id", type=int)
    used = [l.project_id for l in _get_entry(entry_id).lines if l.project_id] if entry_id else []
    options = entry_form_options(used)
    journals = Journal.query.order_by(Journal.code).all()
    bt_id = request.args.get("bt_id", type=int)
    if entry_id:
        entry = _get_entry(entry_id)
        if entry.fiscal_year.closed:
            raise ApiError("conflict", "Impossible de modifier une écriture d'un exercice clôturé.", 409)
        if entry.is_validated:
            raise ApiError("entry_validated", VALIDATED_MESSAGE, 409)
        if _locked(entry):
            exc = period_locked(entry.fiscal_year, entry.entry_date)
            raise ApiError(exc.code, str(exc), 409)
        if entry_is_reconciled(entry):
            raise ApiError("conflict", "Cette écriture est rapprochée à une transaction bancaire. "
                           "Annulez le rapprochement avant de la modifier.", 409)
        return jsonify(mode="edit", entry_id=entry.id, reference=entry.reference, options=options, initial={
            "fiscal_year_id": entry.fiscal_year_id, "journal_id": entry.journal_id,
            "entry_date": entry.entry_date.isoformat(), "description": entry.description or "",
            "lines": [{"account": _account_json(l.account), "label": l.label or "",
                       "debit_cents": l.debit_cents, "credit_cents": l.credit_cents,
                       "project_id": str(l.project_id) if l.project_id else None,
                       "analytic": _line_analytic(l)[0],
                       "vat_code": l.vat_code, "vat_base_cents": l.vat_base_cents} for l in entry.lines]})
    proposal_id = request.args.get("proposal_id", type=int)
    if proposal_id:
        # Lot AG9b.c : brouillon proposé par l'assistant ; l'utilisateur le relit et l'enregistre lui-même.
        from app.api.assistant import proposal_of_user
        proposal = proposal_of_user(proposal_id)
        if proposal.kind != "entry":
            raise ApiError("not_found", "Brouillon d'écriture introuvable.", 404)
        draft = json.loads(proposal.payload_json)
        journal = next((j for j in journals if j.code == draft.get("journal")), journals[0] if journals else None)
        fy = _default_fiscal_year(date.fromisoformat(draft["date"]))
        lines = []
        for line in draft.get("lines", []):
            account = Account.query.filter_by(code=line["account"]).first()
            if account is not None:
                lines.append({"account": _account_json(account), "label": line.get("label") or draft.get("label") or "",
                              "debit_cents": line.get("debit_cents", 0), "credit_cents": line.get("credit_cents", 0)})
        return jsonify(mode="create", options=options, proposal={"id": proposal.id, "status": proposal.status}, initial={
            "fiscal_year_id": fy.id if fy else None, "journal_id": journal.id if journal else None,
            "entry_date": draft["date"], "description": draft.get("label") or "", "lines": lines})
    if bt_id:
        bt = db.session.get(BankTransaction, bt_id)
        if bt is None:
            raise ApiError("not_found", "Transaction bancaire introuvable.", 404)
        if bt.reconciled:
            raise ApiError("conflict", "Cette transaction bancaire est déjà rapprochée.", 409)
        fy = _default_fiscal_year(bt.transaction_date)
        bq = next((j for j in journals if j.code == "BQ"), journals[0] if journals else None)
        amount, inflow = abs(bt.amount_cents), bt.amount_cents >= 0
        lines = [{"account": _account_json(bt.bank_account.account), "label": bt.label or "",
                  "debit_cents": amount if inflow else 0, "credit_cents": 0 if inflow else amount}]
        associate_id = request.args.get("associate_id", type=int)
        if associate_id:
            # Apport ou remboursement du compte courant d'un associé : contrepartie 455 préremplie.
            from app.models import Associate
            from app.services.associate_operations import bank_entry_lines
            associate = db.session.get(Associate, associate_id)
            if associate is None:
                raise ApiError("not_found", "Associé introuvable.", 404)
            lines = [{**line, "account": _account_json(line["account"])} for line in bank_entry_lines(bt, associate)]
        return jsonify(mode="create", options=options, initial={
            "fiscal_year_id": fy.id if fy else None, "journal_id": bq.id if bq else None,
            "entry_date": bt.transaction_date.isoformat(), "description": bt.label or "",
            "lines": lines},
            bank_transaction={"id": bt.id, "date": bt.transaction_date.isoformat(), "label": bt.label or "",
                              "amount_cents": bt.amount_cents,
                              "return_url": url_for("reconciliation.index", bank_account_id=bt.bank_account_id)})
    fy = _default_fiscal_year(date.today())
    return jsonify(mode="create", options=options, initial={
        "fiscal_year_id": fy.id if fy else None, "journal_id": journals[0].id if journals else None,
        "entry_date": date.today().isoformat(), "description": "", "lines": []})


# ------------------------------------------------------------------ validation (lot F1)


def _validation_error(exc):
    problems = getattr(exc, "problems", [])
    return ApiError("validation_refused", str(exc), 409, extra={"problems": problems})


@bp.route("/entries/validation", methods=["POST"])
@login_required
def entries_validation():
    """Valide une sélection (`{ids}`) ou tout jusqu'à une date (`{fiscal_year_id, until}`) : un lot."""
    data = json_body()
    try:
        if data.get("ids") is not None:
            ids = [i for i in data.get("ids") or [] if isinstance(i, int)]
            entries = JournalEntry.query.filter(JournalEntry.id.in_(ids)).all() if ids else []
            years = {e.fiscal_year_id for e in entries}
            if len(years) > 1:
                raise ApiError("validation_error", "Sélection sur plusieurs exercices : validez-les séparément.", 422)
            if not entries:
                raise ApiError("validation_error", "Aucune écriture sélectionnée.", 422)
            fy = entries[0].fiscal_year
            batch = validation.validate(fy, entries, "manual", current_user.id)
        else:
            fy = db.session.get(FiscalYear, data.get("fiscal_year_id")) if isinstance(data.get("fiscal_year_id"), int) else None
            if fy is None:
                raise ApiError("validation_error", "Exercice obligatoire.", 422, {"fiscal_year_id": "Exercice obligatoire."})
            try:
                until = date.fromisoformat(str(data.get("until") or ""))
            except ValueError:
                raise ApiError("validation_error", "Date invalide.", 422, {"until": "Date obligatoire (AAAA-MM-JJ)."}) from None
            batch = validation.validate_until(fy, until, current_user.id)
    except validation.ValidationError as exc:
        db.session.rollback()
        raise _validation_error(exc) from None
    db.session.commit()
    count = batch.entries if batch else 0
    message = f"{count} écriture(s) validée(s)." if count else "Aucune écriture en brouillard à valider."
    return jsonify(validated=count, notices=[notice(message, "success" if count else "info")])


@bp.route("/entries/<int:entry_id>/reverse", methods=["POST"])
@login_required
def entries_reverse(entry_id):
    """Contrepasse l'écriture : `{date?, reason}`."""
    entry = _get_entry(entry_id)
    data = json_body()
    on_date = None
    if data.get("date"):
        try:
            on_date = date.fromisoformat(str(data["date"]))
        except ValueError:
            raise ApiError("validation_error", "Date invalide.", 422, {"date": "Date invalide (AAAA-MM-JJ)."}) from None
    try:
        reversal = reverse(entry, on_date, data.get("reason"), current_user.id)
    except LedgerError as exc:
        raise ApiError("conflict", str(exc), 409) from None
    return jsonify(item=serialize_entry(reversal),
                   notices=[notice(f"Écriture {entry.reference} contrepassée par {reversal.reference}.")])


@bp.route("/entries/<int:entry_id>/history")
@login_required
def entries_history(entry_id):
    """Instantanés successifs de l'écriture (le plus ancien d'abord)."""
    from app.models import User
    events = EntryEvent.query.filter_by(entry_id=entry_id).order_by(EntryEvent.id).all()
    if not events:
        _get_entry(entry_id)
    users = {u.id: u.email for u in User.query.filter(User.id.in_({e.user_id for e in events if e.user_id}))}
    return jsonify(items=[{
        "id": e.id, "action": e.action, "at": e.at.isoformat(), "user": users.get(e.user_id),
        "origin": e.origin, "snapshot": json.loads(e.snapshot_json) if e.snapshot_json else None,
    } for e in events])


@bp.route("/fiscal-years/<int:fy_id>/validation-batches")
@login_required
def fiscal_year_validation_batches(fy_id):
    fy = db.session.get(FiscalYear, fy_id)
    if fy is None:
        raise ApiError("not_found", "Exercice introuvable.", 404)
    last = validation.last_batch(fy)
    return jsonify(items=[validation.batch_payload(b, last.id if last and not fy.is_final else None)
                          for b in validation.batches(fy)],
                   drafts=validation.draft_counts(fy))


@bp.route("/fiscal-years/<int:fy_id>/validation-batches/last/undo", methods=["POST"])
@instance_admin_required
def fiscal_year_validation_undo(fy_id):
    """Dévalide le dernier lot (administrateur, motif obligatoire)."""
    fy = db.session.get(FiscalYear, fy_id)
    if fy is None:
        raise ApiError("not_found", "Exercice introuvable.", 404)
    try:
        batch = validation.undo_last_batch(fy, json_body().get("reason"), current_user.id)
    except validation.ValidationError as exc:
        db.session.rollback()
        raise ApiError("conflict", str(exc), 409, {"reason": str(exc)} if "Motif" in str(exc) else None) from None
    db.session.commit()
    return jsonify(notices=[notice(f"Lot de validation annulé : {batch.entries} écriture(s) repassent en brouillard.")])
