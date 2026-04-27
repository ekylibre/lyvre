"""Synchronisation des Payouts et Payments Stancer (API v2).

Endpoints utilisés (https://api.stancer.com/v2) :
- GET /payouts                 : liste paginée des payouts
- GET /payouts/{id}/payments   : payments rattachés à un payout

Auth : HTTP Basic, login = STANCER_SECRET_KEY, password vide.
"""
import json
from datetime import datetime

import requests
from flask import current_app

from app.extensions import db
from app.models import Payout, Payment, BankTransaction


API_BASE = "https://api.stancer.com/v2"
PAGE_SIZE = 100


def _get_secret_key():
    key = current_app.config.get("STANCER_SECRET_KEY")
    if not key:
        raise RuntimeError(
            "Clé secrète Stancer manquante : définissez STANCER_SECRET_KEY dans .env"
        )
    return key


def _to_date(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.utcfromtimestamp(value).date()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            return None
    return None


def _to_datetime(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.utcfromtimestamp(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _api_get(path, **params):
    url = f"{API_BASE}{path}"
    response = requests.get(
        url,
        auth=(_get_secret_key(), ""),
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _paginate(path, collection_key):
    """Yield every item across all pages of a list endpoint."""
    start = 0
    while True:
        payload = _api_get(path, start=start, limit=PAGE_SIZE)
        items = payload.get(collection_key) or payload.get("data") or []
        if not items:
            return
        for item in items:
            yield item
        if len(items) < PAGE_SIZE:
            return
        start += PAGE_SIZE


def _customer_field(customer, *keys):
    if not isinstance(customer, dict):
        return None
    for k in keys:
        v = customer.get(k)
        if v:
            return v
    return None


def _match_bank_transaction(amount_cents, date_bank, description):
    """Cherche une BankTransaction qui correspond au payout.

    Critères, du plus précis au plus tolérant :
    1. amount + label contient "No <description>"  (référence Stancer unique)
    2. amount + transaction_date == date_bank      (fallback si pas de description)

    On ne lie que si exactement un candidat correspond.
    """
    if not amount_cents:
        return None

    if description:
        cands = (
            BankTransaction.query.filter_by(amount_cents=amount_cents)
            .filter(BankTransaction.label.like(f"%No {description}%"))
            .limit(2)
            .all()
        )
        if len(cands) == 1:
            return cands[0]
        if len(cands) >= 2:
            return None

    if date_bank:
        cands = (
            BankTransaction.query.filter_by(
                amount_cents=amount_cents,
                transaction_date=date_bank,
            )
            .limit(2)
            .all()
        )
        if len(cands) == 1:
            return cands[0]
    return None


def _upsert_payout(item):
    stancer_id = item.get("id")
    if not stancer_id:
        return None, False

    existing = Payout.query.filter_by(stancer_id=stancer_id).first()
    target = existing or Payout(stancer_id=stancer_id)

    # total = montant net versé en banque, payments.amount = brut, fees = commissions.
    payments_block = item.get("payments") or {}
    gross = payments_block.get("amount") if isinstance(payments_block, dict) else None
    net = item.get("total")
    target.amount_cents = int(net if net is not None else (gross or 0))
    target.currency = (item.get("currency") or "EUR").upper()
    target.status = item.get("status") or "pending"
    target.date_payout = _to_date(item.get("date_paym") or item.get("date_payout"))
    target.date_bank = _to_date(item.get("date_bank"))
    target.statement_description = (
        item.get("statement_description") or item.get("description")
    )
    target.fees_cents = int(item.get("fees") or 0)
    target.description = item.get("description") or item.get("reference")
    target.raw_payload = json.dumps(item, ensure_ascii=False)
    target.created_at = _to_datetime(item.get("created")) or target.created_at
    target.imported_at = datetime.utcnow()

    if not target.bank_transaction_id:
        match = _match_bank_transaction(
            target.amount_cents, target.date_bank, target.description
        )
        if match:
            target.bank_transaction_id = match.id

    is_new = existing is None
    if is_new:
        db.session.add(target)
    return target, is_new


def _upsert_payment(item, payout):
    stancer_id = item.get("id")
    if not stancer_id:
        return None, False

    existing = Payment.query.filter_by(stancer_id=stancer_id).first()
    target = existing or Payment(stancer_id=stancer_id)

    target.payout_id = payout.id if payout else None
    target.amount_cents = int(item.get("amount") or 0)
    target.currency = (item.get("currency") or "EUR").upper()
    target.status = item.get("status")
    target.method = item.get("method") or item.get("methods_allowed")
    target.description = item.get("description")
    target.order_id = item.get("order_id")
    target.unique_id = item.get("unique_id")

    customer = item.get("customer")
    target.customer_email = _customer_field(customer, "email")
    target.customer_name = _customer_field(customer, "name")

    target.date_payment = _to_datetime(item.get("date_payment") or item.get("date"))
    target.created_at = _to_datetime(item.get("created")) or target.created_at
    target.raw_payload = json.dumps(item, ensure_ascii=False)
    target.imported_at = datetime.utcnow()

    is_new = existing is None
    if is_new:
        db.session.add(target)
    return target, is_new


def sync_payments_for_payout(payout, progress_cb=None):
    """Récupère et upsert tous les payments d'un payout via /v2/payouts/{id}/payments.

    `progress_cb(done, total, message)` est appelé après chaque payment traité.
    Retourne (imported, updated, total).
    """
    imported = updated = total = 0
    for item in _paginate(f"/payouts/{payout.stancer_id}/payments", "payments"):
        total += 1
        _, is_new = _upsert_payment(item, payout)
        if is_new:
            imported += 1
        else:
            updated += 1
        if progress_cb:
            progress_cb(total, None, f"{payout.stancer_id} : {total} paiement(s)")
    return imported, updated, total


def sync_payouts(progress_cb=None):
    """Synchronise tous les payouts puis leurs payments.

    `progress_cb(done, total, message)` est appelé régulièrement pendant le
    traitement. Retourne un dict avec compteurs payouts et payments.
    """
    imported = updated = total_seen = 0
    payments_imported = payments_updated = payments_total = 0

    touched_payouts = []
    for item in _paginate("/payouts", "payouts"):
        total_seen += 1
        target, is_new = _upsert_payout(item)
        if target is None:
            continue
        if is_new:
            imported += 1
        else:
            updated += 1
        touched_payouts.append(target)
        if progress_cb:
            progress_cb(total_seen, None, f"Payout {target.stancer_id}")

    # Flush pour que les nouveaux payouts aient un id avant le rattachement des payments.
    db.session.flush()

    nb_payouts = len(touched_payouts)
    for idx, payout in enumerate(touched_payouts, start=1):
        try:
            pi, pu, pt = sync_payments_for_payout(payout)
            payments_imported += pi
            payments_updated += pu
            payments_total += pt
        except requests.HTTPError as e:
            # 404 = pas de payments pour ce payout, on continue.
            if e.response is None or e.response.status_code != 404:
                raise
        if progress_cb:
            progress_cb(
                idx, nb_payouts,
                f"Paiements : {idx}/{nb_payouts} payouts traités "
                f"({payments_total} paiement(s))",
            )

    db.session.commit()
    return {
        "imported": imported,
        "updated": updated,
        "total": total_seen,
        "payments_imported": payments_imported,
        "payments_updated": payments_updated,
        "payments_total": payments_total,
    }
