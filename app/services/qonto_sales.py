"""Ventes avec Qonto (lot S4, claudedocs/design_ventes.md § 6) — périmètre « Ventes » de
l'intégration Qonto.

Émission (case « Émettre avec Qonto ») : la pièce est d'abord validée par l'application, puis
créée dans Qonto — facture en brouillon puis finalisée (Qonto attribue le numéro), avoir, devis —
et comptabilisée avec le numéro Qonto ; le PDF Factur-X de Qonto (produit en différé) est
récupéré ensuite. Le client est cherché dans Qonto (SIREN, TVA, email, nom) avant d'être créé.

Écritures dans Qonto : seulement sur action explicite (émission, envoi, encaissement d'une facture
Qonto), jamais rejouées automatiquement (client sans reprise). La synchronisation ne fait que lire :
clients et produits rattachés ou importés, devis et factures créés dans Qonto importés, statuts
mis à jour, PDF récupérés.

Contraintes de l'API : libellé d'une ligne limité à 40 caractères (la suite passe en description),
lignes non liées aux produits, IBAN obligatoire d'un compte Qonto de l'organisation, aucun lien
facture ↔ transaction (l'encaissement est rapproché par l'application, puis marqué payé dans Qonto).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal

from app.extensions import db
from app.models import BankAccount, Entity, Product, Sale, SaleLine, SyncCursor
from app.services import billing, external_config
from app.services.qonto_client import QontoError, from_app_config
from app.services.sale_entry import SaleError, client_snapshot, compute, default_sale_account, vat_mode_for

TITLE_MAX = 40
CURSOR = "qonto_sales"
QUOTE_STATUSES = {"pending_approval": "issued", "approved": "accepted", "canceled": "refused"}


def available() -> bool:
    return external_config.scope_available("qonto", "sales")


def client():
    """Client Qonto sans reprise automatique : une création n'est jamais envoyée deux fois."""
    return from_app_config(retry=False)


def _money(cents: int) -> str:
    return f"{Decimal(cents) / 100:.2f}"


def _rate(bp: int) -> str:
    return str((Decimal(bp) / 10000).normalize()) if bp else "0"


def _cents(value) -> int:
    if isinstance(value, dict):
        value = value.get("value")
    return int((Decimal(str(value or "0")) * 100).quantize(Decimal("1")))


# ------------------------------------------------------------------ client

def _client_payload(entity: Entity) -> dict:
    snap = client_snapshot(entity)
    payload = {"currency": "EUR", "locale": "FR", "email": entity.email or None,
               "billing_address": {"street_address": " ".join(filter(None, [snap["address_line1"], snap["address_line2"]])),
                                   "city": snap["city"] or "", "zip_code": snap["postal_code"] or "", "country_code": "FR"}}
    if entity.person_kind == "individual":
        first, _, last = entity.name.partition(" ")
        payload.update(kind="individual", first_name=first[:60], last_name=(last or first)[:60])
    else:
        payload.update(kind="company", name=entity.name[:250])
        if entity.siret:
            payload["tax_identification_number"] = entity.siret[:9]
        if entity.vat_number:
            payload["vat_number"] = entity.vat_number
    return {k: v for k, v in payload.items() if v is not None}


def ensure_client(entity: Entity, api) -> str:
    """Identifiant du client Qonto du tiers : déjà connu, retrouvé (SIREN, TVA, email, nom), sinon créé."""
    if entity.qonto_client_id:
        return entity.qonto_client_id
    searches = [{"tax_identification_number": (entity.siret or "")[:9]}, {"vat_number": entity.vat_number},
                {"email": entity.email}, {"name": entity.name}]
    for filters in searches:
        if any(filters.values()):
            found = api.find_clients(**filters)
            if len(found) == 1:
                entity.qonto_client_id = found[0]["id"]
                return entity.qonto_client_id
    created = api.create_client(_client_payload(entity))
    if not created.get("id"):
        raise QontoError("Qonto n'a pas créé le client.")
    entity.qonto_client_id = created["id"]
    return entity.qonto_client_id


