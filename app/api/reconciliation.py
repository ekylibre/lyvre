"""Bank reconciliation for the ReconcileWorkspace island.

Every write returns ``results`` (one per item), ``counters`` and ``undo``: the
request that reverts the successful part of the operation (the client replays
it for "Annuler" / Ctrl+Z; nothing is stored on the server).
"""
from flask import jsonify, request, url_for
from flask_login import login_required
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import BankAccount, BankTransaction, Entity, JournalEntry, JournalLine, PurchasePayment
from app.services import rule_entries
from app.services.ledger import LedgerError, delete_entries, reversed_entry_ids
from app.services.reconciler import (
    auto_reconcile, reconcile_many, suggest_matches_scored, unreconcile_many,
)
from app.services.rules_engine import apply_rules
from app.utils.list_filters import apply_date_sort, apply_month_filter, parse_month, parse_sort

from . import ApiError, bp, get_or_404, invalid, json_body, notice


def _bank_account(bank_account_id):
    ba = db.session.get(BankAccount, bank_account_id) if isinstance(bank_account_id, int) else None
    if ba is None:
        raise ApiError("not_found", "Compte bancaire introuvable.", 404)
    return ba


def _int_list(data, key):
    values = data.get(key)
    if not isinstance(values, list) or not all(isinstance(v, int) and not isinstance(v, bool) for v in values):
        raise ApiError("bad_request", f"« {key} » : liste d'identifiants attendue.", 400)
    return values


def counters(bank_account_id):
    q = BankTransaction.query.filter_by(bank_account_id=bank_account_id)
    return {"unreconciled": q.filter_by(reconciled=False).count(), "total": q.count()}


def _counters_for(bt_ids):
    bt = db.session.get(BankTransaction, bt_ids[0]) if bt_ids else None
    return counters(bt.bank_account_id) if bt else None


def attachment_status(bt):
    """ok | missing | lost | None (source sans justificatifs, ex. OFX)."""
    if bt.attachment_count is None:
        return None
    if bt.attachment_lost:
        return "lost"
    if bt.attachment_count == 0 and bt.attachment_required:
        return "missing"
    return "ok"


def _rule_fitids(transactions) -> set[str]:
    """FITID des transactions passées par une règle en partie double (pièce de règle présente)."""
    refs = [f"RULE:{bt.fitid}" for bt in transactions if bt.reconciled]
    if not refs:
        return set()
    rows = db.session.query(JournalEntry.source_ref).filter(
        JournalEntry.source == rule_entries.SOURCE_RULE, JournalEntry.source_ref.in_(refs),
        JournalEntry.id.notin_(reversed_entry_ids()))
    return {ref.removeprefix("RULE:") for (ref,) in rows}


def serialize_transaction(bt, invoices=None, rule_fitids=()):
    line = bt.journal_line
    return {
        "id": bt.id,
        "date": bt.transaction_date.isoformat(),
        "label": bt.label or "",
        "raw_type": bt.raw_type,
        "note": bt.note,
        "amount_cents": bt.amount_cents,
        "reconciled": bt.reconciled,
        "is_reversed": bt.is_reversed,
        "attachment_status": attachment_status(bt),
        "category": bt.category,
        "entity": bt.entity.name if bt.entity else None,
        "entity_id": bt.entity_id,
        # Factures d'achat payées par cette transaction.
        "invoices": [{"id": p.id, "label": f"{'Avoir' if p.is_credit_note else 'Facture'} "
                      f"{p.invoice_number or 'sans numéro'}",
                      "url": url_for("purchases.detail", purchase_id=p.id)} for p in (invoices or [])],
        "entry": (
            {"id": line.entry_id, "reference": line.entry.reference,
             "url": url_for("entries.detail", entry_id=line.entry_id)}
            if line else None
        ),
        "new_entry_url": url_for("entries.new", bt_id=bt.id),
        # Passée par une règle (tiers par défaut ou tiers de la règle) : un vrai tiers peut être attribué.
        "rule_tiers": bt.fitid in rule_fitids,
    }


@bp.route("/bank-accounts/<int:bank_account_id>/transactions")
@login_required
def bank_transactions(bank_account_id):
    ba = _bank_account(bank_account_id)
    status = request.args.get("status", "unreconciled")
    # Écriture et tiers chargés avec les transactions (pas une requête par ligne).
    query = BankTransaction.query.filter_by(bank_account_id=ba.id).options(
        joinedload(BankTransaction.journal_line).joinedload(JournalLine.entry),
        joinedload(BankTransaction.entity),
    )
    if status == "unreconciled":
        query = query.filter_by(reconciled=False)
    elif status == "reconciled":
        query = query.filter_by(reconciled=True)
    if request.args.get("missing") == "1":
        # Justificatif exigé mais absent, ou déclaré perdu (transactions Qonto).
        query = query.filter(db.or_(
            db.and_(BankTransaction.attachment_required.is_(True), BankTransaction.attachment_count == 0),
            BankTransaction.attachment_lost.is_(True)))
    if request.args.get("no_invoice") == "1":
        # Débits qu'aucune facture d'achat ne désigne comme paiement.
        paid = db.session.query(PurchasePayment.bank_transaction_id).filter(
            PurchasePayment.bank_transaction_id.isnot(None))
        query = query.filter(BankTransaction.amount_cents < 0, BankTransaction.is_reversed.is_(False),
                             BankTransaction.id.notin_(paid))
    query = apply_month_filter(query, BankTransaction.transaction_date,
                               parse_month(request.args.get("month")))
    query = apply_date_sort(query, BankTransaction.transaction_date,
                            parse_sort(request.args.get("sort"), default="asc"))
    rows = query.order_by(BankTransaction.id).all()
    invoices = {}
    if rows:
        for payment in PurchasePayment.query.filter(
                PurchasePayment.bank_transaction_id.in_([bt.id for bt in rows])):
            invoices.setdefault(payment.bank_transaction_id, []).append(payment.purchase)
    rule_fitids = _rule_fitids(rows)
    return jsonify(transactions=[serialize_transaction(bt, invoices.get(bt.id), rule_fitids) for bt in rows],
                   counters=counters(ba.id))


