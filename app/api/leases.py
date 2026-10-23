"""Ventes, lot S5 : factures récurrentes (échéancier, préparation des échéances, émission en lot),
baux (dépôt de garantie), quittances et reçus de loyer."""
from contextlib import contextmanager
from datetime import date

from flask import jsonify, send_file

from app.extensions import db
from app.models import Account, BankAccount, Lease, Recurrence, RentReceipt, Sale
from app.models.sale import FREQUENCIES
from app.services import external_config, leases, recurrence, sale_entry
from app.services.sale_entry import SaleError

from . import ApiError, bp, get_or_404, invalid, json_body, notice, require_integration
from .sales import _line, _require_channel, sale_row


@contextmanager
def _errors():
    try:
        yield
    except SaleError as exc:
        db.session.rollback()
        if exc.status == 422:
            raise invalid(exc.message, exc.field) from None
        raise ApiError("conflict", exc.message, status=exc.status) from None


def _iso(value):
    return value.isoformat() if value else None


def recurrence_payload(rec: Recurrence, detail: bool = False) -> dict:
    t = rec.template
    lease = Lease.query.filter_by(recurrence_id=rec.id).first()
    row = {"id": rec.id, "label": rec.label, "frequency": rec.frequency, "frequency_label": FREQUENCIES[rec.frequency],
           "due_day": rec.due_day, "start_date": _iso(rec.start_date), "end_date": _iso(rec.end_date),
           "in_advance": rec.in_advance, "next_date": _iso(rec.next_date), "qonto_emit": rec.qonto_emit,
           "active": rec.active, "client": {"id": t.entity_id, "name": t.entity.name}, "total_cents": t.total_cents,
           "lease": {"id": lease.id, "unit_label": lease.unit_label} if lease else None,
           "invoices": Sale.query.filter_by(recurrence_id=rec.id).count()}
    if detail:
        row.update(operation_type=t.operation_type, terms=t.terms or "", header=t.header or "", footer=t.footer or "",
                   purchase_order=t.purchase_order or "", lines=[_line(l) for l in t.lines])
    return row


# ------------------------------------------------------------------ récurrences

@bp.route("/recurrences")
def recurrences_list():
    rows = Recurrence.query.order_by(Recurrence.active.desc(), Recurrence.next_date).all()
    return jsonify(items=[recurrence_payload(r) for r in rows],
                   meta={"frequencies": [{"value": k, "label": v} for k, v in FREQUENCIES.items()]})


@bp.route("/recurrences", methods=["POST"])
def recurrences_create():
    with _errors():
        rec = recurrence.create(json_body())
    return jsonify(item=recurrence_payload(rec, True), notices=[notice("Facture récurrente enregistrée.")]), 201


@bp.route("/recurrences/<int:rec_id>")
def recurrences_detail(rec_id):
    return jsonify(item=recurrence_payload(get_or_404(Recurrence, rec_id, "Récurrence introuvable."), True))


@bp.route("/recurrences/<int:rec_id>", methods=["PATCH"])
def recurrences_update(rec_id):
    rec = get_or_404(Recurrence, rec_id, "Récurrence introuvable.")
    if Lease.query.filter_by(recurrence_id=rec.id).first() and "lines" in json_body():
        raise ApiError("conflict", "Loyer d'un bail : modifiez le bail.", status=409)
    with _errors():
        recurrence.update(rec, json_body())
    return jsonify(item=recurrence_payload(rec, True), notices=[notice("Facture récurrente enregistrée.")])


@bp.route("/recurrences/<int:rec_id>", methods=["DELETE"])
def recurrences_delete(rec_id):
    rec = get_or_404(Recurrence, rec_id, "Récurrence introuvable.")
    if Lease.query.filter_by(recurrence_id=rec.id).first():
        raise ApiError("conflict", "Loyer d'un bail : arrêtez le bail plutôt.", status=409)
    recurrence.delete(rec)
    return jsonify(notices=[notice("Facture récurrente supprimée (les factures déjà faites restent).")])


@bp.route("/sales/due")
def sales_due():
    """Prépare les échéances arrivées (brouillons), puis liste les brouillons récurrents à émettre."""
    prepared = recurrence.prepare_due()
    return jsonify(items=[sale_row(s) for s in recurrence.due_drafts()], meta={"prepared": prepared})


@bp.route("/sales/issue-batch", methods=["POST"])
def sales_issue_batch():
    """`{ids, send}` : émission en lot (et envoi par email si `send`)."""
    data = json_body()
    ids = data.get("ids")
    if not isinstance(ids, list) or not ids or not all(isinstance(i, int) for i in ids):
        raise invalid("Choisissez les factures à émettre.", "ids")
    if data.get("send"):
        _require_channel(Sale.query.filter(Sale.id.in_(ids)).all())
    result = recurrence.issue_batch(ids, send=bool(data.get("send")))
    notices = [notice(f"{result['issued']} facture(s) émise(s)" + (f", {result['sent']} envoyée(s)" if data.get("send") else "") + ".",
                      "success" if result["issued"] else "info")]
    notices += [notice(e, "warning") for e in result["errors"][:10]]
    return jsonify(result=result, notices=notices)


# ------------------------------------------------------------------ baux

