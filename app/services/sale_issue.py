"""Émission des ventes (lot S1) : numéro de la série de l'application, écriture VE et PDF Factur-X
dans une seule transaction (échec → rien d'enregistré, aucun numéro consommé) ; avoir sur une
facture émise ; envoi manuel par email (SMTP), PDF joint."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from sqlalchemy import func, update

from app.extensions import db
from app.models import Sale, SaleCounter, SaleEmail, SaleLine
from app.models.sale import SERIES
from app.services import billing, organization, sale_documents, sale_posting, sale_settlement
from app.services.ledger import LedgerError
from app.services.sale_entry import SaleError, client_snapshot, compute, fiscal_year_for, json_snapshot, vat_mode_for
from app.utils.money import euros

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_BATCH = 50


# ------------------------------------------------------------------ numérotation

def next_number(kind: str, year: int) -> tuple[str, int]:
    """Numéro suivant de la série, réservé dans la transaction en cours (verrou d'écriture sur le
    compteur) : annulé avec elle si l'émission échoue, donc sans trou."""
    series = SERIES[kind]
    updated = db.session.execute(update(SaleCounter).where(SaleCounter.series == series, SaleCounter.year == year)
                                 .values(last_number=SaleCounter.last_number + 1))
    if updated.rowcount == 0:
        db.session.add(SaleCounter(series=series, year=year, last_number=1))
        db.session.flush()
    seq = db.session.query(SaleCounter.last_number).filter_by(series=series, year=year).scalar()
    return f"{series}-{year}-{seq:04d}", seq


# ------------------------------------------------------------------ émission

def credited_cents(invoice: Sale, exclude_id=None) -> int:
    query = db.session.query(func.coalesce(func.sum(Sale.total_cents), 0)).filter(
        Sale.kind == "credit_note", Sale.invoice_id == invoice.id, Sale.status != "draft")
    if exclude_id:
        query = query.filter(Sale.id != exclude_id)
    return int(query.scalar() or 0)


def issue_problems(sale: Sale) -> list[str]:
    """Ce qui empêche d'émettre la pièce (liste vide : émission possible)."""
    problems = []
    if sale.status != "draft":
        return ["Pièce déjà émise."]
    if sale.kind not in ("invoice", "credit_note", "quote"):
        return ["Type de pièce non émissible."]
    fy = fiscal_year_for(sale.issue_date)
    if sale.kind == "quote":
        pass  # un devis n'est pas comptabilisé
    elif fy is None:
        problems.append(f"Aucun exercice ne couvre le {sale.issue_date:%d/%m/%Y}.")
    elif fy.closed:
        problems.append(f"L'exercice « {fy.label} » est clôturé.")
    vat_mode = vat_mode_for(sale.issue_date)
    if not sale.qonto_emit:  # pièce Qonto : mentions et numéro portés par Qonto
        problems += [f"Mention manquante : {r['label']}." for r in billing.readiness(vat_liable=vat_mode != "none") if not r["ok"]]
    client = client_snapshot(sale.entity)
    if not (client["address_line1"] and client["postal_code"] and client["city"]):
        problems.append(f"Adresse du client « {sale.entity.name} » incomplète (fiche du tiers).")
    if not sale.lines:
        problems.append("Aucune ligne.")
    missing = [str(i) for i, line in enumerate(sale.lines, start=1) if not line.account_id]
    if missing:
        problems.append(f"Compte de vente manquant (ligne {', '.join(missing)}).")
    if sale.total_cents <= 0:
        problems.append("Montant nul ou négatif.")
    if sale.kind == "credit_note":
        invoice = sale.invoice
        if invoice is None or invoice.status in ("draft", "canceled"):
            problems.append("Facture d'origine non émise ou annulée.")
        elif sale.total_cents > invoice.total_cents - credited_cents(invoice, sale.id):
            problems.append("L'avoir dépasse le montant restant de la facture.")
    last = db.session.query(func.max(Sale.issue_date)).filter(
        Sale.kind == sale.kind, Sale.source == "app", Sale.series_year == sale.issue_date.year,
        Sale.number.isnot(None)).scalar()
    if last and sale.issue_date < last:
        problems.append(f"Date antérieure à la dernière pièce émise de la série ({last:%d/%m/%Y}).")
    return problems


