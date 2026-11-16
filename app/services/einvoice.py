"""Factur-X des factures de vente (lot S0 du module Ventes, claudedocs/design_ventes.md § 5).

`cii_xml(doc)` produit le XML CII au profil EN 16931 à partir d'une facture décrite par `Document`
(bibliothèque `factur-x` d'Akretion, contrôle XSD) ; `pdf_a3(html)` rend le PDF/A-3b avec
WeasyPrint ; `facturx_pdf(html, doc)` insère le XML dans le PDF. Le contrôle schematron demande un
serveur Saxon : il n'est jamais lancé ici (`check_schematron=False`).

Montants en centimes, taux en points de base (2000 = 20 %), comme le reste de l'application.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

import facturx

LEVEL = "en16931"
INVOICE, CREDIT_NOTE = "380", "381"
SEPA_TRANSFER = "58"
# Motif d'exonération des structures non assujetties (franchise en base).
FRANCHISE = ("VATEX-FR-FRANCHISE", "TVA non applicable, art. 293 B du CGI")
# Lot AG10.e : facture à un particulier, note BAR « B2C » (documentation SUPER PDP, article « E-reporting » :
# la plateforme en tire l'e-reporting).
B2C_NOTE = {"BT-21": "BAR", "BT-22": "B2C"}


@dataclass
class Party:
    name: str
    country: str = "FR"
    address1: str | None = None
    address2: str | None = None
    postcode: str | None = None
    city: str | None = None
    siren: str | None = None          # identifiant légal (schéma 0002)
    vat_number: str | None = None


@dataclass
class Line:
    label: str
    quantity_milli: int               # quantité × 1000
    unit_price_cents: int             # prix unitaire HT
    untaxed_cents: int                # montant HT de la ligne (après remise)
    vat_rate_bp: int = 0
    unit: str = "C62"                 # UN/ECE rec. 20 : C62 = unité, HUR = heure, MON = mois
    description: str | None = None
    # Lot T2 : vente sans TVA française — catégorie (AE, K, G, O), code et motif d'exonération.
    exemption: tuple[str, str, str] | None = None


@dataclass
class Document:
    number: str
    issue_date: date
    seller: Party
    buyer: Party
    lines: list[Line]
    type_code: str = INVOICE
    due_date: date | None = None
    vat_exempt: bool = False          # franchise en base (art. 293 B)
    vat_on_receipts: bool = False     # TVA exigible à l'encaissement (prestations)
    iban: str | None = None
    payment_terms: str | None = None
    notes: list[str] = field(default_factory=list)
    preceding_number: str | None = None   # avoir : facture d'origine
    preceding_date: date | None = None
    period_start: date | None = None
    period_end: date | None = None
    delivery_date: date | None = None     # livraison ou fin de prestation ; défaut : date d'émission
    b2c: bool = False                     # client particulier : note BAR = B2C (lot AG10.e)
    # Motif d'exonération d'une pièce sans TVA autre que la franchise (code, libellé) : RFA sourcé (lot AG10.e).
    exempt_reason: tuple[str, str] | None = None


# La bibliothèque attend des nombres en chaîne (ou float) : chaînes exactes, jamais de float.
def _amount(cents: int) -> str:
    return str((Decimal(cents) / 100).quantize(Decimal("0.01")))


def _rate(bp: int) -> str:
    return str((Decimal(bp) / 100).quantize(Decimal("0.01")))


def _category(doc: Document, rate_bp: int, exemption: tuple[str, str, str] | None = None) -> str:
    if doc.vat_exempt:
        return "E"
    if exemption is not None and not rate_bp:
        return exemption[0]
    return "S" if rate_bp else "Z"


def _party(p: Party) -> dict:
    party = {"name": p.name, "country_code": p.country}
    for key, value in (("addr_l1", p.address1), ("addr_l2", p.address2), ("postcode", p.postcode),
                       ("city", p.city), ("vat_identifier", p.vat_number)):
        if value:
            party[key] = value
    if p.siren:
        party["legal_identifier"], party["legal_identifier_schemeid"] = p.siren, "0002"
    return party


def _breakdown(doc: Document) -> tuple[list[dict], int]:
    """Ventilation de la TVA par taux (BG-23) et TVA totale, arrondie par taux."""
    bases: dict[tuple, int] = {}
    for line in doc.lines:
        exemption = line.exemption if not line.vat_rate_bp else None
        key = (line.vat_rate_bp, exemption)
        bases[key] = bases.get(key, 0) + line.untaxed_cents
    rows, total = [], 0
    for (rate_bp, exemption), base in sorted(bases.items(), key=lambda item: (item[0][0], item[0][1] or ())):
        tax = 0 if doc.vat_exempt else round(base * rate_bp / 10000)
        total += tax
        row = {"BT-116": _amount(base), "BT-117": _amount(tax), "BT-118": _category(doc, rate_bp, exemption),
               "BT-119": _rate(0 if doc.vat_exempt else rate_bp)}
        if doc.vat_exempt:
            row["BT-121"], row["BT-120"] = doc.exempt_reason or FRANCHISE
        elif exemption is not None:
            row["BT-121"], row["BT-120"] = exemption[1], exemption[2]
        rows.append(row)
    return rows, total


def data_dict(doc: Document) -> dict:
    """Facture → dictionnaire de la bibliothèque factur-x (clés BT/BG de la norme EN 16931)."""
    vat_rows, tax_cents = _breakdown(doc)
    untaxed = sum(line.untaxed_cents for line in doc.lines)
    total = untaxed + tax_cents
    data = {
        "BT-1": doc.number, "BT-2": doc.issue_date, "BT-3": doc.type_code, "BT-5": "EUR",
        "BT-24": "urn:cen.eu:en16931:2017",
        # Bloc livraison obligatoire et non vide dans le schéma : date de livraison (BT-72).
        "BT-72": doc.delivery_date or doc.period_end or doc.issue_date,
        "BG-4": _party(doc.seller), "BG-7": _party(doc.buyer), "BG-23": vat_rows,
        "BT-106": _amount(untaxed), "BT-109": _amount(untaxed), "BT-110": _amount(tax_cents),
        "BT-112": _amount(total), "BT-115": _amount(total),
        "BG-25": [{
            "BT-126": str(i), "BT-129": str((Decimal(line.quantity_milli) / 1000).normalize()), "BT-130": line.unit,
            "BT-131": _amount(line.untaxed_cents), "BT-146": _amount(line.unit_price_cents),
            "BT-151": _category(doc, line.vat_rate_bp, line.exemption),
            "BT-152": _rate(0 if doc.vat_exempt else line.vat_rate_bp),
            "BT-153": line.label[:200], **({"BT-154": line.description} if line.description else {}),
        } for i, line in enumerate(doc.lines, start=1)],
    }
    if doc.due_date:
        data["BT-9"] = doc.due_date
    if doc.vat_on_receipts and not doc.vat_exempt:
        data["BT-8"] = "payment"      # TVA exigible au paiement (prestations, option de l'exercice)
    if doc.iban:
        data["BT-81"], data["BT-84"] = SEPA_TRANSFER, doc.iban.replace(" ", "")
    if doc.payment_terms:
        data["BT-20"] = doc.payment_terms
    notes = [{"BT-22": note} for note in doc.notes] + ([dict(B2C_NOTE)] if doc.b2c else [])
    if notes:
        data["BG-1"] = notes
    if doc.preceding_number:
        data["BG-3"] = [{"BT-25": doc.preceding_number,
                         **({"BT-26": doc.preceding_date} if doc.preceding_date else {})}]
    if doc.period_start:
        data["BT-73"] = doc.period_start
    if doc.period_end:
        data["BT-74"] = doc.period_end
    return data


def cii_xml(doc: Document) -> bytes:
    """XML CII EN 16931, contrôlé contre le schéma XSD (exception si invalide)."""
    return facturx.generate_cii_xml(data_dict(doc), level=LEVEL, check_xsd=True, check_schematron=False)


def pdf_a3(html: str, base_url: str | None = None) -> bytes:
    from weasyprint import HTML

    return HTML(string=html, base_url=base_url).write_pdf(pdf_variant="pdf/a-3b")


def facturx_pdf(html: str, doc: Document, base_url: str | None = None) -> bytes:
    """PDF/A-3 de la facture avec son XML Factur-X embarqué."""
    return facturx.generate_from_binary(pdf_a3(html, base_url), cii_xml(doc), flavor="factur-x",
                                        level=LEVEL, check_xsd=True, check_schematron=False,
                                        lang="fr-FR")
