"""Factures d'achat : liste et synchronisation Qonto, lecture d'une pièce et saisie, fiche
(lignes, comptabilisation, règlements, envoi à Qonto), suppression, règlements à remplacer,
fournisseurs à valider. Les pièces restent servies par Flask (`purchases.attachment`,
`purchases.staged`). Les champs de saisie gardent les noms et le format texte du formulaire
(montants « 39,99 ») : ils passent par purchase_entry.validate_header."""
from flask import current_app, jsonify, request, url_for

from app.access import current_role, instance_admin_required
from app.extensions import db
from app.models import Account, Associate, Entity, Project, Purchase, PurchasePayment
from app.models.instance_membership import ROLE_ACCOUNTANT
from app.models.purchase import PURCHASE_SOURCES
from app.services import (
    associate_operations, associates, attachments, catalog, counterparties, external_config, projects,
    purchase_entry, purchase_posting,
    purchase_settlement, purchase_sync,
)
from app.services.attachments import AttachmentError
from app.services.ledger import LedgerError
from app.services.purchase_posting import STATE_LABELS, purchase_state
from app.services.purchase_sync import STATUS_LABELS
from app.utils.list_filters import apply_date_sort, apply_month_filter, month_options_for_fy, parse_month, parse_sort

from . import ApiError, bp, get_or_404, invalid, json_body, notice, require_integration
from .session import job_payload

KEY_FIELDS = ("entity_id", "new_name", "supplier_name", "supplier_vat", "supplier_siret", "supplier_iban",
              "invoice_number", "issue_date", "due_date", "is_credit_note", "total", "untaxed", "tax")
ROW_FIELDS = ("product_id", "account_code", "label", "untaxed", "vat_rate", "vat", "project_id")


def _iso(value):
    return value.isoformat() if value else None


def _kind(p):
    return "Avoir" if p.is_credit_note else "Facture"


def _state(p):
    st = purchase_state(p)
    return {"code": st.code, "label": st.label, "reasons": list(st.reasons)}


def purchase_row(p: Purchase, state=None) -> dict:
    return {
        "id": p.id, "source": p.source, "invoice_number": p.invoice_number, "issue_date": _iso(p.issue_date),
        "due_date": _iso(p.due_date), "is_credit_note": p.is_credit_note, "is_einvoice": p.is_einvoice,
        "is_hidden": p.is_hidden, "total_cents": p.total_cents,
        "supplier": ({"id": p.entity.id, "name": p.entity.name} if p.entity else None),
        "supplier_name": p.supplier_name, "qonto_status": p.qonto_status,
        "qonto_status_label": STATUS_LABELS.get(p.qonto_status, p.qonto_status) if p.qonto_status else None,
        "review_reason": p.review_reason, "has_attachment": bool(p.attachment_path),
        "qonto_upload_status": p.qonto_upload_status, "qonto_upload_error": p.qonto_upload_error,
        "in_qonto": bool(p.qonto_id),
        "state": state or _state(p), "journal_entry_id": p.journal_entry_id,
    }


def _rows(data):
    rows = data.get("rows") or []
    if not isinstance(rows, list):
        raise invalid("Lignes invalides.")
    return [{key: "" if r.get(key) is None else str(r.get(key)) for key in ROW_FIELDS} for r in rows if isinstance(r, dict)]


def _values(data):
    values = {key: "" if data.get(key) in (None, False) else str(data.get(key)) for key in KEY_FIELDS}
    values["is_credit_note"] = "1" if data.get("is_credit_note") else ""
    return values


def _form_payload(form: purchase_entry.EntryForm) -> dict:
    return {"values": form.values, "checks": sorted(form.checks), "rows": form.rows,
            "warnings": form.warnings, "source": form.source}


def _charge_accounts():
    return [{"value": a.code, "label": f"{a.code} — {a.label}"} for a in
            Account.query.filter(Account.code.like("6%"), Account.is_header.is_(False)).order_by(Account.code)]