def issue(sale: Sale) -> Sale:
    """Émet un brouillon : numéro, client figé, écriture VE, PDF Factur-X ; un seul commit.
    Case « Émettre avec Qonto » : la pièce est créée (et finalisée) dans Qonto, qui donne le numéro."""
    sale.vat_mode = vat_mode_for(sale.issue_date)
    compute(sale)
    problems = issue_problems(sale)
    if problems:
        db.session.rollback()
        raise SaleError(" ".join(problems), status=409)
    if sale.qonto_emit:
        return _issue_with_qonto(sale)
    written = None
    try:
        sale.number, sale.series_seq = next_number(sale.kind, sale.issue_date.year)
        sale.series_year = sale.issue_date.year
        sale.client_snapshot = json_snapshot(sale.entity)
        sale.status, sale.issued_at = "issued", datetime.utcnow()
        if sale.kind != "quote":  # un devis n'a pas d'écriture
            sale_posting.post(sale, fiscal_year_for(sale.issue_date))
        sale_documents.store_pdf(sale)
        written = sale_documents.pdf_file(sale)
        # credited_cents compte déjà cet avoir (émis ci-dessus, vidé dans la session par la requête).
        if sale.kind == "credit_note" and credited_cents(sale.invoice) >= sale.invoice.total_cents:
            sale.invoice.status = "canceled"  # avoirs = montant de la facture : elle est annulée
        elif sale.kind == "credit_note":
            sale_settlement.refresh_status(sale.invoice)  # le restant dû baisse (payée si soldée)
        if sale.kind == "credit_note":
            sale_settlement._letter([sale])  # noqa: SLF001 — avoir lettré avec sa facture (F3)
        db.session.commit()
    except LedgerError as exc:
        db.session.rollback()
        _discard(written)
        raise SaleError(str(exc), status=409) from None
    except Exception:
        db.session.rollback()
        _discard(written)
        raise
    return sale


def _issue_with_qonto(sale: Sale) -> Sale:
    from app.services import qonto_sales
    from app.services.qonto_client import QontoError

    try:
        obj = qonto_sales.emit(sale)
    except QontoError as exc:
        db.session.rollback()
        raise SaleError(f"Qonto a refusé la pièce : {exc}", status=409) from None
    try:
        record_external(sale, obj["number"], obj)
    except Exception as exc:
        # Pièce finalisée dans Qonto mais non comptabilisée : on garde son identifiant (elle sera
        # reprise à la synchronisation) et on le dit.
        db.session.rollback()
        sale = db.session.get(Sale, sale.id)
        qonto_sales.apply(sale, obj)
        sale.qonto_error = f"Émise dans Qonto (n° {obj['number']}) mais non comptabilisée : {exc}"
        db.session.commit()
        raise SaleError(sale.qonto_error, status=409) from None
    return sale


def record_external(sale: Sale, number: str, obj: dict | None = None) -> Sale:
    """Pièce numérotée par Qonto (émise depuis l'application ou importée) : client figé, écriture VE
    (sauf devis), PDF Qonto s'il est prêt ; commit."""
    from app.services import qonto_sales

    if Sale.query.filter(Sale.kind == sale.kind, Sale.number == number, Sale.id != sale.id).first():
        raise SaleError(f"Le numéro {number} existe déjà.", status=409)
    sale.number, sale.series_year, sale.series_seq = number, None, None
    sale.client_snapshot = json_snapshot(sale.entity)
    sale.status, sale.issued_at, sale.qonto_error = "issued", datetime.utcnow(), None
    if obj:
        qonto_sales.apply(sale, obj)
        if sale.kind == "quote" and obj.get("status") in qonto_sales.QUOTE_STATUSES:
            sale.status = qonto_sales.QUOTE_STATUSES[obj["status"]]
    if sale.kind != "quote":
        fy = fiscal_year_for(sale.issue_date)
        if fy is None or fy.closed:
            raise SaleError(f"Aucun exercice ouvert ne couvre le {sale.issue_date:%d/%m/%Y}.", status=409)
        try:
            sale_posting.post(sale, fy)
        except LedgerError as exc:
            raise SaleError(str(exc), status=409) from None
    if sale.kind == "credit_note" and credited_cents(sale.invoice) >= sale.invoice.total_cents:
        sale.invoice.status = "canceled"
    elif sale.kind == "credit_note":
        sale_settlement.refresh_status(sale.invoice)
    if sale.kind == "credit_note":
        sale_settlement._letter([sale])  # noqa: SLF001
    db.session.commit()
    try:
        if qonto_sales.fetch_pdf(sale):
            db.session.commit()
    except Exception:  # noqa: BLE001 — PDF produit en différé par Qonto : récupéré plus tard
        db.session.rollback()
    return sale


def _discard(path) -> None:
    if path is not None:
        path.unlink(missing_ok=True)


# ------------------------------------------------------------------ devis

def quote_status(quote: Sale) -> str:
    """Statut affiché d'un devis : « expiré » s'il est émis et sa validité passée."""
    if quote.status == "issued" and quote.validity_date and quote.validity_date < date.today():
        return "expired"
    return quote.status


