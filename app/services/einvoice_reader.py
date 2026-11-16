"""Lecture complète d'une facture électronique reçue (lot AG10.c, claudedocs/design_efacturation_agricole.md § 3).

Formats de la réforme (EN 16931) :
- **CII** (`CrossIndustryInvoice`), seul ou inséré dans un PDF **Factur-X** (fichier joint `factur-x.xml`) ;
- **UBL** (`Invoice` ou `CreditNote`).

`read(body)` renvoie un `ReceivedInvoice` : type (BT-3), numéro, dates, parties (nom, SIREN, SIRET, TVA,
adresse), lignes (désignation, quantité, unité, prix, montant HT, taux), remises et frais de pied de facture
(en lignes, pour que la somme des lignes égale la base HT), ventilation de TVA, totaux, notes. Rien n'est
enregistré ici. Montants en centimes signés, taux en points de base.

`invoice_reader.parse_facturx` reste la lecture rapide des factures d'achat (montants d'en-tête seulement).
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from app.services.invoice_reader import FACTURX_NAMES, MAX_XML_SIZE

# Codes d'unité UN/ECE (recommandation 20) usuels en agriculture → unité affichée.
UNITS = {"KGM": "kg", "TNE": "t", "DTN": "q", "LTR": "L", "HLT": "hL", "C62": "unité", "H87": "unité", "EA": "unité",
         "HUR": "heure", "DAY": "jour", "HAR": "ha", "MTK": "m²", "MTQ": "m³", "MTR": "m"}
CREDIT_TYPES = ("381", "261", "396", "532")
SELF_BILLED_TYPES = ("389",)  # BT-3, autofacture (documentation SUPER PDP, « Mandat de facturation »)


class EinvoiceError(ValueError):
    pass


@dataclass
class Party:
    name: str = ""
    siren: str | None = None
    siret: str | None = None
    vat_number: str | None = None
    address_line1: str | None = None
    postal_code: str | None = None
    city: str | None = None
    country: str | None = None


@dataclass
class Line:
    label: str
    net_cents: int
    vat_rate_bp: int = 0
    vat_category: str | None = None
    quantity: Decimal = Decimal(1)
    unit: str | None = None
    unit_price: Decimal | None = None
    item_id: str | None = None
    kind: str = "line"        # line | allowance | charge (remise ou frais de pied de facture)


@dataclass
class Tax:
    rate_bp: int
    base_cents: int
    tax_cents: int
    category: str | None = None
    exemption: str | None = None


@dataclass
class ReceivedInvoice:
    syntax: str                       # cii | ubl
    type_code: str = "380"
    number: str = ""
    issue_date: date | None = None
    due_date: date | None = None
    currency: str = "EUR"
    seller: Party = field(default_factory=Party)
    buyer: Party = field(default_factory=Party)
    lines: list[Line] = field(default_factory=list)
    taxes: list[Tax] = field(default_factory=list)
    untaxed_cents: int | None = None
    tax_cents: int | None = None
    total_cents: int | None = None
    payable_cents: int | None = None
    notes: list[tuple[str | None, str]] = field(default_factory=list)
    container: str = "xml"            # xml | pdf

    @property
    def credit(self) -> bool:
        return self.type_code in CREDIT_TYPES

    @property
    def self_billed(self) -> bool:
        return self.type_code in SELF_BILLED_TYPES


# ------------------------------------------------------------------ outils

def _local(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _kids(node, name):
    return [c for c in (node if node is not None else []) if _local(c.tag) == name]


def _at(node, *path):
    """Élément au bout du chemin d'enfants directs (noms locaux), None sinon."""
    for name in path:
        if node is None:
            return None
        node = next(iter(_kids(node, name)), None)
    return node


def _txt(node, *path) -> str | None:
    node = _at(node, *path)
    text = "".join(node.itertext()).strip() if node is not None else ""
    return text or None


def _dec(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value).strip().replace(",", "."))
    except InvalidOperation:
        return None


def _cents(value) -> int | None:
    d = _dec(value)
    return int((d * 100).quantize(Decimal("1"))) if d is not None else None


def _bp(value) -> int:
    d = _dec(value)
    return int((d * 100).quantize(Decimal("1"))) if d is not None else 0


