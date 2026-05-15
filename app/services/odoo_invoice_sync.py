"""Synchronisation des factures clients Odoo.

Récupère via XML-RPC :
- account.move (move_type='out_invoice')   → table customer_invoices
- account.move.line (lignes produit)       → table customer_invoice_lines

Miroir de odoo_pos_sync.py. Les helpers internes sont volontairement dupliqués
pour rester aligné sur le pattern POS plutôt que d'introduire une dépendance
croisée. Pas de notion d'adhésion / `is_member` ici : une facture client n'a
aucune sémantique d'adhésion.
"""
import json
from datetime import date, datetime

from app.extensions import db
from app.models import CustomerInvoice, CustomerInvoiceLine, Entity
from app.services.entity_resolver import entity_by_email, unique_entity_name
from app.services.odoo_client import from_app_config


PAGE_SIZE = 200


INVOICE_FIELDS = [
    "id", "name", "ref", "move_type", "state", "payment_state",
    "partner_id", "invoice_date", "invoice_date_due", "currency_id",
    "amount_untaxed", "amount_tax", "amount_total", "amount_residual",
    "invoice_origin", "journal_id", "narration",
    "invoice_line_ids",
]
INVOICE_LINE_FIELDS = [
    "id", "move_id", "product_id", "name",
    "quantity", "price_unit", "discount",
    "price_subtotal", "price_total", "tax_ids",
    "account_id", "display_type",
]
PARTNER_FIELDS = ["id", "name", "email", "phone", "mobile"]

DEFAULT_DOMAIN = [("move_type", "=", "out_invoice")]


def _to_cents(value):
    if value is None or value is False:
        return 0
    return int(round(float(value) * 100))


def _to_date(value):
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
        except (TypeError, ValueError):
            return None


def _m2o_id(value):
    if isinstance(value, (list, tuple)) and value:
        return value[0]
    return None


def _m2o_name(value):
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return value[1]
    return None


def _currency_code(value):
    name = _m2o_name(value)
    if not name:
        return "EUR"
    return name.upper()[:3]