def set_quote_status(quote: Sale, status: str) -> Sale:
    """Accepté ou refusé (ou retour à « envoyé ») pour un devis émis non facturé."""
    if quote.kind != "quote" or quote.status in ("draft", "invoiced"):
        raise SaleError("Seul un devis émis et non facturé change de statut.", status=409)
    if status not in ("issued", "accepted", "refused"):
        raise SaleError("Statut de devis inconnu.", "status")
    quote.status = status
    db.session.commit()
    return quote


def to_invoice(quote: Sale) -> Sale:
    """Brouillon de facture reprenant le devis (client, lignes, textes) ; le devis est accepté puis
    « facturé ». Un devis facturé peut donner d'autres factures (solde, complément)."""
    if quote.kind != "quote" or quote.status not in ("issued", "accepted", "invoiced"):
        raise SaleError("Seul un devis émis (ou accepté) se transforme en facture.", status=409)
    invoice = Sale(kind="invoice", status="draft", source="app", entity=quote.entity, quote_id=quote.id,
                   issue_date=date.today(), operation_type=quote.operation_type,
                   service_start=quote.service_start, service_end=quote.service_end,
                   purchase_order=quote.purchase_order or (f"Devis {quote.number}" if quote.number else None),
                   terms=quote.terms, header=quote.header, footer=quote.footer)
    invoice.due_date = date.today() + timedelta(days=billing.get().payment_terms_days or 0)
    invoice.vat_mode = vat_mode_for(invoice.issue_date)
    invoice.lines = [SaleLine(position=i, product_id=l.product_id, label=l.label, description=l.description,
                              quantity_milli=l.quantity_milli, unit=l.unit, unit_price_cents=l.unit_price_cents,
                              discount_bp=l.discount_bp, vat_rate_bp=l.vat_rate_bp, account_id=l.account_id,
                              project_id=l.project_id, nature=l.nature) for i, l in enumerate(quote.lines)]
    compute(invoice)
    quote.status = "invoiced"
    db.session.add(invoice)
    db.session.commit()
    return invoice


def quote_invoices(quote: Sale) -> list[Sale]:
    return Sale.query.filter_by(kind="invoice", quote_id=quote.id).order_by(Sale.id).all()


def credit_note(invoice: Sale, reason: str, line_ids=None) -> Sale:
    """Brouillon d'avoir sur une facture émise : toutes ses lignes, ou celles choisies."""
    if invoice.kind != "invoice" or invoice.status in ("draft", "canceled"):
        raise SaleError("Un avoir se fait sur une facture émise et non annulée.", status=409)
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise SaleError("Motif de l'avoir obligatoire.", "reason")
    chosen = [l for l in invoice.lines if not line_ids or l.id in set(line_ids)]
    if not chosen:
        raise SaleError("Choisissez les lignes à créditer.", "line_ids")
    note = Sale(kind="credit_note", status="draft", source="app", entity=invoice.entity, invoice_id=invoice.id,
                qonto_emit=invoice.qonto_id is not None,  # avoir d'une facture Qonto : émis par Qonto
                issue_date=max(date.today(), invoice.issue_date), operation_type=invoice.operation_type,
                credit_reason=reason[:500], vat_mode=invoice.vat_mode)
    note.lines = [SaleLine(position=i, product_id=l.product_id, label=l.label, description=l.description,
                           quantity_milli=l.quantity_milli, unit=l.unit, unit_price_cents=l.unit_price_cents,
                           discount_bp=l.discount_bp, vat_rate_bp=l.vat_rate_bp, account_id=l.account_id,
                           project_id=l.project_id, nature=l.nature) for i, l in enumerate(chosen)]
    compute(note)
    db.session.add(note)
    db.session.commit()
    return note


# ------------------------------------------------------------------ envoi

def recipients_of(sale: Sale) -> list[str]:
    emails = [sale.client.get("email") or sale.entity.email]
    emails += [e.strip() for e in (sale.entity.billing_emails or "").replace(";", ",").split(",")]
    seen = []
    for email in emails:
        if email and EMAIL.match(email) and email not in seen:
            seen.append(email)
    return seen


def message_for(sale: Sale, purpose: str = "send") -> tuple[str, str]:
    settings, org = billing.get(), organization.get()
    title = sale_documents.TITLES.get(sale.kind, "Facture")
    due = (f"Échéance : {sale.due_date:%d/%m/%Y}.\n" if sale.kind == "invoice" and sale.due_date else "")
    values = {"type": title, "type_minuscule": title.lower(), "article": "notre",
              "numero": sale.number or "", "date": f"{sale.issue_date:%d/%m/%Y}", "montant": euros(sale.total_cents),
              "echeance": due, "date_echeance": f"{sale.due_date:%d/%m/%Y}" if sale.due_date else "",
              "restant": euros(sale_settlement.due_cents(sale)), "organisation": org.name, "client": sale.entity.name}
    if purpose == "reminder":
        subject = settings.reminder_subject or billing.DEFAULT_REMINDER_SUBJECT
        body = settings.reminder_body or billing.DEFAULT_REMINDER_BODY
    else:
        subject = settings.send_subject or billing.DEFAULT_SEND_SUBJECT
        body = settings.send_body or billing.DEFAULT_SEND_BODY
    for key, value in values.items():
        subject, body = subject.replace("{" + key + "}", value), body.replace("{" + key + "}", value)
    return subject, body