def _date(text, compact: bool) -> date | None:
    if not text:
        return None
    raw = text.strip()
    try:
        if compact:
            return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _siren(value: str | None) -> tuple[str | None, str | None]:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 14:
        return digits[:9], digits
    if len(digits) == 9:
        return digits, None
    return None, None


def _unit(code: str | None) -> str | None:
    return UNITS.get((code or "").upper(), (code or "")[:20] or None)


# ------------------------------------------------------------------ CII

def _cii_party(node) -> Party:
    p = Party(name=(_txt(node, "Name") or "")[:200])
    for legal in (_txt(node, "SpecifiedLegalOrganization", "ID"), *(_txt(i) for i in _kids(node, "ID"))):
        siren, siret = _siren(legal)
        if siren:
            p.siren, p.siret = siren, p.siret or siret
            break
    for reg in _kids(node, "SpecifiedTaxRegistration"):
        ident = _at(reg, "ID")
        if ident is not None and ident.get("schemeID") == "VA" and ident.text:
            p.vat_number = ident.text.replace(" ", "").upper()[:30]
    addr = _at(node, "PostalTradeAddress")
    p.address_line1 = (_txt(addr, "LineOne") or "")[:200] or None
    p.postal_code = (_txt(addr, "PostcodeCode") or "")[:10] or None
    p.city = (_txt(addr, "CityName") or "")[:100] or None
    p.country = _txt(addr, "CountryID")
    return p


def _parse_cii(root) -> ReceivedInvoice:
    inv = ReceivedInvoice(syntax="cii")
    doc = _at(root, "ExchangedDocument")
    inv.number = (_txt(doc, "ID") or "")[:40]
    inv.type_code = _txt(doc, "TypeCode") or "380"
    inv.issue_date = _date(_txt(doc, "IssueDateTime", "DateTimeString"), compact=True)
    for note in _kids(doc, "IncludedNote"):
        if _txt(note, "Content"):
            inv.notes.append((_txt(note, "SubjectCode"), _txt(note, "Content")))
    trade = _at(root, "SupplyChainTradeTransaction")
    for item in _kids(trade, "IncludedSupplyChainTradeLineItem"):
        product = _at(item, "SpecifiedTradeProduct")
        qty_node = _at(item, "SpecifiedLineTradeDelivery", "BilledQuantity")
        tax = _at(item, "SpecifiedLineTradeSettlement", "ApplicableTradeTax")
        price = _at(item, "SpecifiedLineTradeAgreement", "NetPriceProductTradePrice")
        basis = _dec(_txt(price, "BasisQuantity")) or Decimal(1)
        unit_price = _dec(_txt(price, "ChargeAmount"))
        inv.lines.append(Line(
            label=(_txt(product, "Name") or _txt(product, "Description") or "Ligne")[:300],
            net_cents=_cents(_txt(item, "SpecifiedLineTradeSettlement",
                                  "SpecifiedTradeSettlementLineMonetarySummation", "LineTotalAmount")) or 0,
            vat_rate_bp=_bp(_txt(tax, "RateApplicablePercent")), vat_category=_txt(tax, "CategoryCode"),
            quantity=_dec(qty_node.text) if qty_node is not None and qty_node.text else Decimal(1),
            unit=_unit(qty_node.get("unitCode") if qty_node is not None else None),
            unit_price=unit_price / basis if unit_price is not None and basis else unit_price,
            item_id=_txt(product, "SellerAssignedID")))
    agreement = _at(trade, "ApplicableHeaderTradeAgreement")
    inv.seller, inv.buyer = _cii_party(_at(agreement, "SellerTradeParty")), _cii_party(_at(agreement, "BuyerTradeParty"))
    settlement = _at(trade, "ApplicableHeaderTradeSettlement")
    inv.currency = (_txt(settlement, "InvoiceCurrencyCode") or "EUR").upper()
    for ac in _kids(settlement, "SpecifiedTradeAllowanceCharge"):
        charge = (_txt(ac, "ChargeIndicator", "Indicator") or "").lower() == "true"
        amount = _cents(_txt(ac, "ActualAmount")) or 0
        tax = _at(ac, "CategoryTradeTax")
        inv.lines.append(Line(
            label=(_txt(ac, "Reason") or ("Frais" if charge else "Remise"))[:300],
            net_cents=amount if charge else -amount, vat_rate_bp=_bp(_txt(tax, "RateApplicablePercent")),
            vat_category=_txt(tax, "CategoryCode"), kind="charge" if charge else "allowance"))
    for tax in _kids(settlement, "ApplicableTradeTax"):
        inv.taxes.append(Tax(rate_bp=_bp(_txt(tax, "RateApplicablePercent")),
                             base_cents=_cents(_txt(tax, "BasisAmount")) or 0,
                             tax_cents=_cents(_txt(tax, "CalculatedAmount")) or 0,
                             category=_txt(tax, "CategoryCode"), exemption=_txt(tax, "ExemptionReason")))
    inv.due_date = _date(_txt(settlement, "SpecifiedTradePaymentTerms", "DueDateDateTime", "DateTimeString"), True)
    summary = _at(settlement, "SpecifiedTradeSettlementHeaderMonetarySummation")
    inv.untaxed_cents = _cents(_txt(summary, "TaxBasisTotalAmount"))
    inv.tax_cents = _cents(_txt(summary, "TaxTotalAmount"))
    inv.total_cents = _cents(_txt(summary, "GrandTotalAmount"))
    inv.payable_cents = _cents(_txt(summary, "DuePayableAmount"))
    return inv


