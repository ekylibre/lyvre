"""Facture d'achat créée depuis une transaction Qonto qui porte un justificatif (paiement par carte,
prélèvement) : la pièce jointe est téléchargée de Qonto, lue (texte, Factur-X, OCR : `invoice_reader`)
et le formulaire de saisie est prérempli ; les informations de la transaction complètent ou corrigent
la lecture (montant payé, date, fournisseur). À l'enregistrement, la facture est reliée à la transaction
**avant** sa comptabilisation : son règlement (401 / banque) est passé sur cette transaction-là, jamais
sur un autre débit de même montant.
"""
from __future__ import annotations

from app.extensions import db
from app.models import BankTransaction, PurchasePayment
from app.services import attachments, purchase_entry, purchase_settlement, purchase_sync
from app.services.attachments import AttachmentError
from app.services.ledger_errors import LedgerError


class TransactionInvoiceError(LedgerError):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


def blocker(txn: BankTransaction) -> str | None:
    """Pourquoi la transaction ne peut pas donner une facture d'achat (None : elle le peut)."""
    if txn.source != "qonto":
        return "Seule une transaction Qonto porte un justificatif téléchargeable."
    if txn.amount_cents >= 0:
        return "Seul un débit (paiement) donne une facture d'achat."
    if txn.is_reversed:
        return "Transaction annulée par Qonto."
    if not txn.attachment_count:
        return "Aucun justificatif dans Qonto pour cette transaction."
    if PurchasePayment.query.filter(db.or_(PurchasePayment.bank_transaction_id == txn.id,
                                           PurchasePayment.qonto_transaction_id == txn.fitid)).first():
        return "Cette transaction règle déjà une facture d'achat."
    if not purchase_settlement._free_for_matching(txn):  # noqa: SLF001 — même règle que le rapprochement
        return "Transaction déjà rapprochée d'une écriture : défaites d'abord ce rapprochement."
    return None


def _attachment(client, txn: BankTransaction) -> tuple[bytes, str]:
    """(contenu, nom) du premier justificatif PDF ou image de la transaction."""
    tx = client.transaction(txn.fitid)
    ids = [i for i in (tx.get("attachment_ids") or []) if i]
    for attachment_id in ids:
        meta = client.attachment(attachment_id)
        url = meta.get("url") or (meta.get("probative_attachment") or {}).get("url")
        if not url:
            continue
        content = client.download(url)
        if attachments.sniff(content[:16]) is not None:
            return content, meta.get("file_name") or f"justificatif-{attachment_id}"
    raise TransactionInvoiceError("Aucun justificatif PDF, JPEG ou PNG lisible dans Qonto pour cette transaction.")


def _complete(form: purchase_entry.EntryForm, txn: BankTransaction) -> None:
    """La transaction fait foi pour le montant payé ; elle complète la date et le fournisseur."""
    from app.services.purchase_entry import fmt_cents

    paid = fmt_cents(abs(txn.amount_cents))
    read = form.values.get("total")
    if read and read != paid:
        form.warnings.append(f"Total lu sur la pièce ({read} €) différent du montant payé ({paid} €) : "
                             "vérifiez (devise, pourboire, plusieurs factures).")
        form.checks.add("total")
    elif not read:
        form.values["total"] = paid
        form.checks.add("total")
    if not form.values.get("issue_date"):
        form.values["issue_date"] = txn.transaction_date.isoformat()
        form.checks.add("issue_date")
    if not form.values.get("entity_id") or form.values.get("entity_id") == "new":
        entity = txn.entity or purchase_sync.find_supplier(name=txn.counterparty)
        if entity is not None:
            form.values["entity_id"] = str(entity.id)
            form.values.pop("new_name", None)
        elif not form.values.get("entity_id") and txn.counterparty:
            form.values["entity_id"] = "new"
            form.values["new_name"] = txn.counterparty
    if not form.rows:
        from app.services import catalog
        catalog.ensure_default_purchase_product()
        entity = txn.entity
        form.rows = purchase_entry.line_rows(purchase_entry.proposed_lines(entity, abs(txn.amount_cents), None, [], 0))


def draft(txn: BankTransaction, client=None) -> tuple[str, dict, purchase_entry.EntryForm]:
    """(jeton de la pièce en attente, métadonnées, formulaire prérempli) ; TransactionInvoiceError sinon."""
    from app.services import qonto_client

    reason = blocker(txn)
    if reason:
        raise TransactionInvoiceError(reason)
    try:
        client = client or qonto_client.from_app_config()
        content, name = _attachment(client, txn)
        token = attachments.stage_bytes(content, name)
    except AttachmentError as exc:
        raise TransactionInvoiceError(str(exc)) from None
    except qonto_client.QontoError as exc:
        raise TransactionInvoiceError(f"Qonto : {exc}", status=502) from None
    _, meta = attachments.staged(token)
    form = purchase_entry.form_from_extraction(purchase_entry.read_staged(token))
    _complete(form, txn)
    return token, meta, form


def link(purchase, txn: BankTransaction) -> None:
    """Relie la facture qui vient d'être créée à sa transaction (avant comptabilisation, sans commit)."""
    reason = blocker(txn)
    if reason:
        raise TransactionInvoiceError(reason)
    purchase.payments.append(PurchasePayment(bank_transaction=txn, origin="manual"))