def _products():
    return [{"value": str(p.id), "label": p.name, "account": p.purchase_account.code if p.purchase_account else "",
             "rate": catalog.format_rate(p.vat_rate_bp).replace(" %", "")} for p in catalog.purchase_products()]


def _qonto():
    return {**external_config.state("qonto", "purchases"), "upload": purchase_entry.qonto_upload_available()}


# ------------------------------------------------------------------ liste


@bp.route("/purchases")
def purchases_list():
    args = request.args
    query = Purchase.query
    if args.get("hidden") != "1":
        query = query.filter(Purchase.is_hidden.is_(False))
    if args.get("source") in PURCHASE_SOURCES:
        query = query.filter(Purchase.source == args["source"])
    if args.get("status"):
        query = query.filter(Purchase.qonto_status == args["status"])
    entity_id = args.get("entity_id", type=int)
    if entity_id:
        query = query.filter(Purchase.entity_id == entity_id)
    if args.get("unpaid") == "1":
        # Non réglée : ni payée selon Qonto, ni règlement comptabilisé dans l'application.
        settled = db.session.query(PurchasePayment.purchase_id).filter(PurchasePayment.journal_entry_id.isnot(None))
        query = query.filter(db.or_(Purchase.qonto_status.is_(None), Purchase.qonto_status != "paid"),
                             Purchase.id.notin_(settled))
    if args.get("no_supplier") == "1":
        query = query.filter(Purchase.entity_id.is_(None))
    q = (args.get("q") or "").strip()
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(db.or_(db.func.lower(Purchase.invoice_number).like(like),
                                    db.func.lower(Purchase.supplier_name).like(like)))
    query = apply_month_filter(query, Purchase.issue_date, parse_month(args.get("month")))
    query = apply_date_sort(query, Purchase.issue_date, parse_sort(args.get("sort")))
    purchases = query.order_by(Purchase.id.desc()).limit(500).all()
    states = {p.id: _state(p) for p in purchases}
    state = args.get("state")
    if state in STATE_LABELS:
        purchases = [p for p in purchases if states[p.id]["code"] == state]
    cursor = purchase_sync.cursor_row()
    job = purchase_sync.latest_job()
    return jsonify(items=[purchase_row(p, states[p.id]) for p in purchases], meta={
        "counters": {
            "to_complete": purchase_posting.count_to_complete(),
            "to_review": Purchase.query.filter(Purchase.review_reason.isnot(None)).count(),
            "to_replace": sum(r.replaceable for r in purchase_settlement.to_replace()),
            "supplier_proposals": counterparties.count_invoice_proposals(),
            "hidden": Purchase.query.filter(Purchase.is_hidden.is_(True)).count(),
            "without_supplier": Purchase.query.filter(Purchase.entity_id.is_(None), Purchase.is_hidden.is_(False)).count(),
            "ready": len(purchase_posting.ready_purchases()),
        },
        "suppliers": [{"value": str(e.id), "label": e.name} for e in
                      Entity.query.join(Purchase, Purchase.entity_id == Entity.id).distinct().order_by(Entity.name)],
        "states": [{"value": k, "label": v} for k, v in STATE_LABELS.items() if k != "hidden"],
        "statuses": [{"value": k, "label": v} for k, v in STATUS_LABELS.items() if k != "to_pay"],
        "months": month_options_for_fy(),
        "sync": {"from": _iso(purchase_sync.sync_from_date()), "synced_at": _iso(cursor.synced_at) if cursor else None,
                 "job": job_payload(job) if job else None},
        "qonto": _qonto(),
    })


@bp.route("/purchases/sync", methods=["POST"])
def purchases_sync():
    require_integration("qonto", "purchases")
    return jsonify(job=job_payload(purchase_sync.start_sync(current_app._get_current_object())))


@bp.route("/purchases/sync-from", methods=["PATCH"])
@instance_admin_required
def purchases_sync_from():
    from datetime import date
    try:
        sync_from = date.fromisoformat(str(json_body().get("sync_from") or ""))
    except ValueError:
        raise invalid("Date de début invalide.", "sync_from") from None
    purchase_sync.set_sync_from(sync_from)
    return jsonify(notices=[notice(f"Factures Qonto synchronisées à partir du {sync_from.strftime('%d/%m/%Y')}.")])