# ------------------------------------------------------------------ UBL

def _ubl_party(node) -> Party:
    party = _at(node, "Party")
    legal = _at(party, "PartyLegalEntity")
    p = Party(name=(_txt(legal, "RegistrationName") or _txt(party, "PartyName", "Name") or "")[:200])
    for ident in (_txt(legal, "CompanyID"), _txt(party, "PartyIdentification", "ID"), _txt(party, "EndpointID")):
        siren, siret = _siren(ident)
        if siren:
            p.siren, p.siret = siren, siret
            break
    vat = _txt(party, "PartyTaxScheme", "CompanyID")
    p.vat_number = vat.replace(" ", "").upper()[:30] if vat else None
    addr = _at(party, "PostalAddress")
    p.address_line1 = (_txt(addr, "StreetName") or "")[:200] or None
    p.postal_code = (_txt(addr, "PostalZone") or "")[:10] or None
    p.city = (_txt(addr, "CityName") or "")[:100] or None
    p.country = _txt(addr, "Country", "IdentificationCode")
    return p


def _parse_ubl(root) -> ReceivedInvoice:
    credit = _local(root.tag) == "CreditNote"
    inv = ReceivedInvoice(syntax="ubl")
    inv.number = (_txt(root, "ID") or "")[:40]
    inv.type_code = _txt(root, "CreditNoteTypeCode" if credit else "InvoiceTypeCode") or ("381" if credit else "380")
    inv.issue_date = _date(_txt(root, "IssueDate"), compact=False)
    inv.due_date = _date(_txt(root, "DueDate") or _txt(root, "PaymentMeans", "PaymentDueDate"), compact=False)
    inv.currency = (_txt(root, "DocumentCurrencyCode") or "EUR").upper()
    for note in _kids(root, "Note"):
        text = "".join(note.itertext()).strip()
        match = re.match(r"#([A-Z]{3})#(.*)", text, re.S)   # convention UBL : « #AAI#texte »
        if text:
            inv.notes.append((match.group(1), match.group(2).strip()) if match else (None, text))
    inv.seller = _ubl_party(_at(root, "AccountingSupplierParty"))
    inv.buyer = _ubl_party(_at(root, "AccountingCustomerParty"))
    for item in _kids(root, "CreditNoteLine" if credit else "InvoiceLine"):
        qty_node = _at(item, "CreditedQuantity" if credit else "InvoicedQuantity")
        product = _at(item, "Item")
        category = _at(product, "ClassifiedTaxCategory")
        basis = _dec(_txt(item, "Price", "BaseQuantity")) or Decimal(1)
        unit_price = _dec(_txt(item, "Price", "PriceAmount"))
        inv.lines.append(Line(
            label=(_txt(product, "Name") or _txt(product, "Description") or "Ligne")[:300],
            net_cents=_cents(_txt(item, "LineExtensionAmount")) or 0,
            vat_rate_bp=_bp(_txt(category, "Percent")), vat_category=_txt(category, "ID"),
            quantity=_dec(qty_node.text) if qty_node is not None and qty_node.text else Decimal(1),
            unit=_unit(qty_node.get("unitCode") if qty_node is not None else None),
            unit_price=unit_price / basis if unit_price is not None and basis else unit_price,
            item_id=_txt(product, "SellersItemIdentification", "ID")))
    for ac in _kids(root, "AllowanceCharge"):
        charge = (_txt(ac, "ChargeIndicator") or "").lower() == "true"
        amount = _cents(_txt(ac, "Amount")) or 0
        category = _at(ac, "TaxCategory")
        inv.lines.append(Line(
            label=(_txt(ac, "AllowanceChargeReason") or ("Frais" if charge else "Remise"))[:300],
            net_cents=amount if charge else -amount, vat_rate_bp=_bp(_txt(category, "Percent")),
            vat_category=_txt(category, "ID"), kind="charge" if charge else "allowance"))
    total = next((t for t in _kids(root, "TaxTotal") if _kids(t, "TaxSubtotal")), None) or _at(root, "TaxTotal")
    inv.tax_cents = _cents(_txt(total, "TaxAmount"))
    for sub in _kids(total, "TaxSubtotal"):
        category = _at(sub, "TaxCategory")
        inv.taxes.append(Tax(rate_bp=_bp(_txt(category, "Percent")), base_cents=_cents(_txt(sub, "TaxableAmount")) or 0,
                             tax_cents=_cents(_txt(sub, "TaxAmount")) or 0, category=_txt(category, "ID"),
                             exemption=_txt(category, "TaxExemptionReason")))
    money = _at(root, "LegalMonetaryTotal")
    inv.untaxed_cents = _cents(_txt(money, "TaxExclusiveAmount"))
    inv.total_cents = _cents(_txt(money, "TaxInclusiveAmount"))
    inv.payable_cents = _cents(_txt(money, "PayableAmount"))
    return inv