def qonto_iban() -> str:
    """IBAN d'un compte Qonto de l'organisation (exigé par Qonto pour une facture)."""
    account = BankAccount.query.filter(BankAccount.qonto_account_id.isnot(None), BankAccount.iban.isnot(None)).first()
    iban = account.iban if account else billing.get().iban
    if not iban:
        raise SaleError("IBAN du compte Qonto inconnu : rattachez le compte bancaire Qonto (Comptes Qonto) "
                        "ou renseignez l'IBAN dans l'onglet Facturation.", status=409)
    return iban.replace(" ", "")


# ------------------------------------------------------------------ lignes

def items(sale: Sale) -> list[dict]:
    rows = []
    for line in sale.lines:
        title, rest = line.label[:TITLE_MAX], line.label[TITLE_MAX:]
        description = " ".join(filter(None, [rest.strip(), line.description or ""]))
        unit_price = line.unit_price_cents
        if line.discount_bp:  # remise incluse dans le prix unitaire (format de remise de Qonto non garanti)
            unit_price = round(Decimal(unit_price) * (10000 - line.discount_bp) / 10000)
            description = (description + f" (remise {Decimal(line.discount_bp) / 100:g} % incluse)").strip()
        item = {"title": title, "quantity": str((Decimal(line.quantity_milli) / 1000).normalize()),
                "unit_price": {"value": _money(unit_price), "currency": "EUR"}, "currency": "EUR",
                "vat_rate": "0" if sale.vat_mode == "none" else _rate(line.vat_rate_bp)}
        if description:
            item["description"] = description[:600]
        if line.unit:
            item["unit"] = line.unit[:20]
        if sale.vat_mode == "none":
            item["vat_exemption_reason"] = "S293B"
        rows.append(item)
    return rows


# ------------------------------------------------------------------ émission

def emit(sale: Sale) -> dict:
    """Crée (et finalise) la pièce dans Qonto ; renvoie l'objet Qonto (avec son numéro).
    Rien n'est comptabilisé ici : l'appelant passe l'écriture avec ce numéro."""
    if not available():
        raise SaleError(external_config.required_message("qonto", "sales"), status=409)
    api = client()
    if sale.kind == "credit_note":
        invoice = sale.invoice
        if not invoice or not invoice.qonto_id:
            raise SaleError("L'avoir d'une facture émise par Qonto se fait dans Qonto ; celle-ci n'en vient pas.", status=409)
        obj = api.create_credit_note({"invoice_id": invoice.qonto_id, "issue_date": sale.issue_date.isoformat(),
                                      "reason": (sale.credit_reason or "Avoir")[:500], "currency": "EUR",
                                      "items": items(sale)})
    else:
        client_id = ensure_client(sale.entity, api)
        db.session.flush()
        if sale.kind == "quote":
            obj = api.create_quote({"client_id": client_id, "issue_date": sale.issue_date.isoformat(),
                                    "expiry_date": (sale.validity_date or sale.issue_date + timedelta(days=30)).isoformat(),
                                    "terms_and_conditions": (sale.terms or "Devis valable jusqu'à la date indiquée.")[:3000],
                                    "currency": "EUR", "items": items(sale),
                                    **({"header": sale.header} if sale.header else {}),
                                    **({"footer": sale.footer} if sale.footer else {})})
        else:
            payload = {"client_id": client_id, "issue_date": sale.issue_date.isoformat(),
                       "due_date": (sale.due_date or sale.issue_date).isoformat(), "currency": "EUR",
                       "status": "draft", "payment_methods": {"iban": qonto_iban()}, "items": items(sale)}
            quote = db.session.get(Sale, sale.quote_id) if sale.quote_id else None
            if quote is not None and quote.qonto_id:
                payload["quote_id"] = quote.qonto_id
            if sale.purchase_order:
                payload["purchase_order"] = sale.purchase_order[:40]
            if sale.service_start:
                payload["performance_start_date"] = sale.service_start.isoformat()
            if sale.service_end:
                payload["performance_end_date"] = sale.service_end.isoformat()
            if sale.terms:
                payload["terms_and_conditions"] = sale.terms[:525]
            draft = api.create_client_invoice(payload)
            if not draft.get("id"):
                raise QontoError("Qonto n'a pas créé la facture.")
            try:
                obj = api.finalize_client_invoice(draft["id"])
            except Exception:
                try:
                    api.delete_client_invoice(draft["id"])  # pas de brouillon orphelin dans Qonto
                except Exception:  # noqa: BLE001 — le brouillon restera visible dans Qonto
                    pass
                raise
    if not obj.get("id") or not obj.get("number"):
        raise QontoError("Qonto n'a pas renvoyé le numéro de la pièce.")
    return obj


