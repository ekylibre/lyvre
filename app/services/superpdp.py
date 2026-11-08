"""Facture électronique par SUPER PDP (lot PDP1, claudedocs/design_superpdp.md).

- **Une seule plateforme agréée** par entreprise à un instant donné : SUPER PDP et Qonto (partie « Ventes ») ne
  peuvent pas être actives ensemble (`external_config.PDP_ROLES`, refus à l'activation ou au cochage).
- **Envoi** (partie « Envoi des factures de vente ») : une facture ou un avoir émis, au PDF Factur-X conforme, est
  déposé par `POST /invoices` ; l'identifiant SUPER PDP et le dernier statut sont gardés sur la pièce. Le dépôt est
  synchrone, la validation et l'acheminement asynchrones : les statuts se lisent ensuite.
- **Réception** (partie « Réception des factures d'achat ») : `GET /invoices?direction=in`, à partir de la dernière
  facture reçue (séquence strictement croissante, documentation « Synchronisation ») ; chaque fichier est lu
  (Factur-X, CII, UBL) et devient une facture d'achat (source `superpdp`), fournisseur rattaché, lignes par défaut
  comme pour Qonto, fichier rangé avec les pièces. Une autofacture reçue (type 389) n'est pas un achat : signalée.
- **Statuts** : pour chaque pièce transmise encore en cours, `GET /invoice_events?invoice_id=` ; le dernier statut
  (`api:*`, `fr:*`) est gardé avec son libellé.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.extensions import db
from app.models import Purchase, Sale
from app.services import external_config

STATUS_LABELS = {
    "api:uploaded": "Déposée", "api:invalid": "Invalide", "api:validated": "Validée", "api:sent": "Transmise",
    "api:rejected": "Rejetée", "api:received": "Reçue", "api:acknowledged": "Prise en compte", "api:accepted": "Acceptée",
    "fr:200": "Déposée", "fr:201": "Émise", "fr:202": "Reçue", "fr:203": "Mise à disposition", "fr:204": "Prise en charge",
    "fr:205": "Approuvée", "fr:206": "Approuvée partiellement", "fr:207": "En litige", "fr:208": "Suspendue",
    "fr:209": "Complétée", "fr:210": "Refusée", "fr:211": "Paiement transmis", "fr:212": "Encaissée",
    "fr:213": "Rejetée", "fr:501": "Irrecevable",
}
FINAL = {"api:invalid", "api:rejected", "fr:210", "fr:212", "fr:213", "fr:501"}
ERRORS = {"api:invalid", "api:rejected", "fr:213", "fr:501"}


class PdpError(RuntimeError):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.message, self.status = message, status


def label(code: str | None) -> str | None:
    return STATUS_LABELS.get(code, code) if code else None


def can_send() -> bool:
    return external_config.scope_available("superpdp", "send")


def can_receive() -> bool:
    return external_config.scope_available("superpdp", "receive")


def _client():
    from app.services.superpdp_client import from_app_config
    return from_app_config()


def _last_status(events: list[dict]) -> tuple[str | None, str | None]:
    if not events:
        return None, None
    last = max(events, key=lambda e: (e.get("created_at") or "", int(e.get("id") or 0)))
    return last.get("status_code"), last.get("status_text")


# ------------------------------------------------------------------ envoi


def sendable(sale: Sale) -> str | None:
    """Motif d'un refus d'envoi, ou None."""
    from app.services.sale_documents import facturx_warning
    if sale.kind not in ("invoice", "credit_note") or sale.status == "draft" or not sale.number:
        return "Seules les factures et avoirs émis se transmettent."
    if sale.pdp_id:
        return f"Pièce déjà transmise à SUPER PDP (n° {sale.pdp_id})."
    if sale.qonto_emit:
        return "Pièce émise par Qonto : transmise par Qonto."
    warning = facturx_warning(sale)
    if warning:
        return f"PDF Factur-X impossible : {warning}"
    return None


def send(sale: Sale, client=None) -> Sale:
    """Dépose la facture Factur-X de la pièce (sans commit) ; l'erreur est gardée sur la pièce et levée."""
    from app.services.sale_documents import render_pdf
    from app.services.superpdp_client import SuperPdpError
    from app.tenant import current_instance
    if not can_send():
        raise PdpError(external_config.required_message("superpdp", "send"))
    refusal = sendable(sale)
    if refusal:
        raise PdpError(refusal)
    client = client or _client()
    inst = current_instance()
    external_id = f"lyvre-{getattr(inst, 'slug', 'x')}-sale-{sale.id}"
    try:
        body = client.send_invoice(render_pdf(sale), external_id)
    except SuperPdpError as exc:
        sale.pdp_error = str(exc)[:2000]
        raise PdpError(f"SUPER PDP a refusé la facture {sale.number} : {exc}", 502) from None
    code, _text = _last_status(body.get("events") or [])
    sale.pdp_id, sale.pdp_status = str(body["id"]), code or "api:uploaded"
    sale.pdp_error, sale.pdp_sent_at = None, datetime.utcnow()
    return sale


# ------------------------------------------------------------------ statuts


def refresh_statuses(client, result: dict) -> None:
    for sale in Sale.query.filter(Sale.pdp_id.isnot(None)):
        if sale.pdp_status in FINAL:
            continue
        events = client.events_of(int(sale.pdp_id))
        code, text = _last_status(events)
        if code and code != sale.pdp_status:
            sale.pdp_status = code
            sale.pdp_error = text if code in ERRORS else None
            result["statuses"] += 1


# ------------------------------------------------------------------ réception


