"""Synchronisation Qonto → factures d'achat (`purchases`).

Lecture de `GET /v2/supplier_invoices` par fenêtres (mensuelles sur `created_at`
au premier passage, puis incrémentale sur `updated_at`), dédoublonnage par
l'identifiant Qonto, commit par page ; le curseur (`sync_cursors`) n'avance
qu'après un succès complet.

Qonto ne fournit pas de lignes : elles sont construites ici à partir du produit
par défaut du fournisseur (une par taux de TVA quand Qonto donne la ventilation)
et régénérées tant que le trésorier ne les a pas modifiées. Une facture déjà
comptabilisée n'est jamais modifiée sur ses montants : un changement dans Qonto
est seulement signalé (`review_reason`).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from app.extensions import db
from app.models import Entity, Purchase, PurchaseLine, SyncCursor
from app.models.sync_cursor import CURSOR_QONTO_SUPPLIER_INVOICES
from app.services import catalog
from app.services.counterparties import name_key
from app.services.qonto_sync import (
    CURSOR_OVERLAP, PER_PAGE, SPLIT_THRESHOLD, _paris_midnight_utc, _parse_utc, default_sync_from,
)

STATUS_LABELS = {
    "to_review": "À traiter",
    "to_pay": "À payer",
    "to_approve": "À approuver",
    "awaiting_payment": "À payer",
    "pending": "En attente",
    "scheduled": "Programmée",
    "paid": "Payée",
    "archived": "Archivée",
    "rejected": "Rejetée",
    "discarded": "Écartée",
}
HIDDEN_STATUSES = {"rejected", "discarded"}
NON_FINANCIAL_CATEGORIES = {"OTHER_NON_FINANCIAL_DOCUMENT"}
# Champs comptables figés une fois la facture comptabilisée (changement → signalé).
POSTED_FIELDS = {
    "total_cents": "montant TTC",
    "untaxed_cents": "montant HT",
    "tax_cents": "TVA",
    "issue_date": "date",
    "is_credit_note": "nature (facture / avoir)",
}


# ------------------------------------------------------------------ champs

def amount_cents(money) -> int | None:
    """{"value": "22.10"} → 2210 (valeur absolue : le signe est porté par is_credit_note)."""
    if not money or money.get("value") in (None, ""):
        return None
    try:
        value = Decimal(str(money["value"]))
    except InvalidOperation:
        return None
    return abs(int((value * 100).quantize(Decimal("1"))))


def _date(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def is_hidden(inv: dict) -> bool:
    return (inv.get("status") in HIDDEN_STATUSES
            or bool(inv.get("is_attachment_non_financial"))
            or inv.get("attachment_category") in NON_FINANCIAL_CATEGORIES)


def invoice_fields(inv: dict) -> dict:
    """Champs d'une facture Qonto pour `Purchase` (sans lignes ni rattachement)."""
    snapshot = inv.get("supplier_snapshot") or {}
    total = inv.get("total_amount") or {}
    supplier = (snapshot.get("name") or inv.get("supplier_name") or inv.get("issuer_name") or "")
    related = [r.get("id") for r in (inv.get("related_invoices") or []) if r.get("id")]
    return {
        "supplier_name": supplier.strip()[:200] or None,
        "qonto_supplier_id": snapshot.get("id") or inv.get("supplier_id") or None,
        "supplier_vat": (snapshot.get("vat_number") or inv.get("vat_number") or "")
                        .replace(" ", "").upper()[:30] or None,
        "supplier_iban": (snapshot.get("iban") or inv.get("iban") or "")
                         .replace(" ", "").upper()[:34] or None,
        "invoice_number": (inv.get("invoice_number") or "")[:100] or None,
        "issue_date": _date(inv.get("issue_date")),
        "due_date": _date(inv.get("due_date")),
        "payment_date": _date(inv.get("payment_date")),
        "currency": (total.get("currency") or inv.get("currency") or "EUR")[:3],
        "total_cents": amount_cents(total) or 0,
        "untaxed_cents": amount_cents(inv.get("total_amount_excluding_taxes")),
        "tax_cents": amount_cents(inv.get("total_tax_amount")),
        "payable_cents": amount_cents(inv.get("payable_amount")),
        "is_credit_note": bool(inv.get("is_credit_note")),
        "is_einvoice": bool(inv.get("is_einvoice")),
        "qonto_status": (inv.get("status") or "")[:20] or None,
        "is_hidden": is_hidden(inv),
        "attachment_id": inv.get("attachment_id") or None,
        "related_qonto_ids": json.dumps(related) if related else None,
        "source_updated_at": _parse_utc(inv.get("updated_at")),
    }