def apply(sale: Sale, obj: dict) -> None:
    """Reporte l'objet Qonto sur la pièce (identifiant, statut, pièce jointe), sans commit."""
    sale.qonto_id = obj.get("id") or sale.qonto_id
    sale.qonto_status = obj.get("status") or sale.qonto_status
    sale.qonto_attachment_id = obj.get("attachment_id") or sale.qonto_attachment_id
    sale.raw_payload = json.dumps(obj)[:20000]


# ------------------------------------------------------------------ PDF, paiement, envoi

def fetch_pdf(sale: Sale, api=None) -> bool:
    """Télécharge et conserve le PDF Qonto de la pièce s'il est prêt ; vrai si c'est fait."""
    from app.services import sale_documents
    from app.services.attachments import instance_dir

    if not sale.qonto_id or sale_documents.pdf_file(sale) is not None:
        return False
    api = api or client()
    if not sale.qonto_attachment_id and sale.kind == "invoice":
        apply(sale, api.get_client_invoice(sale.qonto_id))
    if not sale.qonto_attachment_id:
        return False
    url = api.attachment(sale.qonto_attachment_id).get("url")
    if not url:
        return False
    folder = instance_dir() / "ventes" / str(sale.issue_date.year)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{sale.number}.pdf"
    path.write_bytes(api.download(url))
    sale.pdf_path = str(path.relative_to(instance_dir()))
    return True


def mark_paid(sale: Sale, paid_on: date) -> None:
    """Facture Qonto soldée par un encaissement rapproché : marquée payée dans Qonto (V11)."""
    if sale.kind == "invoice" and sale.qonto_id and available():
        apply(sale, client().mark_client_invoice_paid(sale.qonto_id, min(paid_on, date.today()).isoformat()))


def unmark_paid(sale: Sale) -> None:
    if sale.kind == "invoice" and sale.qonto_id and sale.qonto_status == "paid" and available():
        apply(sale, client().unmark_client_invoice_paid(sale.qonto_id))


def send(sale: Sale, to: list[str], subject: str, body: str) -> None:
    payload = {"send_to": to, "email_title": subject[:255], "email_body": body, "copy_to_self": False}
    if sale.kind == "quote":
        client().send_quote(sale.qonto_id, payload)
    else:
        client().send_client_invoice(sale.qonto_id, payload)


# ------------------------------------------------------------------ synchronisation (lecture)

def _cursor() -> SyncCursor:
    row = SyncCursor.query.filter_by(key=CURSOR).first()
    if row is None:
        row = SyncCursor(key=CURSOR)
        db.session.add(row)
    return row


