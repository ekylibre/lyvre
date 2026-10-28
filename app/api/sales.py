"""Ventes (lot S1, claudedocs/design_ventes.md) : factures et avoirs de l'application — liste,
brouillons, émission (numéro, écriture VE, PDF Factur-X), avoir, PDF, envoi manuel par email ;
réglages de facturation (mentions, IBAN, conditions, logo, message d'envoi)."""
from contextlib import contextmanager
from datetime import date
from io import BytesIO

from flask import jsonify, request, send_file

from app.access import instance_admin_required
from app.extensions import db
from app.models import Account, BankAccount, BankTransaction, Entity, Lease, RentReceipt, Sale, SalePayment
from app.models.sale import OPERATION_TYPES, PAYMENT_METHODS, QUOTE_STATUS_LABELS, STATUS_LABELS
from app.services import (
    billing, catalog, external_config, projects, qonto_sales, sale_documents, sale_entry, sale_issue, sale_settlement,
    vat_codes,
)
from app.services.sale_entry import SaleError
from app.utils.list_filters import apply_month_filter, month_options_for_fy, parse_month

from . import ApiError, bp, get_or_404, invalid, json_body, notice, require_integration

KIND_LABELS = {"invoice": "Facture", "credit_note": "Avoir", "quote": "Devis"}
UNIT_OPTIONS = ["unité", "heure", "jour", "mois", "forfait", "kg", "m²"]


@contextmanager
def _errors():
    try:
        yield
    except SaleError as exc:
        db.session.rollback()
        if exc.status == 422:
            raise invalid(exc.message, exc.field) from None
        raise ApiError("conflict" if exc.status == 409 else "not_found", exc.message, status=exc.status) from None


def _iso(value):
    return value.isoformat() if value else None


def _money(cents):
    return f"{cents / 100:.2f}".replace(".", ",")


def _qty(milli):
    return sale_documents._qty(milli)


def _status(s: Sale) -> tuple[str, str]:
    if s.kind == "quote":
        status = sale_issue.quote_status(s)
        return status, QUOTE_STATUS_LABELS.get(status, status)
    return s.status, STATUS_LABELS.get(s.status, s.status)


def sale_row(s: Sale) -> dict:
    status, label = _status(s)
    return {"id": s.id, "kind": s.kind, "kind_label": KIND_LABELS.get(s.kind, s.kind), "status": status,
            "status_label": label, "number": s.number, "source": s.source, "validity_date": _iso(s.validity_date),
            "qonto_emit": s.qonto_emit, "qonto_status": s.qonto_status, "qonto_error": s.qonto_error,
            "client": {"id": s.entity_id, "name": s.entity.name}, "issue_date": _iso(s.issue_date),
            "due_date": _iso(s.due_date), "untaxed_cents": s.untaxed_cents, "tax_cents": s.tax_cents,
            "total_cents": s.total_cents, "paid_cents": s.paid_cents, "sent_at": _iso(s.sent_at),
            "due_cents": sale_settlement.due_cents(s), "reminder_count": s.reminder_count,
            "last_reminder_at": _iso(s.last_reminder_at),
            "overdue": s.kind == "invoice" and s.status in ("issued", "partially_paid") and bool(s.due_date)
            and s.due_date < date.today()}


def _line(l) -> dict:
    return {"id": l.id, "product_id": str(l.product_id or ""), "label": l.label, "description": l.description or "",
            "quantity": _qty(l.quantity_milli), "unit": l.unit or "", "unit_price": _money(l.unit_price_cents),
            "discount": catalog.format_rate(l.discount_bp).replace(" %", "") if l.discount_bp else "",
            "vat_rate": catalog.format_rate(l.vat_rate_bp).replace(" %", "") if l.vat_rate_bp else "0",
            "account_code": l.account.code if l.account else "", "project_id": str(l.project_id or ""),
            "nature": l.nature, "untaxed_cents": l.untaxed_cents, "vat_cents": l.vat_cents, "total_cents": l.total_cents}