@bp.route("/bank-transactions/<int:bt_id>/entity", methods=["POST"])
@login_required
def bank_transaction_assign_entity(bt_id):
    """Attribue un vrai tiers à une transaction passée par une règle : pièce et règlement repassés sur
    le compte du tiers (supprimés en brouillard, contrepassés si validés)."""
    bt = get_or_404(BankTransaction, bt_id, "Transaction bancaire introuvable.")
    entity_id = json_body().get("entity_id")
    entity = db.session.get(Entity, entity_id) if isinstance(entity_id, int) else None
    if entity is None:
        raise invalid("Tiers introuvable.", "entity_id")
    try:
        rule_entries.assign(bt, entity)
        db.session.commit()
    except LedgerError as exc:
        db.session.rollback()
        raise invalid(str(exc)) from None
    return jsonify(item=serialize_transaction(bt, rule_fitids=_rule_fitids([bt])),
                   notices=[notice(f"Transaction attribuée à {entity.name} : écritures repassées sur son compte.")])


@bp.route("/bank-transactions/<int:bt_id>/suggestions")
@login_required
def bank_transaction_suggestions(bt_id):
    if db.session.get(BankTransaction, bt_id) is None:
        raise ApiError("not_found", "Transaction bancaire introuvable.", 404)
    return jsonify(suggestions=[
        {
            "journal_line_id": line.id,
            "entry_id": line.entry_id,
            "reference": line.entry.reference,
            "entry_date": line.entry.entry_date.isoformat(),
            "label": line.label or line.entry.description or "",
            "account_code": line.account.code,
            "amount_cents": line.debit_cents - line.credit_cents,
            "score": score,
        }
        for line, score in suggest_matches_scored(bt_id)
    ])


@bp.route("/reconciliations", methods=["POST"])
@login_required
def reconciliations_create():
    items = json_body().get("items")
    if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
        raise ApiError("bad_request", "« items » : liste de {bank_transaction_id, journal_line_id} attendue.", 400)
    results = reconcile_many([(i.get("bank_transaction_id"), i.get("journal_line_id")) for i in items])
    done = [r["bank_transaction_id"] for r in results if r["status"] == "ok"]
    return jsonify(
        results=results,
        counters=_counters_for([i.get("bank_transaction_id") for i in items if isinstance(i.get("bank_transaction_id"), int)]),
        undo={"method": "POST", "url": url_for("api.reconciliations_delete"),
              "body": {"bank_transaction_ids": done}} if done else None,
    )


@bp.route("/reconciliations/delete", methods=["POST"])
@login_required
def reconciliations_delete():
    ids = _int_list(json_body(), "bank_transaction_ids")
    results = unreconcile_many(ids)
    relink = [{"bank_transaction_id": r["bank_transaction_id"], "journal_line_id": r["journal_line_id"]}
              for r in results if r["status"] == "ok"]
    return jsonify(
        results=results,
        counters=_counters_for(ids),
        undo={"method": "POST", "url": url_for("api.reconciliations_create"),
              "body": {"items": relink}} if relink else None,
    )


@bp.route("/reconciliations/auto", methods=["POST"])
@login_required
def reconciliations_auto():
    data = json_body()
    ba = _bank_account(data.get("bank_account_id"))
    ids = _int_list(data, "bank_transaction_ids") if "bank_transaction_ids" in data else None
    results = auto_reconcile(ba.id, bank_transaction_ids=ids, dry_run=bool(data.get("dry_run")))
    done = [r["bank_transaction_id"] for r in results if r["status"] == "ok"]
    return jsonify(
        results=results,
        counters=counters(ba.id),
        undo={"method": "POST", "url": url_for("api.reconciliations_delete"),
              "body": {"bank_transaction_ids": done}} if done else None,
    )


@bp.route("/bank-transactions/apply-rules", methods=["POST"])
@login_required
def bank_transactions_apply_rules():
    ids = _int_list(json_body(), "ids")
    transactions = BankTransaction.query.filter(BankTransaction.id.in_(ids)).all() if ids else []
    if len(transactions) != len(set(ids)):
        raise ApiError("not_found", "Transaction bancaire introuvable.", 404)
    result = apply_rules(transactions, overwrite=True)
    created = result["created_entry_ids"]
    return jsonify(
        summary={k: result[k] for k in ("matched", "posted", "skipped", "total")},
        errors=result["errors"],
        counters=_counters_for(ids),
        # L'annulation supprime les écritures générées (et leurs rapprochements) ;
        # la catégorie et le tiers affectés aux transactions sont conservés.
        undo={"method": "POST", "url": url_for("api.entries_bulk_delete"),
              "body": {"entry_ids": created}} if created else None,
    )


@bp.route("/entries/bulk-delete", methods=["POST"])
@login_required
def entries_bulk_delete():
    results = delete_entries(_int_list(json_body(), "entry_ids"))
    return jsonify(results=results)