def taxes(inv: dict) -> list[tuple[int, int]]:
    """Ventilation Qonto [(taux en points de base, TVA en centimes)], taux nuls en dernier."""
    rows = []
    for tax in inv.get("taxes") or []:
        try:
            rate = catalog.parse_rate_bp(tax.get("tax_rate"))
        except ValueError:
            continue
        amount = amount_cents(tax.get("tax_amount"))
        if rate is None or amount is None:
            continue
        rows.append((rate, amount))
    return sorted(rows, key=lambda row: row[0] == 0)


# ------------------------------------------------------------------ lignes

def default_lines(purchase: Purchase, product, breakdown) -> list[PurchaseLine]:
    """Lignes par défaut ; leur total est toujours égal au TTC de la facture.

    - une ligne par taux quand Qonto donne la ventilation et le HT ;
    - sinon une ligne HT / TVA si Qonto les connaît (taux déduit du produit s'il concorde) ;
    - sinon une ligne TTC à taux à confirmer.
    """
    total, untaxed = purchase.total_cents, purchase.untaxed_cents
    base = {"product_id": product.id, "account_id": product.purchase_account_id,
            "label": product.name}
    lines = []
    if breakdown and untaxed is not None and untaxed <= total:
        others = breakdown[:-1]
        for position, (rate, vat) in enumerate(others):
            line_untaxed = round(vat * 10000 / rate) if rate else 0
            lines.append(PurchaseLine(position=position, vat_rate_bp=rate, untaxed_cents=line_untaxed,
                                      vat_cents=vat, total_cents=line_untaxed + vat, **base))
        rate, _ = breakdown[-1]
        last_untaxed = untaxed - sum(line.untaxed_cents for line in lines)
        last_total = total - sum(line.total_cents for line in lines)
        lines.append(PurchaseLine(position=len(others), vat_rate_bp=rate, untaxed_cents=last_untaxed,
                                  vat_cents=last_total - last_untaxed, total_cents=last_total, **base))
        return lines
    if untaxed is not None and untaxed <= total:
        vat = total - untaxed
        rate = product.vat_rate_bp
        if rate is None or abs(round(untaxed * rate / 10000) - vat) > 1:
            rate = 0 if vat == 0 else None
        return [PurchaseLine(position=0, vat_rate_bp=rate, untaxed_cents=untaxed, vat_cents=vat,
                             total_cents=total, **base)]
    return [PurchaseLine(position=0, vat_rate_bp=None, untaxed_cents=total, vat_cents=0,
                         total_cents=total, **base)]


# ------------------------------------------------------------- fournisseurs

def match_entity(purchase: Purchase) -> Entity | None:
    """Entité du fournisseur : identifiant Qonto, puis n° de TVA, puis nom normalisé.

    Une entité trouvée reçoit l'identifiant Qonto, la TVA et l'IBAN s'ils lui manquent.
    """
    entity = None
    if purchase.qonto_supplier_id:
        entity = Entity.query.filter_by(qonto_supplier_id=purchase.qonto_supplier_id).first()
    if entity is None and purchase.supplier_vat:
        entity = Entity.query.filter_by(vat_number=purchase.supplier_vat).first()
    if entity is None and purchase.supplier_name:
        key = name_key(purchase.supplier_name)
        entity = next((e for e in Entity.query.order_by(Entity.id) if name_key(e.name) == key),
                      None)
    if entity is not None:
        entity.qonto_supplier_id = entity.qonto_supplier_id or purchase.qonto_supplier_id
        entity.vat_number = entity.vat_number or purchase.supplier_vat
        entity.iban = entity.iban or purchase.supplier_iban
    return entity


