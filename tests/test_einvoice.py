"""Factur-X des factures de vente (lot S0) : XML CII EN 16931 contrôlé par le schéma, PDF/A-3 avec
le XML embarqué, relu par le lecteur de factures de l'application."""
import re
from datetime import date

import facturx
import pytest
from lxml import etree
from pypdf import PdfReader

from app.services import einvoice as e
from app.services import invoice_reader

NS = {"rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
      "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"}
SELLER = e.Party("SCI Exemple", address1="1 rue des Chênes", postcode="75001", city="Paris",
                 siren="123456789", vat_number="FR32123456789")
BUYER = e.Party("Client SARL", address1="2 avenue X", postcode="69001", city="Lyon", siren="987654321")
HTML = "<html><body><h1>Facture</h1><p>Exemple</p></body></html>"


def _doc(**fields):
    values = dict(number="F-2026-0001", issue_date=date(2026, 10, 23), due_date=date(2026, 11, 22),
                  seller=SELLER, buyer=BUYER, iban="FR76 3000 6000 0112 3456 7890 189",
                  lines=[e.Line("Prestation de conseil", 2000, 50000, 100000, 2000, unit="HUR"),
                         e.Line("Fournitures", 3000, 1000, 3000, 550)])
    values.update(fields)
    return e.Document(**values)


def _xpath(xml, path):
    return [n.text for n in etree.fromstring(xml).xpath(path, namespaces=NS)]


def test_invoice_xml_is_valid_en16931():
    xml = e.cii_xml(_doc(vat_on_receipts=True))
    facturx.xml_check_xsd(xml, flavor="factur-x", level="en16931")  # lève si invalide
    assert _xpath(xml, "//rsm:ExchangedDocument/ram:ID") == ["F-2026-0001"]
    assert _xpath(xml, "//rsm:ExchangedDocument/ram:TypeCode") == ["380"]
    assert _xpath(xml, "//ram:GrandTotalAmount") == ["1231.65"]
    assert _xpath(xml, "//ram:TaxTotalAmount") == ["201.65"]
    assert sorted(_xpath(xml, "//ram:ApplicableHeaderTradeSettlement/ram:ApplicableTradeTax/ram:RateApplicablePercent")) == ["20.00", "5.50"]
    assert set(_xpath(xml, "//ram:ApplicableHeaderTradeSettlement/ram:ApplicableTradeTax/ram:DueDateTypeCode")) == {"72"}  # à l'encaissement
    assert _xpath(xml, "//ram:IBANID") == ["FR7630006000011234567890189"]


def test_franchise_293b_has_no_vat():
    xml = e.cii_xml(_doc(vat_exempt=True))
    assert _xpath(xml, "//ram:TaxTotalAmount") == ["0.00"]
    assert set(_xpath(xml, "//ram:ApplicableTradeTax/ram:CategoryCode")) == {"E"}
    assert set(_xpath(xml, "//ram:ApplicableHeaderTradeSettlement/ram:ApplicableTradeTax/ram:ExemptionReasonCode")) == {"VATEX-FR-FRANCHISE"}
    assert _xpath(xml, "//ram:GrandTotalAmount") == ["1030.00"]


def test_credit_note_references_its_invoice():
    xml = e.cii_xml(_doc(number="AV-2026-0001", type_code=e.CREDIT_NOTE, preceding_number="F-2026-0001",
                         preceding_date=date(2026, 10, 23)))
    assert _xpath(xml, "//rsm:ExchangedDocument/ram:TypeCode") == ["381"]
    assert _xpath(xml, "//ram:InvoiceReferencedDocument/ram:IssuerAssignedID") == ["F-2026-0001"]


def test_invalid_document_is_refused():
    with pytest.raises(Exception):
        e.cii_xml(_doc(lines=[e.Line("", 1000, 100, 100, 2000)]))  # désignation obligatoire


def test_facturx_pdf_is_pdfa3_and_read_back(tmp_path):
    pdf = e.facturx_pdf(HTML, _doc())
    name, xml = facturx.get_xml_from_pdf(pdf, check_xsd=True)
    assert name == "factur-x.xml" and b"F-2026-0001" in xml
    path = tmp_path / "x.pdf"
    path.write_bytes(pdf)
    reader = PdfReader(path)
    xmp = reader.trailer["/Root"]["/Metadata"].get_object().get_data().decode()
    assert re.search(r"pdfaid:part(>|=\")3", xmp) and re.search(r"pdfaid:conformance(>|=\")B", xmp)
    assert "/OutputIntents" in reader.trailer["/Root"]

    # Relu par le lecteur de factures (régression : embfile_info de PyMuPDF échouait sur ce PDF).
    ext = invoice_reader.read(str(path))
    assert ext.source == "facturx" and ext.coherent
    assert ext.fields["invoice_number"].value == "F-2026-0001"
    assert (ext.fields["total"].value, ext.fields["untaxed"].value, ext.fields["tax"].value) == (123165, 103000, 20165)