def sale_detail(s: Sale) -> dict:
    credit_notes = Sale.query.filter_by(kind="credit_note", invoice_id=s.id).order_by(Sale.id).all() \
        if s.kind == "invoice" else []
    return {**sale_row(s), "client": {**s.client, "id": s.entity_id},
            "service_start": _iso(s.service_start), "service_end": _iso(s.service_end),
            "operation_type": s.operation_type, "purchase_order": s.purchase_order or "", "terms": s.terms or "",
            "header": s.header or "", "footer": s.footer or "", "vat_mode": s.vat_mode,
            "vat_regime": vat_codes.sale_regime(s), "vat_exemptions": sale_documents.exemption_mentions(s),
            "credit_reason": s.credit_reason, "lines": [_line(l) for l in s.lines],
            "vat_rows": sale_documents.vat_rows(s),
            "journal_entry": {"id": s.journal_entry_id, "reference": s.journal_entry.reference}
            if s.journal_entry_id and s.journal_entry else None,
            "invoice": {"id": s.invoice.id, "number": s.invoice.number} if s.kind == "credit_note" and s.invoice else None,
            "quote": ({"id": s.quote_id, "number": db.session.get(Sale, s.quote_id).number}
                      if s.quote_id and db.session.get(Sale, s.quote_id) else None),
            "invoices": [{"id": i.id, "number": i.number, "status": i.status, "total_cents": i.total_cents}
                         for i in sale_issue.quote_invoices(s)] if s.kind == "quote" else [],
            "credit_notes": [{"id": c.id, "number": c.number, "status": c.status, "total_cents": c.total_cents}
                             for c in credit_notes],
            "remaining_credit_cents": s.total_cents - sale_issue.credited_cents(s) if s.kind == "invoice" else 0,
            "issue_problems": sale_issue.issue_problems(s) if s.status == "draft" else [],
            "recipients": sale_issue.recipients_of(s), "emails": [
                {"sent_at": _iso(e.sent_at), "recipients": e.recipients, "subject": e.subject, "status": e.status,
                 "error": e.error, "purpose": e.purpose} for e in s.emails],
            "payments": [{"id": p.id, "amount_cents": p.amount_cents, "paid_on": _iso(p.paid_on), "origin": p.origin,
                          "method": PAYMENT_METHODS.get(p.method or "", ""), "vat_released_cents": p.vat_released_cents,
                          "account": p.bank_account.label if p.bank_account else None,
                          "transaction": {"id": p.bank_transaction_id, "label": p.bank_transaction.label}
                          if p.bank_transaction else None,
                          "journal_entry": {"id": p.journal_entry_id, "reference": p.journal_entry.reference}
                          if p.journal_entry else None} for p in s.payments],
            "pdf_url": f"/api/v1/sales/{s.id}/pdf",
            "lease": {"id": s.lease_id, "unit_label": db.session.get(Lease, s.lease_id).unit_label}
            if s.lease_id and db.session.get(Lease, s.lease_id) else None,
            "recurrence_id": s.recurrence_id,
            "rent_receipts": [{"id": r.id, "kind": r.kind, "label": "Quittance" if r.kind == "quittance" else "Reçu",
                               "paid_cents": r.paid_cents, "sent_at": _iso(r.sent_at), "pdf_url": f"/api/v1/rent-receipts/{r.id}/pdf"}
                              for r in RentReceipt.query.filter_by(sale_id=s.id).order_by(RentReceipt.id)]}


# ------------------------------------------------------------------ liste

@bp.route("/sales")
def sales_list():
    args = request.args
    kind = args.get("kind") if args.get("kind") in KIND_LABELS else None
    # Sans type : factures et avoirs ; les devis ont leur onglet (`kind=quote`).
    query = Sale.query.filter(Sale.kind == kind) if kind else Sale.query.filter(Sale.kind.in_(("invoice", "credit_note")))
    status = args.get("status")
    if kind == "quote" and status == "expired":
        query = query.filter(Sale.status == "issued", Sale.validity_date < date.today())
    elif kind == "quote" and status == "issued":
        query = query.filter(Sale.status == "issued", db.or_(Sale.validity_date.is_(None), Sale.validity_date >= date.today()))
    elif status in (QUOTE_STATUS_LABELS if kind == "quote" else STATUS_LABELS):
        query = query.filter(Sale.status == status)
    if args.get("entity_id", "").isdigit():
        query = query.filter(Sale.entity_id == int(args["entity_id"]))
    if args.get("overdue") == "1":
        query = query.filter(Sale.kind == "invoice", Sale.status.in_(("issued", "partially_paid")),
                             Sale.due_date < date.today())
    q = (args.get("q") or "").strip()
    if q:
        query = query.join(Entity, Entity.id == Sale.entity_id).filter(
            db.or_(Sale.number.ilike(f"%{q}%"), Entity.name.ilike(f"%{q}%")))
    query = apply_month_filter(query, Sale.issue_date, parse_month(args.get("month")))
    rows = query.order_by(Sale.status == "draft", Sale.issue_date.desc(), Sale.id.desc()).limit(500).all()
    issued = [s for s in rows if s.status != "draft" and s.kind != "quote"]
    return jsonify(items=[sale_row(s) for s in rows], meta={
        "statuses": [{"value": k, "label": v} for k, v in (QUOTE_STATUS_LABELS if kind == "quote" else STATUS_LABELS).items()],
        "clients": [{"value": str(e.id), "label": e.name} for e in
                    Entity.query.join(Sale, Sale.entity_id == Entity.id).distinct().order_by(Entity.name)],
        "totals": {"untaxed_cents": sum(s.untaxed_cents * (-1 if s.kind == "credit_note" else 1) for s in issued),
                   "total_cents": sum(s.total_cents * (-1 if s.kind == "credit_note" else 1) for s in issued)},
        "drafts": sum(1 for s in rows if s.status == "draft"), "months": month_options_for_fy(),
        "qonto": {**external_config.state("qonto", "sales"), "job": _job(qonto_sales.latest_job())},
        "smtp": _smtp_state()})