@bp.route("/purchases/post-ready", methods=["POST"])
def purchases_post_ready():
    outcome = purchase_posting.post_ready(purchase_posting.ready_purchases())
    return jsonify(notices=[notice(f"{outcome['posted']} facture(s) comptabilisée(s).")]
                   + [notice(e, "danger") for e in outcome["errors"][:10]])


# ------------------------------------------------------------------ fiche


def _payment(pay: PurchasePayment) -> dict:
    t = pay.bank_transaction
    if pay.origin == "associate":
        entry = pay.journal_entry
        return {
            "id": pay.id, "origin": "associate", "status": "settled" if entry else "other_entry",
            "status_label": "Réglée" if entry else "Écriture supprimée", "qonto_transaction_id": None,
            "transaction": None,
            "associate": {"id": pay.associate_id, "name": pay.associate.name},
            "date": entry.entry_date.isoformat() if entry else None, "amount_cents": pay.purchase.total_cents,
            "entry": ({"reference": entry.reference, "url": url_for("entries.detail", entry_id=entry.id)}
                      if entry else None),
        }
    if t is None:
        status, label = "to_import", "À importer"
    elif pay.journal_entry:
        status, label = "settled", "Réglée"
    elif t.is_reversed:
        status, label = "reversed", "Annulée par la banque"
    elif t.reconciled:
        status, label = "other_entry", "Passée par une autre écriture"
    else:
        status, label = "pending", "En attente de comptabilisation"
    return {
        "id": pay.id, "origin": pay.origin, "status": status, "status_label": label,
        "qonto_transaction_id": pay.qonto_transaction_id,
        "transaction": ({"id": t.id, "date": t.transaction_date.isoformat(), "label": t.label or "",
                         "amount_cents": t.amount_cents, "bank_account": t.bank_account.label,
                         "bank_account_id": t.bank_account_id} if t else None),
        "entry": ({"reference": pay.journal_entry.reference,
                   "url": url_for("entries.detail", entry_id=pay.journal_entry.id)} if pay.journal_entry else None),
    }


def _associate_payment(p: Purchase) -> dict | None:
    """Règlement par un associé possible ? (module « Associés » actif seulement)."""
    if not associates.enabled():
        return None
    return {"blocker": associate_operations.payment_blocker(p),
            "associates": [{"value": str(a.id), "label": a.name}
                           for a in Associate.query.join(Entity).order_by(Entity.name)]}


def purchase_detail(p: Purchase) -> dict:
    fy = purchase_posting.fiscal_year_for(p.issue_date)
    awaiting = purchase_settlement.awaiting_payment(p)
    window = purchase_settlement.match_window(p) if p.issue_date else None
    entry = p.journal_entry
    return {
        "item": {**purchase_row(p), "payment_date": _iso(p.payment_date), "untaxed_cents": p.untaxed_cents,
                 "tax_cents": p.tax_cents, "supplier_vat": p.supplier_vat, "supplier_siret": p.supplier_siret,
                 "supplier_iban": p.supplier_iban,
                 "supplier_account_code": p.entity.account_code if p.entity else None,
                 "attachment": ({"name": p.attachment_name, "size": p.attachment_size, "mime": p.attachment_mime,
                                 "url": url_for("purchases.attachment", purchase_id=p.id)} if p.attachment_path else None),
                 "entry": ({"reference": entry.reference, "date": entry.entry_date.isoformat(),
                            "url": url_for("entries.detail", entry_id=entry.id)} if entry else None)},
        "fiscal_year": {"label": fy.label, "vat_liable": fy.vat_liable} if fy else None,
        "lines": purchase_entry.line_rows(p.lines),
        "lines_view": [{"product": l.product.name if l.product else None,
                        "account": l.account.code if l.account else None, "label": l.label or "",
                        "untaxed_cents": l.untaxed_cents, "vat_rate": catalog.format_rate(l.vat_rate_bp) or None,
                        "vat_cents": l.vat_cents, "total_cents": l.total_cents,
                        "project": db.session.get(Project, l.project_id).name if l.project_id else None}
                       for l in p.lines],
        "payments": [_payment(pay) for pay in p.payments],
        "awaiting_payment": awaiting,
        "suggestions": [{"id": t.id, "date": t.transaction_date.isoformat(), "bank_account": t.bank_account.label,
                         "label": t.label or "", "amount_cents": t.amount_cents, "rule": t.reconciled}
                        for t in (purchase_settlement.match_candidates(p) if awaiting else [])],
        "match_window": [window[0].isoformat(), window[1].isoformat()] if window else None,
        "can_send": purchase_entry.can_send_to_qonto(p),
        "associate_payment": _associate_payment(p),
        "meta": {"products": _products(), "charge_accounts": _charge_accounts(), "qonto": _qonto(),
                 "projects": projects.options([l.project_id for l in p.lines if l.project_id])},
    }


