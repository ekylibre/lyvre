"""PDF des ventes (lot S1) : facture ou avoir émis en PDF/A-3 avec Factur-X (EN 16931), brouillon
en PDF simple marqué « BROUILLON ». Le PDF émis est conservé avec les pièces de l'instance
(`ventes/AAAA/<numéro>.pdf`) et n'est plus régénéré."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from flask import render_template

from app.models import Sale
from app.models.sale import OPERATION_TYPES
from app.services import billing, einvoice, organization
from app.services.attachments import instance_dir
from app.utils.money import euros

TITLES = {"invoice": "Facture", "credit_note": "Avoir", "quote": "Devis"}
UNIT_CODES = {"heure": "HUR", "jour": "DAY", "mois": "MON", "kg": "KGM", "m²": "MTK", "forfait": "C62", "unité": "C62"}


def _date(value) -> str:
    return value.strftime("%d/%m/%Y") if value else ""


def _qty(milli: int) -> str:
    text = f"{Decimal(milli) / 1000:f}".rstrip("0").rstrip(".") if milli % 1000 else str(milli // 1000)
    return text.replace(".", ",")


def _rate(bp: int) -> str:
    text = f"{Decimal(bp) / 100:f}".rstrip("0").rstrip(".") if bp % 100 else str(bp // 100)
    return f"{text.replace('.', ',')} %"


def vat_rows(sale: Sale) -> list[dict]:
    rows: dict[int, dict] = {}
    for line in sale.lines:
        row = rows.setdefault(line.vat_rate_bp, {"rate": line.vat_rate_bp, "base": 0, "tax": 0})
        row["base"] += line.untaxed_cents
        row["tax"] += line.vat_cents
    return [] if sale.vat_mode == "none" else [r for _, r in sorted(rows.items()) if r["rate"]]


def render_html(sale: Sale) -> str:
    settings, org = billing.get(), organization.get()
    logo = billing.logo_file(settings)
    client = sale.client
    title = TITLES.get(sale.kind, "Facture")
    return render_template(
        "sales/document.html", sale=sale, org=org, settings=settings, client=client, title=title,
        invoice=sale.invoice if sale.kind == "credit_note" else None,
        logo_src=logo.as_uri() if logo else None, money=euros, date=_date, qty=_qty, rate=_rate,
        vat_rows=vat_rows(sale), exempt=sale.vat_mode == "none",
        has_discount=any(l.discount_bp for l in sale.lines),
        has_services=any(l.nature == "services" for l in sale.lines),
        is_business=client.get("person_kind") != "individual",
        operation=OPERATION_TYPES.get(sale.operation_type, ""),
        iban=" ".join((settings.iban or "")[i:i + 4] for i in range(0, len(settings.iban or ""), 4)),
        default_penalty=billing.DEFAULT_LATE_PENALTY,
        footer_line=f"{title} {sale.number or 'brouillon'} — {org.name}")


def einvoice_document(sale: Sale) -> einvoice.Document:
    settings, org = billing.get(), organization.get()
    client = sale.client
    invoice = sale.invoice if sale.kind == "credit_note" else None
    return einvoice.Document(
        number=sale.number, issue_date=sale.issue_date, due_date=sale.due_date if sale.kind == "invoice" else None,
        type_code=einvoice.CREDIT_NOTE if sale.kind == "credit_note" else einvoice.INVOICE,
        seller=einvoice.Party(org.name, address1=org.address_line1, address2=org.address_line2,
                              postcode=org.postal_code, city=org.city, siren=org.siren,
                              vat_number=settings.vat_number),
        buyer=einvoice.Party(client["name"], address1=client.get("address_line1"), address2=client.get("address_line2"),
                             postcode=client.get("postal_code"), city=client.get("city"),
                             siren=client.get("siren"), vat_number=client.get("vat_number")),
        lines=[einvoice.Line(l.label, l.quantity_milli, l.unit_price_cents, l.untaxed_cents, l.vat_rate_bp,
                             unit=UNIT_CODES.get(l.unit or "", "C62"), description=l.description)
               for l in sale.lines],
        vat_exempt=sale.vat_mode == "none", vat_on_receipts=sale.vat_mode == "receipts",
        iban=settings.iban if sale.kind == "invoice" else None,
        preceding_number=invoice.number if invoice else None, preceding_date=invoice.issue_date if invoice else None,
        period_start=sale.service_start, period_end=sale.service_end,
        notes=[sale.credit_reason] if sale.credit_reason else [])


def render_pdf(sale: Sale) -> bytes:
    """PDF de la pièce : Factur-X si elle est émise, PDF simple (brouillon) sinon."""
    html = render_html(sale)
    if sale.number and sale.kind in ("invoice", "credit_note"):
        return einvoice.facturx_pdf(html, einvoice_document(sale))
    from weasyprint import HTML
    return HTML(string=html).write_pdf()


def store_pdf(sale: Sale) -> None:
    folder = instance_dir() / "ventes" / str(sale.issue_date.year)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{sale.number}.pdf"
    path.write_bytes(render_pdf(sale))
    sale.pdf_path = str(path.relative_to(instance_dir()))


def pdf_file(sale: Sale) -> Path | None:
    if not sale.pdf_path:
        return None
    path = (instance_dir() / sale.pdf_path).resolve()
    return path if path.is_relative_to(instance_dir().resolve()) and path.is_file() else None


def filename(sale: Sale) -> str:
    return f"{TITLES.get(sale.kind, 'Facture').lower()}-{sale.number or f'brouillon-{sale.id}'}.pdf"