def _job(job):
    from .session import job_payload
    return job_payload(job) if job else None


def _require_channel(sales) -> None:
    """Pièces émises par Qonto : envoyées par Qonto (périmètre Ventes) ; les autres par SMTP."""
    if any(s.qonto_id for s in sales):
        require_integration("qonto", "sales")
    if any(not s.qonto_id for s in sales):
        require_integration("smtp")


def _smtp_state():
    from app.services import external_config
    return external_config.state("smtp")


@bp.route("/sales/form-options")
def sales_form_options():
    settings = billing.get()
    fy = sale_entry.fiscal_year_for(date.today())
    default_account = sale_entry.default_sale_account()
    return jsonify(
        clients=[{"value": str(e.id), "label": e.name, "vat_regime": e.vat_regime or "fr",
                  "vat_number": e.vat_number or ""} for e in Entity.query.order_by(Entity.name)],
        products=[{"value": str(p.id), "label": p.name, "account": p.sale_account.code if p.sale_account else "",
                   "rate": catalog.format_rate(p.vat_rate_bp).replace(" %", "") if p.vat_rate_bp is not None else "",
                   "price": "" if p.sale_price_cents is None else _money(p.sale_price_cents),
                   "unit": p.unit or "", "description": p.description or "", "nature": p.nature}
                  for p in catalog.sale_products()],
        sale_accounts=[{"value": a.code, "label": f"{a.code} — {a.label}"} for a in
                       Account.query.filter(Account.code.like("7%"), Account.is_header.is_(False)).order_by(Account.code)],
        default_account=default_account.code if default_account else "",
        projects=projects.options(), units=UNIT_OPTIONS,
        operation_types=[{"value": k, "label": v} for k, v in OPERATION_TYPES.items()],
        vat_regimes=[{"value": k, "label": v} for k, v in vat_codes.regime_labels().items()],
        vat_mode=sale_entry.vat_mode_for(date.today()), vat_liable=bool(fy and fy.vat_liable),
        qonto=external_config.scope_available("qonto", "sales"),
        payment_terms_days=settings.payment_terms_days)


# ------------------------------------------------------------------ brouillons

@bp.route("/sales", methods=["POST"])
def sales_create():
    """Brouillon de facture, ou de devis avec `kind: "quote"`."""
    data = json_body()
    kind = "quote" if data.get("kind") == "quote" else "invoice"
    with _errors():
        sale = sale_entry.create(data, kind=kind)
    return jsonify(item=sale_detail(sale), notices=[notice(
        "Brouillon de devis enregistré." if kind == "quote" else "Brouillon de facture enregistré.")]), 201


@bp.route("/sales/<int:sale_id>")
def sales_detail(sale_id):
    return jsonify(item=sale_detail(get_or_404(Sale, sale_id, "Pièce introuvable.")))


@bp.route("/sales/<int:sale_id>", methods=["PATCH"])
def sales_update(sale_id):
    sale = get_or_404(Sale, sale_id, "Pièce introuvable.")
    with _errors():
        sale_entry.update(sale, json_body())
    return jsonify(item=sale_detail(sale), notices=[notice("Brouillon enregistré.")])


@bp.route("/sales/<int:sale_id>", methods=["DELETE"])
def sales_delete(sale_id):
    sale = get_or_404(Sale, sale_id, "Pièce introuvable.")
    with _errors():
        sale_entry.delete(sale)
    return jsonify(notices=[notice("Brouillon supprimé.")])