@bp.route("/purchases/<int:purchase_id>")
def purchases_detail(purchase_id):
    return jsonify(purchase_detail(get_or_404(Purchase, purchase_id, "Facture introuvable.")))


@bp.route("/purchases/<int:purchase_id>/lines", methods=["PUT"])
def purchases_save_lines(purchase_id):
    p = get_or_404(Purchase, purchase_id, "Facture introuvable.")
    try:
        outcome = purchase_posting.save_lines(p, _rows(json_body()))
    except LedgerError as exc:
        db.session.rollback()
        raise invalid(str(exc)) from None
    message = "Lignes enregistrées, facture comptabilisée." if outcome["posted"] else "Lignes enregistrées."
    return jsonify(notices=[notice(message)] + [notice(e, "danger") for e in outcome["errors"]])


@bp.route("/purchases/<int:purchase_id>/post", methods=["POST"])
def purchases_post(purchase_id):
    p = get_or_404(Purchase, purchase_id, "Facture introuvable.")
    outcome = purchase_posting.post_ready([p])
    if not outcome["posted"]:
        raise invalid(" ".join(outcome["errors"]) or " ".join(purchase_state(p).reasons) or "Facture non prête.")
    return jsonify(notices=[notice(f"{_kind(p)} comptabilisé{'' if p.is_credit_note else 'e'}.")]
                   + [notice(e, "danger") for e in outcome["errors"]])


@bp.route("/purchases/<int:purchase_id>/unpost", methods=["POST"])
def purchases_unpost(purchase_id):
    p = get_or_404(Purchase, purchase_id, "Facture introuvable.")
    try:
        purchase_posting.unpost(p)
    except LedgerError as exc:
        db.session.rollback()
        raise ApiError("conflict", str(exc), status=409) from None
    return jsonify(notices=[notice("Comptabilisation annulée : l'écriture d'achat est supprimée.")])


@bp.route("/purchases/<int:purchase_id>", methods=["DELETE"])
def purchases_delete(purchase_id):
    p = get_or_404(Purchase, purchase_id, "Facture introuvable.")
    label = f"{_kind(p)} {p.invoice_number or 'sans numéro'}"
    try:
        reference = purchase_posting.delete(p)
    except LedgerError as exc:
        db.session.rollback()
        raise ApiError("conflict", f"{label} : {exc}", status=409) from None
    return jsonify(notices=[notice(f"{label} supprimée" + (f", ainsi que son écriture {reference}." if reference else "."))])


@bp.route("/purchases/<int:purchase_id>/payments", methods=["POST"])
def purchases_link_payment(purchase_id):
    p = get_or_404(Purchase, purchase_id, "Facture introuvable.")
    try:
        outcome = purchase_settlement.link_manual(p, json_body().get("bank_transaction_id"))
    except LedgerError as exc:
        db.session.rollback()
        raise invalid(str(exc)) from None
    notices = [notice(e, "danger") for e in outcome["errors"]]
    if outcome["settled"]:
        notices.insert(0, notice("Règlement passé et rapproché."))
    elif not outcome["errors"]:
        notices.insert(0, notice("Paiement rattaché : la transaction est déjà passée par une règle, remplacez son "
                                 "écriture (Règlements à remplacer).", "warning"))
    return jsonify(notices=notices)