# ------------------------------------------------------------------ upsert

def _new_result() -> dict:
    return {"read": 0, "created": 0, "updated": 0, "unchanged": 0, "hidden": 0,
            "to_review": 0, "without_supplier": 0, "posted": 0, "to_complete": 0, "errors": []}


def upsert_invoice(inv: dict, result: dict) -> Purchase:
    """Crée ou met à jour une facture Qonto (sans commit)."""
    fields = invoice_fields(inv)
    purchase = Purchase.query.filter_by(qonto_id=inv["id"]).first()
    if purchase is None:
        purchase = Purchase(qonto_id=inv["id"], source="qonto", **fields)
        db.session.add(purchase)
        result["created"] += 1
        result["hidden"] += purchase.is_hidden
    elif purchase.source_updated_at and purchase.source_updated_at == fields["source_updated_at"]:
        result["unchanged"] += 1
        return purchase
    else:
        _update(purchase, fields, result)
        result["updated"] += 1
    _complete(purchase, inv, result)
    return purchase


def apply_payload(purchase: Purchase, inv: dict) -> None:
    """Réapplique la facture Qonto (ex. après annulation de la comptabilisation), sans commit."""
    _update(purchase, invoice_fields(inv), _new_result())
    _complete(purchase, inv, _new_result())


def _complete(purchase: Purchase, inv: dict, result: dict) -> None:
    """Réponse brute, rattachement du fournisseur, lignes par défaut."""
    purchase.raw_payload = json.dumps(inv, ensure_ascii=False)
    if purchase.entity_id is None:
        entity = match_entity(purchase)
        if entity is not None:
            purchase.entity = entity
    if purchase.entity is None and not purchase.is_hidden:
        result["without_supplier"] += 1

    if purchase.journal_entry_id is None and not purchase.lines_edited:
        purchase.lines = default_lines(purchase, catalog.product_for(purchase.entity), taxes(inv))


def _update(purchase: Purchase, fields: dict, result: dict) -> None:
    was_hidden = purchase.is_hidden
    if purchase.journal_entry_id is not None:
        changes = [label for key, label in POSTED_FIELDS.items()
                   if getattr(purchase, key) != fields[key]]
        if fields["is_hidden"] and not was_hidden:
            changes.append(f"statut « {STATUS_LABELS.get(fields['qonto_status'], fields['qonto_status'])} »")
        if changes:
            purchase.review_reason = ("Modifiée dans Qonto après comptabilisation : "
                                      + ", ".join(changes) + ".")
            result["to_review"] += 1
        fields = {k: v for k, v in fields.items() if k not in POSTED_FIELDS}
    for key, value in fields.items():
        setattr(purchase, key, value)
    if purchase.is_hidden and not was_hidden:
        result["hidden"] += 1


# ------------------------------------------------------------------ synchro

def cursor() -> SyncCursor:
    """Curseur des factures d'achat (créé à la demande, sans commit)."""
    row = SyncCursor.query.filter_by(key=CURSOR_QONTO_SUPPLIER_INVOICES).first()
    if row is None:
        row = SyncCursor(key=CURSOR_QONTO_SUPPLIER_INVOICES)
        db.session.add(row)
        db.session.flush()
    return row


def cursor_row() -> SyncCursor | None:
    """Curseur existant, sans le créer (affichage)."""
    return SyncCursor.query.filter_by(key=CURSOR_QONTO_SUPPLIER_INVOICES).first()