# ------------------------------------------------------------------ émission, avoir

@bp.route("/sales/<int:sale_id>/issue", methods=["POST"])
def sales_issue(sale_id):
    sale = get_or_404(Sale, sale_id, "Pièce introuvable.")
    with _errors():
        sale_issue.issue(sale)
    messages = {"invoice": f"Facture {sale.number} émise et comptabilisée.",
                "credit_note": f"Avoir {sale.number} émis et comptabilisé.",
                "quote": f"Devis {sale.number} émis."}
    return jsonify(item=sale_detail(sale), notices=[notice(messages[sale.kind])])


@bp.route("/sales/<int:sale_id>/credit-note", methods=["POST"])
def sales_credit_note(sale_id):
    """`{reason, line_ids?}` : brouillon d'avoir sur toutes les lignes de la facture, ou celles choisies."""
    invoice = get_or_404(Sale, sale_id, "Pièce introuvable.")
    data = json_body()
    with _errors():
        note = sale_issue.credit_note(invoice, data.get("reason"), data.get("line_ids"))
    return jsonify(item=sale_detail(note), notices=[notice("Brouillon d'avoir créé : vérifiez-le puis émettez-le.")]), 201


# ------------------------------------------------------------------ PDF, envoi

@bp.route("/sales/<int:sale_id>/pdf")
def sales_pdf(sale_id):
    """PDF émis (conservé), ou aperçu d'un brouillon."""
    sale = get_or_404(Sale, sale_id, "Pièce introuvable.")
    path = sale_documents.pdf_file(sale)
    download = request.args.get("download") == "1"
    if path is None and sale.qonto_id and qonto_sales.available():
        from app.services.qonto_client import QontoError
        try:  # PDF Qonto produit en différé : récupéré à la première demande
            if qonto_sales.fetch_pdf(sale):
                db.session.commit()
                path = sale_documents.pdf_file(sale)
        except QontoError:
            db.session.rollback()
        if path is None:
            raise ApiError("conflict", "PDF pas encore disponible chez Qonto : réessayez dans un instant.", status=409)
    if path is not None:
        return send_file(path, mimetype="application/pdf", as_attachment=download,
                         download_name=sale_documents.filename(sale))
    if sale.status != "draft":
        raise ApiError("not_found", "PDF introuvable.", status=404)
    return send_file(BytesIO(sale_documents.render_pdf(sale)), mimetype="application/pdf", as_attachment=download,
                     download_name=sale_documents.filename(sale))


@bp.route("/sales/<int:sale_id>/send", methods=["POST"])
def sales_send_one(sale_id):
    """`{to: [...], cc: [...], subject, body}` : envoi d'une pièce émise, message modifiable."""
    sale = get_or_404(Sale, sale_id, "Pièce introuvable.")
    _require_channel([sale])
    data = json_body()
    with _errors():
        to = sale_issue.validate_emails(data.get("to"), "to")
        cc = sale_issue.validate_emails(data.get("cc"), "cc")
        if not to:
            raise SaleError("Indiquez au moins un destinataire.", "to")
        result = sale_issue.send([sale], to=to, cc=cc, subject=(data.get("subject") or "").strip() or None,
                                 body=(data.get("body") or "").strip() or None)
    if result["errors"]:
        raise ApiError("send_failed", "Envoi impossible : " + " ; ".join(result["errors"]), status=502)
    return jsonify(item=sale_detail(sale), notices=[notice(f"{KIND_LABELS.get(sale.kind)} {sale.number} envoyé{'e' if sale.kind == 'invoice' else ''}.")])


@bp.route("/sales/send", methods=["POST"])
def sales_send_many():
    """`{ids}` : envoi des pièces émises choisies à l'adresse de leur client, message par défaut."""
    ids = json_body().get("ids")
    if not isinstance(ids, list) or not ids or not all(isinstance(i, int) for i in ids):
        raise invalid("Choisissez les pièces à envoyer.", "ids")
    sales = Sale.query.filter(Sale.id.in_(ids)).order_by(Sale.number).all()
    _require_channel(sales)
    with _errors():
        result = sale_issue.send(sales)
    notices = [notice(f"{result['sent']} pièce(s) envoyée(s).", "success" if result["sent"] else "info")]
    notices += [notice(e, "warning") for e in result["errors"][:10]]
    return jsonify(result=result, notices=notices)


# ------------------------------------------------------------------ réglages de facturation