@bp.route("/purchases/<int:purchase_id>/payments/<int:payment_id>", methods=["DELETE"])
def purchases_unlink_payment(purchase_id, payment_id):
    payment = PurchasePayment.query.filter_by(id=payment_id, purchase_id=purchase_id).first()
    if payment is None:
        raise ApiError("not_found", "Règlement introuvable.", status=404)
    if payment.origin == "associate":
        try:
            associate_operations.unpay_purchase(payment)
        except associate_operations.OperationError as exc:
            raise ApiError("conflict", str(exc), status=409) from None
        return jsonify(notices=[notice("Règlement par l'associé défait : son écriture est supprimée.")])
    try:
        purchase_settlement.unlink(payment)
    except LedgerError as exc:
        db.session.rollback()
        raise ApiError("conflict", str(exc), status=409) from None
    return jsonify(notices=[notice("Règlement défait : l'écriture est supprimée et la transaction n'est plus rapprochée.")])


def _upload_notice(p, sent):
    if sent:
        return notice("Facture déposée dans Qonto.")
    return notice(f"Envoi à Qonto en échec : {p.qonto_upload_error} — utilisez « Renvoyer à Qonto ».", "danger")


@bp.route("/purchases/<int:purchase_id>/qonto", methods=["POST"])
def purchases_send_to_qonto(purchase_id):
    """Dépose la pièce dans Qonto (écriture côté Qonto, sur action explicite seulement)."""
    p = get_or_404(Purchase, purchase_id, "Facture introuvable.")
    require_integration("qonto", "purchases")
    if not purchase_entry.can_send_to_qonto(p):
        raise ApiError("conflict", "Cette facture ne peut pas être envoyée à Qonto (pièce absente ou déjà envoyée).",
                       status=409)
    return jsonify(notices=[_upload_notice(p, purchase_entry.send_to_qonto(p))])


# ------------------------------------------------------------------ saisie


@bp.route("/purchases/form-options")
def purchases_form_options():
    if current_role() != ROLE_ACCOUNTANT:  # lecture seule : rien n'est créé
        catalog.ensure_default_purchase_product()  # la ligne proposée par défaut figure dans la liste
    return jsonify(entities=[{"value": str(e.id), "label": e.name} for e in Entity.query.order_by(Entity.name)],
                   products=_products(), charge_accounts=_charge_accounts(), qonto=_qonto(),
                   projects=projects.options())


def _stage():
    try:
        token = attachments.stage(request.files.get("invoice_file"))
    except AttachmentError as exc:
        raise invalid(str(exc), "invoice_file") from None
    _, meta = attachments.staged(token)
    return token, meta


@bp.route("/purchases/read", methods=["POST"])
def purchases_read():
    """Dépose la pièce (PDF, JPEG, PNG ≤ 10 Mo) et la lit : formulaire prérempli."""
    token, meta = _stage()
    form = purchase_entry.form_from_extraction(purchase_entry.read_staged(token))
    db.session.commit()  # produit « Achats divers » créé au besoin pour les lignes proposées
    return jsonify(token=token, preview={"url": url_for("purchases.staged", token=token), "mime": meta["mime"]},
                   form=_form_payload(form))


@bp.route("/purchases/stage", methods=["POST"])
def purchases_stage():
    """Dépose une pièce sans la lire (remplacement de la pièce d'une facture saisie)."""
    token, meta = _stage()
    return jsonify(token=token, preview={"url": url_for("purchases.staged", token=token), "mime": meta["mime"]})