def sync_from_date() -> date:
    row = SyncCursor.query.filter_by(key=CURSOR_QONTO_SUPPLIER_INVOICES).first()
    return (row.sync_from if row and row.sync_from else None) or default_sync_from()


def set_sync_from(day: date) -> None:
    cursor().sync_from = day
    db.session.commit()


def _windows(row: SyncCursor, started: datetime):
    """Mensuelles sur `created_at` au premier passage, puis `updated_at` depuis le curseur."""
    if row.synced_at is None:
        day = row.sync_from or default_sync_from()
        month = date(day.year, day.month, 1)
        while True:
            start = _paris_midnight_utc(max(month, day))
            if start >= started:
                return
            next_month = date(month.year + month.month // 12, month.month % 12 + 1, 1)
            end = min(_paris_midnight_utc(next_month), started)
            yield {"key": "created", "start": start, "end": end}
            if end >= started:
                return
            month = next_month
    else:
        yield {"key": "updated", "start": row.synced_at - CURSOR_OVERLAP, "end": started}


def _iter_pages(client, window):
    """Pages de la fenêtre ; coupée en deux tant qu'elle dépasse SPLIT_THRESHOLD résultats."""
    key, start, end = window["key"], window["start"], window["end"]
    filters = {f"{key}_from": start, f"{key}_to": end, "per_page": PER_PAGE}
    items, meta = client.list_supplier_invoices(page=1, **filters)
    if (meta.get("total_count") or 0) > SPLIT_THRESHOLD and end - start > timedelta(minutes=1):
        middle = start + (end - start) / 2
        yield from _iter_pages(client, {**window, "end": middle})
        yield from _iter_pages(client, {**window, "start": middle})
        return
    yield items, meta
    page = meta.get("next_page")
    while page:
        items, meta = client.list_supplier_invoices(page=page, **filters)
        yield items, meta
        page = meta.get("next_page")


def sync_supplier_invoices(client=None, progress_cb=None) -> dict:
    """Synchronise les factures d'achat Qonto de l'organisation."""
    from app.services import purchase_posting, qonto_client

    client = client or qonto_client.from_app_config()
    row = cursor()
    db.session.commit()

    started = datetime.utcnow()
    result = _new_result()
    for window in _windows(row, started):
        for items, _meta in _iter_pages(client, window):
            touched = []
            for inv in items:
                touched.append(upsert_invoice(inv, result))
                result["read"] += 1
                if progress_cb:
                    progress_cb(result["read"], None, f"{result['read']} facture(s) lue(s)…")
            db.session.commit()
            # Comptabilisation automatique des factures devenues prêtes (une transaction chacune).
            posting = purchase_posting.post_ready(touched)
            result["posted"] += posting["posted"]
            result["errors"].extend(posting["errors"])

    row.synced_at = started
    db.session.commit()
    result["to_complete"] = purchase_posting.count_to_complete()
    return result


def start_sync(app):
    """Lance (ou renvoie) la synchronisation des factures en arrière-plan."""
    from app.models.sync_job import SYNC_KIND_QONTO_INVOICES
    from app.services import integrations, sync_jobs

    def work(job_id):
        return sync_supplier_invoices(progress_cb=sync_jobs.progress_callback(job_id))

    def error_message(exc):
        if type(exc) is RuntimeError:
            return str(exc)
        return integrations.mask_secrets("qonto", integrations.describe_error("qonto", exc))

    return sync_jobs.start(app, SYNC_KIND_QONTO_INVOICES, work,
                           message="Démarrage de la synchronisation des factures…",
                           error_message=error_message)


def latest_job():
    from app.models import SyncJob
    from app.models.sync_job import SYNC_KIND_QONTO_INVOICES

    return (SyncJob.query.filter_by(kind=SYNC_KIND_QONTO_INVOICES)
            .order_by(SyncJob.started_at.desc(), SyncJob.id.desc()).first())