def _last_received() -> int | None:
    ids = [int(p) for (p,) in db.session.query(Purchase.pdp_id).filter(Purchase.pdp_id.isnot(None)) if str(p).isdigit()]
    return max(ids) if ids else None


def _store_file(purchase: Purchase, content: bytes, name: str) -> None:
    from app.services import attachments
    kind = attachments.sniff(content[:16]) or (("application/xml", ".xml") if content.lstrip()[:1] == b"<" else None)
    if kind is None:
        return
    day = purchase.issue_date or datetime.utcnow().date()
    relative = Path("achats", f"{day.year:04d}", f"{day.month:02d}", f"superpdp-{purchase.pdp_id}-{attachments.safe_name(name, kind[1])}")
    target = attachments.instance_dir() / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    purchase.attachment_path, purchase.attachment_name = relative.as_posix(), name[:200]
    purchase.attachment_mime, purchase.attachment_size = kind[0], len(content)


def import_received(item: dict, content: bytes, result: dict) -> Purchase | None:
    """Facture reçue → facture d'achat (sans commit). Autofacture et fichier illisible : signalés."""
    from app.services import catalog, einvoice_reader, purchase_settlement, purchase_sync
    pdp_id = str(item["id"])
    if Purchase.query.filter_by(pdp_id=pdp_id).first() is not None:
        return None
    try:
        inv = einvoice_reader.read(content)
    except einvoice_reader.EinvoiceError as exc:
        result["errors"].append(f"Facture SUPER PDP n° {pdp_id} illisible : {exc}")
        return None
    if inv.self_billed:
        result["self_billed"] += 1
        result["errors"].append(f"Autofacture {inv.number} reçue (SUPER PDP n° {pdp_id}) : à déposer dans Ventes › Autofactures.")
        return None
    seller = inv.seller
    total = inv.total_cents if inv.total_cents is not None else (inv.untaxed_cents or 0) + (inv.tax_cents or 0)
    code, _text = _last_status(item.get("events") or [])
    purchase = Purchase(
        source="superpdp", pdp_id=pdp_id, pdp_status=code, supplier_name=(seller.name or "")[:200] or None,
        supplier_vat=purchase_sync.normalize_vat(seller.vat_number), supplier_siret=purchase_sync.normalize_siret(seller.siret),
        invoice_number=(inv.number or "")[:100] or None, issue_date=inv.issue_date, due_date=inv.due_date,
        currency=(inv.currency or "EUR")[:3], total_cents=abs(total), untaxed_cents=abs(inv.untaxed_cents) if inv.untaxed_cents is not None else None,
        tax_cents=abs(inv.tax_cents) if inv.tax_cents is not None else None,
        payable_cents=abs(inv.payable_cents) if inv.payable_cents is not None else None,
        is_credit_note=inv.credit, is_einvoice=True, source_updated_at=datetime.utcnow())
    db.session.add(purchase)
    entity = purchase_sync.match_entity(purchase)
    if entity is not None:
        purchase.entity = entity
    else:
        result["without_supplier"] += 1
    breakdown = sorted(((t.rate_bp, abs(t.tax_cents)) for t in inv.taxes), key=lambda row: row[0] == 0)
    purchase.lines = purchase_sync.default_lines(purchase, catalog.product_for(purchase.entity), breakdown)
    db.session.flush()
    _store_file(purchase, content, f"{inv.number or pdp_id}{'.pdf' if content.startswith(b'%PDF') else '.xml'}")
    purchase_settlement.link_invoice(purchase)
    result["created"] += 1
    return purchase


def receive(client, result: dict, progress=None) -> None:
    after = _last_received()
    while True:
        page = client.invoices("in", starting_after_id=after)
        items = page.get("data") or []
        for item in items:
            result["read"] += 1
            content, _mime = client.download(int(item["id"]))
            import_received(item, content, result)
            db.session.commit()
            after = int(item["id"])
            if progress:
                progress(result["read"], None, f"{result['read']} facture(s) reçue(s) lue(s)")
        if not page.get("has_after") or not items:
            break


def new_result() -> dict:
    return {"read": 0, "created": 0, "without_supplier": 0, "self_billed": 0, "statuses": 0, "errors": []}


def sync(client=None, progress=None) -> dict:
    """Réception des factures d'achat et statuts des pièces transmises (commit par facture)."""
    if not external_config.is_available("superpdp"):
        raise RuntimeError(external_config.unavailable_message("superpdp") or "Intégration SUPER PDP indisponible.")
    client = client or _client()
    result = new_result()
    if can_receive():
        receive(client, result, progress)
    if can_send():
        refresh_statuses(client, result)
    db.session.commit()
    return result


def start_sync(app):
    from app.models.sync_job import SYNC_KIND_SUPERPDP
    from app.services import sync_jobs

    def work(job_id):
        return sync(progress=sync_jobs.progress_callback(job_id))
    return sync_jobs.start(app, SYNC_KIND_SUPERPDP, work, message="Lecture de SUPER PDP…")


def directory_summary(client) -> str:
    """Adresses de réception (lignes d'annuaire) : créées, en attente ou en erreur (portabilité en cours)."""
    entries = [e for e in client.directory_entries() if not e.get("is_replyto")]
    if not entries:
        return "Aucune adresse de réception dans l'annuaire : les factures d'achat ne vous parviendront pas par SUPER PDP."
    states = {"created": "active", "pending": "en attente", "error": "en erreur (portabilité depuis une autre plateforme ?)"}
    return "Adresses de réception : " + ", ".join(f"{e.get('identifier')} {states.get(e.get('status'), e.get('status'))}"
                                                 for e in entries) + "."