def _validated(data, exclude_id=None):
    values = _values(data)
    clean, errors = purchase_entry.validate_header(values)
    token = data.get("token") or None
    if token:
        try:
            attachments.staged(str(token))
        except AttachmentError as exc:
            errors.append(str(exc))
    if errors:
        raise ApiError("validation_error", " ".join(errors), status=422, fields={"form": errors})
    if not data.get("confirm_duplicate"):
        entity = purchase_entry.chosen_supplier(clean)
        dups = purchase_entry.duplicates(entity.id if entity else None, clean["invoice_number"], clean["issue_date"],
                                         clean["total_cents"], supplier_name=clean["new_name"] or clean["supplier_name"],
                                         exclude_id=exclude_id)
        if dups:
            body = {"error": {"code": "duplicate", "message": "Doublon possible.", "duplicates": [{
                "id": d.id, "label": f"{_kind(d)} {d.invoice_number or 'sans numéro'}", "issue_date": _iso(d.issue_date),
                "total_cents": d.total_cents} for d in dups]}}
            raise _Duplicate(body)
    return clean, token


class _Duplicate(Exception):
    def __init__(self, body):
        super().__init__("duplicate")
        self.body = body


@bp.errorhandler(_Duplicate)
def _duplicate(exc):
    return jsonify(exc.body), 409


def _posted_notices(p, outcome, verb):
    feminine = "" if p.is_credit_note else "e"
    message = f"{_kind(p)} {verb}{feminine}" + (f" et comptabilisé{feminine}." if outcome["posted"] else ".")
    return [notice(message)] + [notice(e, "danger") for e in outcome["errors"]]


@bp.route("/purchases", methods=["POST"])
def purchases_create():
    data = json_body()
    clean, token = _validated(data)
    try:
        p, outcome = purchase_entry.create(clean, _rows(data), token)
    except (LedgerError, AttachmentError) as exc:
        db.session.rollback()
        raise invalid(str(exc)) from None
    notices = _posted_notices(p, outcome, "enregistré")
    paid_by = data.get("paid_by_associate")
    if isinstance(paid_by, dict) and paid_by.get("associate_id") and associates.enabled():
        # Réglée par un associé dès la saisie : seulement si la facture a pu être comptabilisée.
        try:
            associate_operations.pay_purchase(p, paid_by.get("associate_id"), paid_by.get("paid_on"))
            notices.append(notice("Réglée par le compte courant de l'associé."))
        except associate_operations.OperationError as exc:
            notices.append(notice(f"Règlement par l'associé non passé : {exc}", "warning"))
    if data.get("send_to_qonto") and token and purchase_entry.qonto_upload_available():
        notices.append(_upload_notice(p, purchase_entry.send_to_qonto(p)))
    return jsonify(item={"id": p.id, "url": url_for("purchases.detail", purchase_id=p.id)}, notices=notices), 201


@bp.route("/purchases/<int:purchase_id>/associate-payment", methods=["POST"])
def purchases_pay_by_associate(purchase_id):
    """Facture réglée par le compte courant d'un associé (module « Associés »)."""
    if not associates.enabled():
        raise ApiError("feature_disabled", "Module Associés désactivé pour cette instance.", status=404)
    p = get_or_404(Purchase, purchase_id, "Facture introuvable.")
    data = json_body()
    try:
        associate_operations.pay_purchase(p, data.get("associate_id"), data.get("paid_on"))
    except associate_operations.OperationError as exc:
        raise invalid(str(exc), exc.field) from None
    return jsonify(notices=[notice("Facture réglée par le compte courant de l'associé.")])


@bp.route("/purchases/<int:purchase_id>/header")
def purchases_header(purchase_id):
    """En-tête d'une facture saisie non comptabilisée, pour sa modification."""
    p = get_or_404(Purchase, purchase_id, "Facture introuvable.")
    if p.source != "manual" or p.journal_entry_id is not None:
        raise ApiError("conflict", "Seule une facture saisie et non comptabilisée se modifie.", status=409)
    return jsonify(values=purchase_entry.header_values(p), can_replace_attachment=p.qonto_upload_status != "sent",
                   preview=({"url": url_for("purchases.attachment", purchase_id=p.id), "mime": p.attachment_mime}
                            if p.attachment_path else None))