def _chunked(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _upsert_invoice(item):
    odoo_id = item.get("id")
    if not odoo_id:
        return None, False
    existing = CustomerInvoice.query.filter_by(odoo_id=odoo_id).first()
    target = existing or CustomerInvoice(odoo_id=odoo_id)

    target.name = item.get("name") or None
    target.ref = item.get("ref") or None
    target.state = item.get("state") or None
    target.payment_state = item.get("payment_state") or None
    target.partner_id = _m2o_id(item.get("partner_id"))
    target.partner_name = _m2o_name(item.get("partner_id"))
    target.invoice_date = _to_date(item.get("invoice_date"))
    target.invoice_date_due = _to_date(item.get("invoice_date_due"))
    target.currency = _currency_code(item.get("currency_id"))
    target.amount_untaxed_cents = _to_cents(item.get("amount_untaxed"))
    target.amount_tax_cents = _to_cents(item.get("amount_tax"))
    target.amount_total_cents = _to_cents(item.get("amount_total"))
    target.amount_residual_cents = _to_cents(item.get("amount_residual"))
    target.invoice_origin = item.get("invoice_origin") or None
    target.journal_name = _m2o_name(item.get("journal_id"))
    target.narration = item.get("narration") or None
    target.raw_payload = json.dumps(item, ensure_ascii=False, default=str)
    target.imported_at = datetime.utcnow()

    is_new = existing is None
    if is_new:
        db.session.add(target)
    return target, is_new


def _is_product_line(item):
    """Filtre lignes produit (vs lignes TVA/contrepartie tiers).

    - display_type='product' depuis Odoo 16.
    - sinon fallback : product_id non vide.
    """
    display_type = item.get("display_type")
    if display_type == "product":
        return True
    if display_type and display_type not in (False, "product"):
        return False
    return bool(_m2o_id(item.get("product_id")))


def _upsert_line(item, invoice):
    odoo_id = item.get("id")
    if not odoo_id:
        return None, False
    existing = CustomerInvoiceLine.query.filter_by(odoo_id=odoo_id).first()
    target = existing or CustomerInvoiceLine(odoo_id=odoo_id)

    target.invoice_id = invoice.id
    target.product_id = _m2o_id(item.get("product_id"))
    target.product_name = _m2o_name(item.get("product_id"))
    target.description = item.get("name") or None
    target.qty = float(item.get("quantity") or 0)
    target.price_unit_cents = _to_cents(item.get("price_unit"))
    target.discount = float(item.get("discount") or 0)
    target.price_subtotal_cents = _to_cents(item.get("price_subtotal"))
    target.price_total_cents = _to_cents(item.get("price_total"))
    tax_ids = item.get("tax_ids") or []
    target.tax_ids = ",".join(str(t) for t in tax_ids) if tax_ids else None
    account_name = _m2o_name(item.get("account_id"))
    # account.id Odoo affiche typiquement "707100 Ventes...". On garde le préfixe code.
    if account_name:
        code = account_name.split(" ", 1)[0]
        target.account_code = code[:20] if code else None
    else:
        target.account_code = None
    target.raw_payload = json.dumps(item, ensure_ascii=False, default=str)
    target.imported_at = datetime.utcnow()

    is_new = existing is None
    if is_new:
        db.session.add(target)
    return target, is_new


def _fetch_partners(client, partner_ids):
    """Renvoie {partner_id: partner_data} depuis res.partner."""
    result = {}
    for chunk in _chunked(list(partner_ids), PAGE_SIZE):
        rows = client.search_read(
            "res.partner", domain=[["id", "in", chunk]],
            fields=PARTNER_FIELDS,
        )
        for row in rows:
            result[row["id"]] = row
    return result


def _resolve_partner_entity(partner, cache):
    """Crée/récupère l'Entity correspondant à un partner Odoo.

    Priorité : email. Sans email → pas de rattachement.
    Renvoie (entity, created, updated).
    """
    email = (partner.get("email") or "").strip() or None
    name = (partner.get("name") or "").strip() or None
    if not email:
        return None, False, False

    existing = entity_by_email(cache, email)
    if existing is not None:
        return existing, False, False

    base_name = name or email
    ent = Entity(
        name=unique_entity_name(base_name, email),
        entity_type="CLIENT",
        email=email,
    )
    db.session.add(ent)
    db.session.flush()
    cache[email.lower()] = ent
    return ent, True, False


def sync_customer_invoices(domain=None, limit=None, progress_cb=None):
    """Synchronise les factures clients Odoo.

    `domain` : filtre Odoo additionnel (combiné AVEC DEFAULT_DOMAIN).
    `limit`  : nombre max de factures (None = tout).
    `progress_cb(done, total, message)` : callback de progression.

    Retourne un dict de compteurs.
    """
    client = from_app_config()
    extra = list(domain or [])
    full_domain = list(DEFAULT_DOMAIN) + extra

    invoices_imported = invoices_updated = 0
    all_line_ids = []
    invoice_by_id = {}

    offset = 0
    while True:
        batch_limit = PAGE_SIZE if limit is None else min(PAGE_SIZE, limit - offset)
        if batch_limit <= 0:
            break
        items = client.search_read(
            "account.move", domain=full_domain, fields=INVOICE_FIELDS,
            limit=batch_limit, offset=offset, order="id asc",
        )
        if not items:
            break
        for item in items:
            target, is_new = _upsert_invoice(item)
            if target is None:
                continue
            if is_new:
                invoices_imported += 1
            else:
                invoices_updated += 1
            all_line_ids.extend(item.get("invoice_line_ids") or [])
            invoice_by_id[item["id"]] = target
        db.session.flush()
        if progress_cb:
            progress_cb(
                invoices_imported + invoices_updated, None,
                f"{invoices_imported + invoices_updated} facture(s) traitée(s)",
            )
        if len(items) < batch_limit:
            break
        offset += batch_limit
        if limit is not None and offset >= limit:
            break

    # 2. lignes — par lots d'IDs, filtrées sur lignes produit
    lines_imported = lines_updated = 0
    for chunk in _chunked(all_line_ids, PAGE_SIZE):
        items = client.search_read(
            "account.move.line", domain=[["id", "in", chunk]],
            fields=INVOICE_LINE_FIELDS,
        )
        for item in items:
            if not _is_product_line(item):
                continue
            invoice = invoice_by_id.get(_m2o_id(item.get("move_id")))
            if invoice is None:
                continue
            _, is_new = _upsert_line(item, invoice)
            if is_new:
                lines_imported += 1
            else:
                lines_updated += 1
        if progress_cb:
            progress_cb(
                lines_imported + lines_updated, len(all_line_ids),
                f"Lignes : {lines_imported + lines_updated}/{len(all_line_ids)}",
            )

    # 3. partenaires (res.partner) → email + Entity
    partner_ids = {i.partner_id for i in invoice_by_id.values() if i.partner_id}
    entities_created = entities_updated = 0
    if partner_ids:
        partners = _fetch_partners(client, partner_ids)
        entity_cache = {}
        partner_to_entity = {}
        for pid, partner in partners.items():
            ent, created, updated = _resolve_partner_entity(partner, entity_cache)
            if created:
                entities_created += 1
            if updated:
                entities_updated += 1
            if ent is not None:
                partner_to_entity[pid] = ent.id
        for invoice in invoice_by_id.values():
            partner = partners.get(invoice.partner_id) if invoice.partner_id else None
            if partner:
                invoice.partner_email = (partner.get("email") or "").strip() or None
            invoice.entity_id = partner_to_entity.get(invoice.partner_id)
        if progress_cb:
            progress_cb(
                entities_created + entities_updated, len(partner_ids),
                f"Tiers : {entities_created} créé(s), {entities_updated} maj",
            )

    db.session.commit()
    return {
        "invoices_imported": invoices_imported,
        "invoices_updated": invoices_updated,
        "invoices_total": invoices_imported + invoices_updated,
        "lines_imported": lines_imported,
        "lines_updated": lines_updated,
        "lines_total": lines_imported + lines_updated,
        "entities_created": entities_created,
        "entities_updated": entities_updated,
    }