@bp.route("/billing-settings")
def billing_settings_get():
    return jsonify(item=billing.payload())


@bp.route("/billing-settings", methods=["PUT"])
@instance_admin_required
def billing_settings_save():
    with _errors():
        settings = billing.save(json_body())
    return jsonify(item=billing.payload(settings), notices=[notice("Réglages de facturation enregistrés.")])


@bp.route("/billing-settings/logo", methods=["POST"])
@instance_admin_required
def billing_logo_upload():
    with _errors():
        billing.save_logo(request.files.get("logo"))
    return jsonify(item=billing.payload(), notices=[notice("Logo enregistré.")])


@bp.route("/billing-settings/logo", methods=["DELETE"])
@instance_admin_required
def billing_logo_delete():
    billing.delete_logo()
    return jsonify(item=billing.payload(), notices=[notice("Logo retiré.")])


# ------------------------------------------------------------------ encaissements

def _txn(t: BankTransaction, sale: Sale) -> dict:
    return {"id": t.id, "date": _iso(t.transaction_date), "label": t.label or t.counterparty or "",
            "amount_cents": t.amount_cents, "account": t.bank_account.label, "same_client": t.entity_id == sale.entity_id,
            "exact": t.amount_cents == sale_settlement.due_cents(sale), "rule": t.journal_line_id is not None}


@bp.route("/sales/<int:sale_id>/payment-options")
def sales_payment_options(sale_id):
    """Restant dû, transactions bancaires candidates, comptes de banque et caisses (saisie)."""
    sale = get_or_404(Sale, sale_id, "Pièce introuvable.")
    return jsonify(due_cents=sale_settlement.due_cents(sale),
                   candidates=[_txn(t, sale) for t in sale_settlement.candidates(sale)],
                   accounts=[{"value": str(b.id), "label": b.label, "kind": b.kind}
                             for b in BankAccount.query.order_by(BankAccount.kind, BankAccount.label)],
                   methods=[{"value": k, "label": v} for k, v in PAYMENT_METHODS.items()])


@bp.route("/sales/match", methods=["POST"])
def sales_match():
    """`{bank_transaction_id, allocations: [{sale_id, amount_cents}]}` : la transaction encaisse les
    factures (un seul client, somme = montant de la transaction)."""
    data = json_body()
    if not isinstance(data.get("bank_transaction_id"), int):
        raise invalid("Choisissez la transaction bancaire.", "bank_transaction_id")
    txn = get_or_404(BankTransaction, data["bank_transaction_id"], "Transaction introuvable.")
    rows = data.get("allocations")
    if not isinstance(rows, list) or not rows:
        raise invalid("Choisissez les factures encaissées.", "allocations")
    allocations = []
    for row in rows:
        sale = db.session.get(Sale, row.get("sale_id")) if isinstance(row.get("sale_id"), int) else None
        amount = row.get("amount_cents")
        if sale is None or not isinstance(amount, int):
            raise invalid("Encaissement invalide.", "allocations")
        allocations.append((sale, amount))
    with _errors():
        entry = sale_settlement.match(txn, allocations)
    return jsonify(items=[sale_detail(sale) for sale, _ in allocations],
                   notices=[notice(f"Encaissement rapproché ({len(allocations)} facture(s))."),
                            *(notice(w, "warning") for w in getattr(entry, "qonto_warnings", []))])


@bp.route("/sales/<int:sale_id>/payments", methods=["POST"])
def sales_manual_payment(sale_id):
    """`{amount, paid_on, bank_account_id, method}` : encaissement saisi (chèque, espèces…)."""
    sale = get_or_404(Sale, sale_id, "Pièce introuvable.")
    data = json_body()
    ba = db.session.get(BankAccount, int(data["bank_account_id"])) if str(data.get("bank_account_id") or "").isdigit() else None
    if ba is None:
        raise invalid("Choisissez le compte encaissé.", "bank_account_id")
    method = data.get("method") if data.get("method") in PAYMENT_METHODS else "other"
    with _errors():
        amount = sale_entry.parse_decimal(data.get("amount"), "Montant", "amount", minimum=0)
        paid_on = sale_entry.parse_date(data.get("paid_on"), "Date", "paid_on") or date.today()
        if amount is None:
            raise SaleError("Montant obligatoire.", "amount")
        entry = sale_settlement.record_manual(sale, int(amount * 100), paid_on, ba, method)
    return jsonify(item=sale_detail(sale), notices=[notice("Encaissement enregistré et comptabilisé."),
                                                    *(notice(w, "warning") for w in getattr(entry, "qonto_warnings", []))])