def _html(body: str) -> str:
    from markupsafe import escape
    return "".join(f"<p>{escape(p).replace(chr(10), '<br>')}</p>" for p in body.strip().split("\n\n"))


def send(sales, to=None, cc=None, subject=None, body=None, purpose="send") -> dict:
    """Envoie chaque pièce émise (PDF joint) ; `to`/`subject`/`body` pour un envoi unitaire, sinon
    destinataires et message par défaut. `purpose = reminder` : relance d'une facture échue non
    soldée (message de relance, compteur de relances). Un échec n'arrête pas les autres envois."""
    from app.services.membership_reminders import _build_message, _open_smtp, smtp_settings

    if len(sales) > MAX_BATCH:
        raise SaleError(f"{MAX_BATCH} pièces au plus par envoi.", status=422)
    settings = smtp_settings() if any(not s.qonto_id for s in sales) else None
    sent, skipped, errors = 0, 0, []
    server = None
    try:
        for sale in sales:
            if sale.status == "draft" or not sale.number:
                skipped += 1
                continue
            if purpose == "reminder" and not sale_settlement.due_cents(sale):
                skipped += 1
                errors.append(f"{sale.number} : rien à relancer (soldée ou annulée).")
                continue
            recipients = list(to) if to else recipients_of(sale)
            if sale.qonto_id:  # pièce émise par Qonto : envoyée par Qonto (son PDF Factur-X)
                if not recipients:
                    skipped += 1
                    errors.append(f"{sale.number} : aucune adresse email.")
                    continue
                default_subject, default_body = message_for(sale, purpose)
                text_subject = (subject or default_subject)[:255]
                log = SaleEmail(sale=sale, purpose=purpose, channel="qonto", subject=text_subject,
                                recipients=", ".join(recipients + list(cc or [])))
                try:
                    from app.services import qonto_sales
                    qonto_sales.send(sale, recipients + list(cc or []), text_subject, body or default_body)
                    log.status = "sent"
                    if purpose == "reminder":
                        sale.reminder_count, sale.last_reminder_at = (sale.reminder_count or 0) + 1, datetime.utcnow()
                    else:
                        sale.sent_at = datetime.utcnow()
                    sent += 1
                except Exception as exc:  # noqa: BLE001 — échec isolé par pièce
                    log.status, log.error = "failed", str(exc)[:500]
                    errors.append(f"{sale.number} : {exc}")
                db.session.add(log)
                db.session.commit()
                continue
            path = sale_documents.pdf_file(sale)
            if not recipients or path is None:
                skipped += 1
                errors.append(f"{sale.number} : {'aucune adresse email' if not recipients else 'PDF introuvable'}.")
                continue
            default_subject, default_body = message_for(sale, purpose)
            text_subject = (subject or default_subject)[:255]
            message = _build_message(settings["sender"], ", ".join(recipients), text_subject, _html(body or default_body))
            if cc:
                message["Cc"] = ", ".join(cc)
            message.add_attachment(path.read_bytes(), maintype="application", subtype="pdf",
                                   filename=sale_documents.filename(sale))
            log = SaleEmail(sale=sale, purpose=purpose, channel="smtp", subject=text_subject,
                            recipients=", ".join(recipients + list(cc or [])))
            try:
                if server is None:
                    server = _open_smtp(settings)
                server.send_message(message)
                log.status = "sent"
                if purpose == "reminder":
                    sale.reminder_count, sale.last_reminder_at = (sale.reminder_count or 0) + 1, datetime.utcnow()
                else:
                    sale.sent_at = datetime.utcnow()
                sent += 1
            except Exception as exc:  # noqa: BLE001 — échec isolé par pièce
                log.status, log.error = "failed", str(exc)[:500]
                errors.append(f"{sale.number} : {exc}")
            db.session.add(log)
            db.session.commit()
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:  # noqa: BLE001 — fermeture best-effort
                pass
    return {"sent": sent, "skipped": skipped, "errors": errors}


def validate_emails(values, field) -> list[str]:
    emails = [str(v).strip() for v in (values or []) if str(v).strip()]
    bad = [e for e in emails if not EMAIL.match(e)]
    if bad:
        raise SaleError(f"Adresse email invalide : {', '.join(bad)}.", field)
    return emails
