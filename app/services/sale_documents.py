"""PDF des ventes (lot S1) : facture ou avoir émis en PDF/A-3 avec Factur-X (EN 16931), brouillon
en PDF simple marqué « BROUILLON ». Le PDF émis est conservé avec les pièces de l'instance
(`ventes/AAAA/<numéro>.pdf`) et n'est plus régénéré."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from flask import render_template

from app.models import Sale
from app.models.sale import OPERATION_TYPES
from app.services import billing, einvoice, organization, vat_codes
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


def _exemption(sale: Sale, line) -> dict | None:
    """Lot T2 : mention et catégorie d'une ligne de vente sans TVA française (client UE, hors UE)."""
    if sale.vat_mode == "none" or line.vat_rate_bp:
        return None
    return vat_codes.exemption(vat_codes.sale_exemption_code(sale, line.nature))


def _factur_x_exemption(sale: Sale, line) -> tuple[str, str, str] | None:
    exemption = _exemption(sale, line)
    return (exemption["category"], exemption["reason_code"], exemption["reason"]) if exemption else None


def exemption_mentions(sale: Sale) -> list[str]:
    mentions = []
    for line in sale.lines:
        exemption = _exemption(sale, line)
        if exemption and exemption["mention"] not in mentions:
            mentions.append(exemption["mention"])
    return mentions


# ------------------------------------------------------------------ lot AG10.e : RFA, B2C

RFA_PARAM = "vat.rfa.facturx_exemption"


def is_b2c(sale: Sale) -> bool:
    """Client particulier : la facture porte la note BAR = B2C."""
    return (sale.client or {}).get("person_kind") == "individual"


def is_rfa(sale: Sale) -> bool:
    from app.services import tax_profile
    return sale.vat_mode == "none" and tax_profile.current_value("vat_regime", sale.issue_date) == "rfa"


def rfa_exemption(sale: Sale) -> dict | None:
    """Motif d'exonération Factur-X d'un producteur au remboursement forfaitaire : paramètre daté, vide tant qu'il
    n'est pas sourcé (design_efacturation_agricole.md § 5). `{code, reason, mention}`."""
    from app.services import reg_params
    value = reg_params.value(RFA_PARAM, sale.issue_date, default=None) if sale.issue_date else None
    return value if isinstance(value, dict) and value.get("code") and value.get("reason") else None


def facturx_warning(sale: Sale) -> str | None:
    """Pourquoi la pièce n'a pas (ou n'aura pas) de Factur-X ; None si elle en a un."""
    if sale.kind not in ("invoice", "credit_note") or sale.self_billed:
        return None
    if is_rfa(sale) and rfa_exemption(sale) is None:
        return ("Producteur au remboursement forfaitaire : le motif d'exonération à porter dans la facture électronique "
                "n'est pas encore sourcé (paramètre réglementaire « vat.rfa.facturx_exemption »). Le PDF est produit "
                "sans Factur-X et sans mention d'exonération.")
    return None


def exempt_mention(sale: Sale) -> str | None:
    if sale.vat_mode != "none":
        return None
    if is_rfa(sale):
        exemption = rfa_exemption(sale)
        return exemption.get("mention") or exemption["reason"] if exemption else None
    return einvoice.FRANCHISE[1] + "."


def render_html(sale: Sale) -> str:
    settings, org = billing.get(), organization.get()
    logo = billing.logo_file(settings)
    client = sale.client
    title = TITLES.get(sale.kind, "Facture")
    return render_template(
        "sales/document.html", sale=sale, org=org, settings=settings, client=client, title=title,
        rcs_mention=organization.rcs_mention(org),
        invoice=sale.invoice if sale.kind == "credit_note" else None,
        logo_src=logo.as_uri() if logo else None, money=euros, date=_date, qty=_qty, rate=_rate,
        vat_rows=vat_rows(sale), exempt=sale.vat_mode == "none", exempt_mention=exempt_mention(sale),
        exemption_mentions=exemption_mentions(sale),
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
                              vat_number=org.vat_number),
        buyer=einvoice.Party(client["name"], address1=client.get("address_line1"), address2=client.get("address_line2"),
                             postcode=client.get("postal_code"), city=client.get("city"),
                             siren=client.get("siren"), vat_number=client.get("vat_number")),
        lines=[einvoice.Line(l.label, l.quantity_milli, l.unit_price_cents, l.untaxed_cents, l.vat_rate_bp,
                             unit=UNIT_CODES.get(l.unit or "", "C62"), description=l.description,
                             exemption=_factur_x_exemption(sale, l))
               for l in sale.lines],
        vat_exempt=sale.vat_mode == "none", vat_on_receipts=sale.vat_mode == "receipts",
        iban=settings.iban if sale.kind == "invoice" else None,
        preceding_number=invoice.number if invoice else None, preceding_date=invoice.issue_date if invoice else None,
        period_start=sale.service_start, period_end=sale.service_end, b2c=is_b2c(sale),
        exempt_reason=((rfa_exemption(sale) or {}).get("code"), (rfa_exemption(sale) or {}).get("reason"))
        if is_rfa(sale) and rfa_exemption(sale) else None,
        notes=[sale.credit_reason] if sale.credit_reason else [])


def render_pdf(sale: Sale) -> bytes:
    """PDF de la pièce : Factur-X si elle est émise, PDF simple (brouillon) sinon."""
    html = render_html(sale)
    if sale.number and sale.kind in ("invoice", "credit_note") and facturx_warning(sale) is None:
        return einvoice.facturx_pdf(html, einvoice_document(sale))
    if sale.number and sale.kind in ("invoice", "credit_note"):
        return einvoice.pdf_a3(html)  # RFA sans motif sourcé : PDF/A sans XML (lot AG10.e)
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