@bp.route("/sale-payments/<int:payment_id>", methods=["DELETE"])
def sale_payments_delete(payment_id):
    payment = get_or_404(SalePayment, payment_id, "Encaissement introuvable.")
    sale = payment.sale
    with _errors():
        sale_settlement.unlink(payment)
    db.session.refresh(sale)
    return jsonify(item=sale_detail(sale), notices=[notice("Encaissement défait : son écriture est supprimée.")])


@bp.route("/sales/auto-match", methods=["POST"])
def sales_auto_match():
    result = sale_settlement.auto_match()
    notices = [notice(f"{result['matched']} facture(s) encaissée(s) automatiquement.",
                      "success" if result["matched"] else "info")]
    notices += [notice(e, "warning") for e in result["errors"][:10]]
    return jsonify(result=result, notices=notices)


# ------------------------------------------------------------------ relances

@bp.route("/sales/remind", methods=["POST"])
def sales_remind_many():
    """`{ids}` : relance par email des factures choisies (non soldées), message de relance par défaut."""
    ids = json_body().get("ids")
    if not isinstance(ids, list) or not ids or not all(isinstance(i, int) for i in ids):
        raise invalid("Choisissez les factures à relancer.", "ids")
    sales = Sale.query.filter(Sale.id.in_(ids), Sale.kind == "invoice").order_by(Sale.number).all()
    _require_channel(sales)
    with _errors():
        result = sale_issue.send(sales, purpose="reminder")
    notices = [notice(f"{result['sent']} relance(s) envoyée(s).", "success" if result["sent"] else "info")]
    notices += [notice(e, "warning") for e in result["errors"][:10]]
    return jsonify(result=result, notices=notices)


@bp.route("/sales/<int:sale_id>/remind", methods=["POST"])
def sales_remind_one(sale_id):
    """`{to, cc, subject, body}` : relance d'une facture, message modifiable."""
    sale = get_or_404(Sale, sale_id, "Pièce introuvable.")
    _require_channel([sale])
    data = json_body()
    with _errors():
        if sale.kind != "invoice" or not sale_settlement.due_cents(sale):
            raise SaleError("Rien à relancer : facture soldée, annulée ou brouillon.", status=409)
        to = sale_issue.validate_emails(data.get("to"), "to")
        cc = sale_issue.validate_emails(data.get("cc"), "cc")
        if not to:
            raise SaleError("Indiquez au moins un destinataire.", "to")
        result = sale_issue.send([sale], to=to, cc=cc, subject=(data.get("subject") or "").strip() or None,
                                 body=(data.get("body") or "").strip() or None, purpose="reminder")
    if result["errors"]:
        raise ApiError("send_failed", "Relance impossible : " + " ; ".join(result["errors"]), status=502)
    return jsonify(item=sale_detail(sale), notices=[notice(f"Relance de la facture {sale.number} envoyée.")])


# ------------------------------------------------------------------ devis

@bp.route("/sales/<int:sale_id>/quote-status", methods=["POST"])
def sales_quote_status(sale_id):
    """`{status: accepted | refused | issued}` : réponse du client à un devis émis."""
    quote = get_or_404(Sale, sale_id, "Pièce introuvable.")
    with _errors():
        sale_issue.set_quote_status(quote, json_body().get("status"))
    return jsonify(item=sale_detail(quote), notices=[notice(f"Devis {quote.number} : {QUOTE_STATUS_LABELS[quote.status].lower()}.")])


@bp.route("/sales/<int:sale_id>/to-invoice", methods=["POST"])
def sales_to_invoice(sale_id):
    """Brouillon de facture reprenant le devis."""
    quote = get_or_404(Sale, sale_id, "Pièce introuvable.")
    with _errors():
        invoice = sale_issue.to_invoice(quote)
    return jsonify(item=sale_detail(invoice), notices=[notice(
        f"Brouillon de facture créé depuis le devis {quote.number} : vérifiez-le puis émettez-le.")]), 201


# ------------------------------------------------------------------ Qonto (lot S4)

@bp.route("/sales/sync", methods=["POST"])
def sales_qonto_sync():
    """Synchronisation des ventes Qonto en arrière-plan (lecture seule côté Qonto)."""
    require_integration("qonto", "sales")
    from flask import current_app
    from .session import job_payload
    return jsonify(job=job_payload(qonto_sales.start_sync(current_app._get_current_object())))