def lease_payload(lease: Lease, detail: bool = False) -> dict:
    rec = lease.recurrence
    row = {"id": lease.id, "unit_label": lease.unit_label, "tenant": {"id": lease.entity_id, "name": lease.entity.name},
           "address_line1": lease.address_line1 or "", "address_line2": lease.address_line2 or "",
           "postal_code": lease.postal_code or "", "city": lease.city or "", "start_date": _iso(lease.start_date),
           "end_date": _iso(lease.end_date), "rent_cents": lease.rent_cents, "charges_cents": lease.charges_cents,
           "due_day": lease.due_day, "deposit_cents": lease.deposit_cents, "active": lease.active,
           "deposit_entry": {"id": lease.deposit_entry_id, "reference": lease.deposit_entry.reference}
           if lease.deposit_entry else None,
           "rent_account_code": lease.rent_account.code if lease.rent_account else "",
           "charges_account_code": lease.charges_account.code if lease.charges_account else "",
           "next_date": _iso(rec.next_date) if rec else None, "frequency": rec.frequency if rec else "monthly",
           "in_advance": rec.in_advance if rec else True, "qonto_emit": rec.qonto_emit if rec else False,
           "notes": lease.notes or ""}
    if detail:
        sales = Sale.query.filter_by(lease_id=lease.id).order_by(Sale.issue_date.desc(), Sale.id.desc()).all()
        row["invoices"] = [{**sale_row(s), "service_start": _iso(s.service_start), "service_end": _iso(s.service_end)}
                           for s in sales]
        row["receipts"] = [receipt_payload(r) for r in
                           RentReceipt.query.filter_by(lease_id=lease.id).order_by(RentReceipt.id.desc())]
    return row


def receipt_payload(r: RentReceipt) -> dict:
    return {"id": r.id, "kind": r.kind, "label": "Quittance" if r.kind == "quittance" else "Reçu",
            "period_start": _iso(r.period_start), "period_end": _iso(r.period_end), "paid_cents": r.paid_cents,
            "sale": {"id": r.sale_id, "number": r.sale.number}, "sent_at": _iso(r.sent_at),
            "pdf_url": f"/api/v1/rent-receipts/{r.id}/pdf"}


@bp.route("/leases")
def leases_list():
    rows = Lease.query.order_by(Lease.active.desc(), Lease.unit_label).all()
    return jsonify(items=[lease_payload(l) for l in rows], meta={
        "tenants": leases.tenant_options(),
        "accounts": [{"value": a.code, "label": f"{a.code} — {a.label}"} for a in
                     Account.query.filter(Account.code.like("7%"), Account.is_header.is_(False)).order_by(Account.code)],
        "bank_accounts": [{"value": str(b.id), "label": b.label} for b in BankAccount.query.order_by(BankAccount.label)],
        "qonto": external_config.scope_available("qonto", "sales")})


@bp.route("/leases", methods=["POST"])
def leases_create():
    with _errors():
        lease = leases.create(json_body())
    return jsonify(item=lease_payload(lease, True), notices=[notice(
        f"Bail enregistré : avis d'échéance préparés à partir du {lease.recurrence.next_date:%d/%m/%Y}.")]), 201


@bp.route("/leases/<int:lease_id>")
def leases_detail(lease_id):
    return jsonify(item=lease_payload(get_or_404(Lease, lease_id, "Bail introuvable."), True))


@bp.route("/leases/<int:lease_id>", methods=["PATCH"])
def leases_update(lease_id):
    lease = get_or_404(Lease, lease_id, "Bail introuvable.")
    with _errors():
        leases.update(lease, json_body())
    return jsonify(item=lease_payload(lease, True), notices=[notice("Bail enregistré.")])


@bp.route("/leases/<int:lease_id>/deposit", methods=["POST"])
def leases_deposit(lease_id):
    """`{paid_on, bank_account_id}` : encaissement du dépôt de garantie (165)."""
    lease = get_or_404(Lease, lease_id, "Bail introuvable.")
    data = json_body()
    ba = db.session.get(BankAccount, int(data["bank_account_id"])) if str(data.get("bank_account_id") or "").isdigit() else None
    if ba is None:
        raise invalid("Choisissez le compte encaissé.", "bank_account_id")
    with _errors():
        leases.deposit(lease, sale_entry.parse_date(data.get("paid_on"), "Date", "paid_on") or date.today(), ba)
    return jsonify(item=lease_payload(lease, True), notices=[notice("Dépôt de garantie encaissé et comptabilisé (165).")])


# ------------------------------------------------------------------ quittances

@bp.route("/sales/<int:sale_id>/rent-receipt", methods=["POST"])
def sales_rent_receipt(sale_id):
    """Quittance (période soldée) ou reçu (paiement partiel) de la facture de loyer."""
    sale = get_or_404(Sale, sale_id, "Pièce introuvable.")
    with _errors():
        row = leases.receipt(sale)
    return jsonify(item=receipt_payload(row), notices=[notice(f"{receipt_payload(row)['label']} prête.")])


@bp.route("/rent-receipts/<int:receipt_id>/pdf")
def rent_receipts_pdf(receipt_id):
    row = get_or_404(RentReceipt, receipt_id, "Quittance introuvable.")
    path = leases.receipt_file(row)
    if path is None:
        raise ApiError("not_found", "PDF introuvable.", status=404)
    return send_file(path, mimetype="application/pdf", download_name=path.name)


@bp.route("/rent-receipts/<int:receipt_id>/send", methods=["POST"])
def rent_receipts_send(receipt_id):
    """`{to}` : envoi de la quittance au locataire (SMTP)."""
    row = get_or_404(RentReceipt, receipt_id, "Quittance introuvable.")
    require_integration("smtp")
    from app.services import sale_issue
    with _errors():
        to = sale_issue.validate_emails(json_body().get("to") or [row.lease.entity.email], "to")
        leases.send_receipt(row, to)
    return jsonify(item=receipt_payload(row), notices=[notice("Quittance envoyée.")])