@bp.route("/purchases/<int:purchase_id>", methods=["PATCH"])
def purchases_update(purchase_id):
    p = get_or_404(Purchase, purchase_id, "Facture introuvable.")
    if p.source != "manual" or p.journal_entry_id is not None:
        raise ApiError("conflict", "Seule une facture saisie et non comptabilisée se modifie.", status=409)
    data = json_body()
    clean, token = _validated(data, exclude_id=p.id)
    try:
        outcome = purchase_entry.update(p, clean, token)
    except (LedgerError, AttachmentError) as exc:
        db.session.rollback()
        raise invalid(str(exc)) from None
    return jsonify(notices=_posted_notices(p, outcome, "modifié"))


# ------------------------------------------------------------------ règlements et fournisseurs


@bp.route("/purchases/settlements")
def purchases_settlements():
    def row(r):
        return {"transaction": {"id": r.transaction.id, "date": r.transaction.transaction_date.isoformat(),
                                "label": r.transaction.label or "", "amount_cents": r.transaction.amount_cents},
                "entry": {"reference": r.entry.reference, "url": url_for("entries.detail", entry_id=r.entry.id),
                          "charge_accounts": [l.account.code for l in r.entry.lines if l.account.code.startswith("6")]},
                "purchases": [{"id": p.id, "label": p.invoice_number or "sans numéro",
                               "url": url_for("purchases.detail", purchase_id=p.id)} for p in r.purchases]}
    rows = purchase_settlement.to_replace()
    return jsonify(replaceable=[row(r) for r in rows if r.replaceable], manual=[row(r) for r in rows if not r.replaceable])


@bp.route("/purchases/settlements/replace", methods=["POST"])
def purchases_replace_settlements():
    ids = json_body().get("transaction_ids")
    if not isinstance(ids, list) or not ids:
        raise invalid("Aucune transaction sélectionnée.")
    outcome = purchase_settlement.replace_many([int(i) for i in ids])
    notices = []
    if outcome["counters"]["ok"]:
        notices.append(notice(f"{outcome['counters']['ok']} écriture(s) de règle remplacée(s) par un règlement fournisseur."))
    notices += [notice(f"Transaction {r['id']} : {r['message']}", "danger") for r in outcome["results"] if r["status"] == "error"]
    return jsonify(notices=notices)


@bp.route("/purchases/suppliers")
def purchases_suppliers():
    return jsonify(items=[{"key": p.key, "label": p.label, "count": p.count, "total_cents": p.total_cents,
                           "first_date": _iso(p.first_date), "last_date": _iso(p.last_date),
                           "vat_number": p.vat_number, "iban": p.iban,
                           "suggestions": [{"value": str(e.id), "label": e.name} for e in p.suggestions]}
                          for p in counterparties.invoice_proposals()],
                   meta={"entities": [{"value": str(e.id), "label": e.name} for e in Entity.query.order_by(Entity.name)]})


@bp.route("/purchases/suppliers", methods=["POST"])
def purchases_suppliers_decide():
    """`{action: create|link|ignore, key, label, name?, entity_id?}` : factures et transactions du nom."""
    data = json_body()
    action, key, label = data.get("action"), str(data.get("key") or ""), str(data.get("label") or "")
    if not key:
        raise invalid("Fournisseur manquant.")
    try:
        if action == "ignore":
            counterparties.ignore(key, label)
            return jsonify(notices=[notice(f"« {label} » ne sera plus proposé.")])
        if action == "link":
            entity, n_txn, n_inv = counterparties.accept(key, entity_id=data.get("entity_id") and int(data["entity_id"]))
        elif action == "create":
            entity, n_txn, n_inv = counterparties.accept(key, create_name=data.get("name"))
        else:
            raise invalid("Action inconnue.", "action")
    except ValueError as exc:
        raise invalid(str(exc)) from None
    return jsonify(notices=[notice(f"« {entity.name} » : {n_inv} facture(s) et {n_txn} transaction(s) rattachée(s).")])