# ------------------------------------------------------------------ entrée

def parse_xml(body: bytes) -> ReceivedInvoice:
    if len(body) > MAX_XML_SIZE:
        raise EinvoiceError("XML trop volumineux.")
    if b"<!DOCTYPE" in body[:4096].upper() or b"<!ENTITY" in body.upper():
        raise EinvoiceError("XML refusé (déclaration DOCTYPE ou ENTITY).")
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        raise EinvoiceError("XML illisible.") from None
    name = _local(root.tag)
    if name == "CrossIndustryInvoice":
        return _parse_cii(root)
    if name in ("Invoice", "CreditNote"):
        return _parse_ubl(root)
    raise EinvoiceError("Ce XML n'est pas une facture CII ou UBL.")


def facturx_xml(pdf_bytes: bytes) -> bytes | None:
    """XML Factur-X joint au PDF, s'il y en a un."""
    import pymupdf
    try:
        pdf = pymupdf.open("pdf", pdf_bytes)
    except Exception:  # noqa: BLE001 — PDF illisible
        raise EinvoiceError("PDF illisible.") from None
    with pdf:
        try:
            names = pdf.embfile_names()
        except Exception:  # noqa: BLE001 — PDF sans fichiers joints
            return None
        for name in names:
            if name.lower() in FACTURX_NAMES:
                try:
                    return pdf.embfile_get(name)
                except Exception:  # noqa: BLE001 — pièce jointe illisible
                    continue
    return None


def read(body: bytes) -> ReceivedInvoice:
    """Facture électronique d'un fichier déposé (PDF Factur-X, XML CII ou UBL)."""
    if not body:
        raise EinvoiceError("Fichier vide.")
    if body.startswith(b"%PDF-"):
        xml = facturx_xml(body)
        if xml is None:
            raise EinvoiceError("Ce PDF ne contient pas de facture électronique (Factur-X) : saisissez-la à la main.")
        inv = parse_xml(xml)
        inv.container = "pdf"
        return inv
    return parse_xml(body.lstrip(b"\xef\xbb\xbf"))