def _entity_for(qonto_client: dict, result: dict) -> Entity:
    """Tiers d'un client Qonto : déjà rattaché, retrouvé (SIREN, TVA, email, nom), sinon créé."""
    cid = qonto_client.get("id")
    entity = Entity.query.filter_by(qonto_client_id=cid).first() if cid else None
    if entity is not None:
        return entity
    name = (qonto_client.get("name") or " ".join(filter(None, [qonto_client.get("first_name"), qonto_client.get("last_name")]))
            or "Client Qonto").strip()[:200]
    siren = (qonto_client.get("tax_identification_number") or "")[:9]
    query = Entity.query
    entity = ((siren and query.filter(Entity.siret.like(f"{siren}%")).first())
              or (qonto_client.get("vat_number") and query.filter_by(vat_number=qonto_client["vat_number"]).first())
              or (qonto_client.get("email") and query.filter_by(email=qonto_client["email"]).first())
              or query.filter(db.func.lower(Entity.name) == name.lower()).first())
    if entity is None:
        address = qonto_client.get("billing_address") or {}
        entity = Entity(name=name, entity_type="CLIENT", email=qonto_client.get("email"),
                        vat_number=qonto_client.get("vat_number"), siret=siren or None,
                        address_line1=address.get("street_address") or qonto_client.get("address"),
                        postal_code=address.get("zip_code") or qonto_client.get("zip_code"),
                        city=address.get("city") or qonto_client.get("city"),
                        person_kind="individual" if qonto_client.get("kind") == "individual" else "company")
        db.session.add(entity)
    entity.qonto_client_id = cid
    result["clients_linked"] += 1
    return entity


def _lines_from(obj: dict, sale: Sale) -> list[SaleLine]:
    account = default_sale_account()
    lines = []
    for i, item in enumerate(obj.get("items") or []):
        rate = Decimal(str(item.get("vat_rate") or "0"))
        lines.append(SaleLine(position=i, label=(item.get("title") or "Ligne")[:300], description=item.get("description"),
                              quantity_milli=int(Decimal(str(item.get("quantity") or "1")) * 1000),
                              unit=(item.get("unit") or None), unit_price_cents=_cents(item.get("unit_price")),
                              vat_rate_bp=int(rate * 10000), account_id=account.id if account else None))
    return lines


def _import(obj: dict, kind: str, result: dict, api) -> Sale | None:
    """Pièce créée dans Qonto (hors application) : importée, comptabilisée si c'est une facture."""
    from app.services import sale_issue

    client_obj = obj.get("client") or {"id": obj.get("client_id"), "name": obj.get("client_name")}
    entity = _entity_for(client_obj, result)
    issue = date.fromisoformat(str(obj.get("issue_date"))[:10]) if obj.get("issue_date") else date.today()
    sale = Sale(kind=kind, status="draft", source="qonto", qonto_emit=True, entity=entity, issue_date=issue,
                due_date=date.fromisoformat(obj["due_date"][:10]) if obj.get("due_date") else None,
                validity_date=date.fromisoformat(obj["expiry_date"][:10]) if obj.get("expiry_date") else None,
                vat_mode=vat_mode_for(issue))
    sale.lines = _lines_from(obj, sale)
    compute(sale)
    apply(sale, obj)
    db.session.add(sale)
    db.session.flush()
    try:
        sale_issue.record_external(sale, obj["number"])
    except SaleError as exc:
        sale.qonto_error = f"Importée de Qonto, non comptabilisée : {exc.message}"
        result["errors"].append(f"{obj.get('number')} : {exc.message}")
    return sale


def sync(progress_cb=None) -> dict:
    """Lit Qonto (clients, produits, devis, factures) depuis le dernier passage ; aucune écriture
    dans Qonto. Factures créées dans Qonto : importées et comptabilisées ; statuts mis à jour ; PDF
    manquants récupérés."""
    if not available():
        raise RuntimeError(external_config.required_message("qonto", "sales"))
    api = client()
    cursor = _cursor()
    since = cursor.synced_at - timedelta(minutes=5) if cursor.synced_at else None
    started = datetime.utcnow()
    result = {"clients_linked": 0, "products_created": 0, "invoices_created": 0, "invoices_updated": 0,
              "quotes_created": 0, "quotes_updated": 0, "pdfs": 0, "errors": []}
    updated = {"filter[updated_at_from]": since.strftime("%Y-%m-%dT%H:%M:%S.000Z")} if since else {}

    for page in api.iter_pages("/clients", "clients", params=updated):
        for qonto_client in page:
            _entity_for(qonto_client, result)
        db.session.commit()
    for page in api.iter_pages("/products", "products"):
        for product in page:
            if Product.query.filter_by(qonto_product_id=product.get("id")).first():
                continue
            existing = Product.query.filter_by(name=(product.get("title") or "")[:200]).first()
            if existing is not None:
                existing.qonto_product_id = product["id"]
                continue
            account = default_sale_account()
            db.session.add(Product(name=(product.get("title") or "Produit Qonto")[:200], kind="sale",
                                   sale_account_id=account.id if account else None,
                                   vat_rate_bp=int(Decimal(str(product.get("vat_rate") or "0")) * 10000),
                                   sale_price_cents=_cents(product.get("unit_price")), unit=product.get("unit"),
                                   description=product.get("description"),
                                   nature="goods" if product.get("type") == "good" else "services",
                                   qonto_product_id=product.get("id")))
            result["products_created"] += 1
        db.session.commit()
    for page in api.iter_pages("/quotes", "quotes", params={"filter[created_at_from]": since.strftime("%Y-%m-%dT%H:%M:%S.000Z")} if since else None):
        for obj in page:
            sale = Sale.query.filter_by(qonto_id=obj.get("id")).first()
            if sale is None:
                sale = _import(obj, "quote", result, api)
                result["quotes_created"] += 1
            elif sale.status != "invoiced":
                status = QUOTE_STATUSES.get(obj.get("status"))
                if status and sale.status != status:
                    sale.status = status
                    result["quotes_updated"] += 1
                apply(sale, obj)
            db.session.commit()
    for page in api.iter_pages("/client_invoices", "client_invoices", params=updated):
        for obj in page:
            if obj.get("status") == "draft":
                continue  # brouillon Qonto : rien à comptabiliser
            sale = Sale.query.filter_by(qonto_id=obj.get("id")).first()
            if sale is None:
                _import(obj, "invoice", result, api)
                result["invoices_created"] += 1
            else:
                before = sale.qonto_status
                apply(sale, obj)
                if obj.get("status") == "canceled" and sale.status not in ("canceled",) and before != "canceled":
                    sale.qonto_error = "Annulée dans Qonto : passez l'avoir correspondant (ou synchronisez les avoirs)."
                if before != sale.qonto_status:
                    result["invoices_updated"] += 1
            db.session.commit()
    for sale in Sale.query.filter(Sale.qonto_id.isnot(None), Sale.pdf_path.is_(None), Sale.number.isnot(None)).limit(50):
        try:
            if fetch_pdf(sale, api):
                result["pdfs"] += 1
            db.session.commit()
        except QontoError as exc:
            db.session.rollback()
            result["errors"].append(f"PDF {sale.number} : {exc}")
    cursor = _cursor()
    cursor.synced_at = started
    db.session.commit()
    return result


def start_sync(app):
    from app.models.sync_job import SYNC_KIND_QONTO_SALES
    from app.services import integrations, sync_jobs

    def work(job_id):
        return sync(progress_cb=sync_jobs.progress_callback(job_id))

    def error_message(exc):
        if type(exc) is RuntimeError:
            return str(exc)
        return integrations.mask_secrets("qonto", integrations.describe_error("qonto", exc))

    return sync_jobs.start(app, SYNC_KIND_QONTO_SALES, work, message="Synchronisation des ventes Qonto…",
                           error_message=error_message)


def latest_job():
    from app.models import SyncJob
    from app.models.sync_job import SYNC_KIND_QONTO_SALES

    return (SyncJob.query.filter_by(kind=SYNC_KIND_QONTO_SALES)
            .order_by(SyncJob.started_at.desc(), SyncJob.id.desc()).first())
