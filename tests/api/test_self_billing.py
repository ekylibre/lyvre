"""Lot AG10.c : autofactures reçues (Factur-X, CII, UBL) enregistrées en ventes, cycle de vie, doublons.

Factures fictives écrites ici ; aucune donnée réelle."""
import io
from datetime import date

import pymupdf
import pytest

from app.extensions import db
from app.models import Account, AnalyticRule, Entity, FiscalYear, JournalEntry, Sale
from app.services import analytic, einvoice_reader, import_activities, organization, self_billing

from test_agri_fixtures import _agri_instance

API = "/api/v1/sales"
FARM_SIREN = "552100554"
COOP_SIREN = "775665912"


def cii(number="AF-2026-0042", type_code="389", seller=FARM_SIREN, lines=None, taxes=None, totals=None,
        allowance=None):
    lines = lines or [("MAIS GRAINS", "12.500", "TNE", "180.00", "2250.00", "5.50"),
                      ("TOURNESOL", "4", "TNE", "400.00", "1600.00", "10.00")]
    taxes = taxes or [("2250.00", "123.75", "5.50"), ("1600.00", "160.00", "10.00")]
    basis, tax, grand = totals or ("3850.00", "283.75", "4133.75")
    items = "".join(f"""
  <ram:IncludedSupplyChainTradeLineItem>
    <ram:AssociatedDocumentLineDocument><ram:LineID>{i}</ram:LineID></ram:AssociatedDocumentLineDocument>
    <ram:SpecifiedTradeProduct><ram:Name>{name}</ram:Name></ram:SpecifiedTradeProduct>
    <ram:SpecifiedLineTradeAgreement><ram:NetPriceProductTradePrice><ram:ChargeAmount>{price}</ram:ChargeAmount>
    </ram:NetPriceProductTradePrice></ram:SpecifiedLineTradeAgreement>
    <ram:SpecifiedLineTradeDelivery><ram:BilledQuantity unitCode="{unit}">{qty}</ram:BilledQuantity></ram:SpecifiedLineTradeDelivery>
    <ram:SpecifiedLineTradeSettlement>
      <ram:ApplicableTradeTax><ram:TypeCode>VAT</ram:TypeCode><ram:CategoryCode>S</ram:CategoryCode>
        <ram:RateApplicablePercent>{rate}</ram:RateApplicablePercent></ram:ApplicableTradeTax>
      <ram:SpecifiedTradeSettlementLineMonetarySummation><ram:LineTotalAmount>{net}</ram:LineTotalAmount>
      </ram:SpecifiedTradeSettlementLineMonetarySummation>
    </ram:SpecifiedLineTradeSettlement>
  </ram:IncludedSupplyChainTradeLineItem>""" for i, (name, qty, unit, price, net, rate) in enumerate(lines, 1))
    vat = "".join(f"""
    <ram:ApplicableTradeTax><ram:CalculatedAmount>{t}</ram:CalculatedAmount><ram:TypeCode>VAT</ram:TypeCode>
      <ram:BasisAmount>{b}</ram:BasisAmount><ram:CategoryCode>S</ram:CategoryCode>
      <ram:RateApplicablePercent>{r}</ram:RateApplicablePercent></ram:ApplicableTradeTax>""" for b, t, r in taxes)
    ac = ""
    if allowance:
        amount, reason, rate = allowance
        ac = f"""
    <ram:SpecifiedTradeAllowanceCharge><ram:ChargeIndicator><udt:Indicator>false</udt:Indicator></ram:ChargeIndicator>
      <ram:ActualAmount>{amount}</ram:ActualAmount><ram:Reason>{reason}</ram:Reason>
      <ram:CategoryTradeTax><ram:TypeCode>VAT</ram:TypeCode><ram:CategoryCode>S</ram:CategoryCode>
        <ram:RateApplicablePercent>{rate}</ram:RateApplicablePercent></ram:CategoryTradeTax>
    </ram:SpecifiedTradeAllowanceCharge>"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
  xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
  xmlns:udt="urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100">
 <rsm:ExchangedDocument><ram:ID>{number}</ram:ID><ram:TypeCode>{type_code}</ram:TypeCode>
  <ram:IssueDateTime><udt:DateTimeString format="102">20261015</udt:DateTimeString></ram:IssueDateTime>
  <ram:IncludedNote><ram:Content>Autofacturation</ram:Content><ram:SubjectCode>AAI</ram:SubjectCode></ram:IncludedNote>
 </rsm:ExchangedDocument>
 <rsm:SupplyChainTradeTransaction>{items}
  <ram:ApplicableHeaderTradeAgreement>
   <ram:SellerTradeParty><ram:Name>EARL des Essais</ram:Name>
    <ram:SpecifiedLegalOrganization><ram:ID schemeID="0002">{seller}</ram:ID></ram:SpecifiedLegalOrganization>
   </ram:SellerTradeParty>
   <ram:BuyerTradeParty><ram:Name>Coopérative Fictive</ram:Name>
    <ram:SpecifiedLegalOrganization><ram:ID schemeID="0002">{COOP_SIREN}</ram:ID></ram:SpecifiedLegalOrganization>
    <ram:PostalTradeAddress><ram:PostcodeCode>17000</ram:PostcodeCode><ram:LineOne>1 route du Silo</ram:LineOne>
     <ram:CityName>La Rochelle</ram:CityName><ram:CountryID>FR</ram:CountryID></ram:PostalTradeAddress>
    <ram:SpecifiedTaxRegistration><ram:ID schemeID="VA">FR00{COOP_SIREN}</ram:ID></ram:SpecifiedTaxRegistration>
   </ram:BuyerTradeParty>
  </ram:ApplicableHeaderTradeAgreement>
  <ram:ApplicableHeaderTradeSettlement><ram:InvoiceCurrencyCode>EUR</ram:InvoiceCurrencyCode>{ac}{vat}
   <ram:SpecifiedTradePaymentTerms><ram:DueDateDateTime><udt:DateTimeString format="102">20261115</udt:DateTimeString>
   </ram:DueDateDateTime></ram:SpecifiedTradePaymentTerms>
   <ram:SpecifiedTradeSettlementHeaderMonetarySummation>
    <ram:TaxBasisTotalAmount>{basis}</ram:TaxBasisTotalAmount>
    <ram:TaxTotalAmount currencyID="EUR">{tax}</ram:TaxTotalAmount>
    <ram:GrandTotalAmount>{grand}</ram:GrandTotalAmount><ram:DuePayableAmount>{grand}</ram:DuePayableAmount>
   </ram:SpecifiedTradeSettlementHeaderMonetarySummation>
  </ram:ApplicableHeaderTradeSettlement>
 </rsm:SupplyChainTradeTransaction>
</rsm:CrossIndustryInvoice>""".encode()


UBL = f"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
 xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
 xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
 <cbc:ID>LAIT-2026-10</cbc:ID><cbc:IssueDate>2026-10-31</cbc:IssueDate><cbc:DueDate>2026-11-20</cbc:DueDate>
 <cbc:InvoiceTypeCode>389</cbc:InvoiceTypeCode><cbc:Note>#AAI#Autofacturation</cbc:Note>
 <cbc:DocumentCurrencyCode>EUR</cbc:DocumentCurrencyCode>
 <cac:AccountingSupplierParty><cac:Party><cac:PartyLegalEntity><cbc:RegistrationName>EARL des Essais</cbc:RegistrationName>
  <cbc:CompanyID schemeID="0002">{FARM_SIREN}</cbc:CompanyID></cac:PartyLegalEntity></cac:Party></cac:AccountingSupplierParty>
 <cac:AccountingCustomerParty><cac:Party><cac:PartyName><cbc:Name>Laiterie Fictive</cbc:Name></cac:PartyName>
  <cac:PartyLegalEntity><cbc:RegistrationName>Laiterie Fictive</cbc:RegistrationName>
  <cbc:CompanyID schemeID="0002">383474814</cbc:CompanyID></cac:PartyLegalEntity></cac:Party></cac:AccountingCustomerParty>
 <cac:AllowanceCharge><cbc:ChargeIndicator>false</cbc:ChargeIndicator><cbc:AllowanceChargeReason>Frais de collecte</cbc:AllowanceChargeReason>
  <cbc:Amount currencyID="EUR">50.00</cbc:Amount><cac:TaxCategory><cbc:ID>S</cbc:ID><cbc:Percent>5.5</cbc:Percent></cac:TaxCategory>
 </cac:AllowanceCharge>
 <cac:TaxTotal><cbc:TaxAmount currencyID="EUR">96.25</cbc:TaxAmount>
  <cac:TaxSubtotal><cbc:TaxableAmount currencyID="EUR">1750.00</cbc:TaxableAmount><cbc:TaxAmount currencyID="EUR">96.25</cbc:TaxAmount>
   <cac:TaxCategory><cbc:ID>S</cbc:ID><cbc:Percent>5.5</cbc:Percent></cac:TaxCategory></cac:TaxSubtotal></cac:TaxTotal>
 <cac:LegalMonetaryTotal><cbc:LineExtensionAmount currencyID="EUR">1800.00</cbc:LineExtensionAmount>
  <cbc:TaxExclusiveAmount currencyID="EUR">1750.00</cbc:TaxExclusiveAmount>
  <cbc:TaxInclusiveAmount currencyID="EUR">1846.25</cbc:TaxInclusiveAmount>
  <cbc:PayableAmount currencyID="EUR">1846.25</cbc:PayableAmount></cac:LegalMonetaryTotal>
 <cac:InvoiceLine><cbc:ID>1</cbc:ID><cbc:InvoicedQuantity unitCode="LTR">4500</cbc:InvoicedQuantity>
  <cbc:LineExtensionAmount currencyID="EUR">1800.00</cbc:LineExtensionAmount>
  <cac:Item><cbc:Name>Lait de vache</cbc:Name><cac:ClassifiedTaxCategory><cbc:ID>S</cbc:ID><cbc:Percent>5.5</cbc:Percent>
  </cac:ClassifiedTaxCategory></cac:Item><cac:Price><cbc:PriceAmount currencyID="EUR">0.40</cbc:PriceAmount></cac:Price>
 </cac:InvoiceLine>
</Invoice>""".encode()


def facturx_pdf(xml: bytes) -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Autofacture fictive")
    doc.embfile_add("factur-x.xml", xml)
    return doc.tobytes()


def _upload(client, url, body, name="autofacture.xml", **form):
    return client.post(url, data={"file": (io.BytesIO(body), name), **form}, content_type="multipart/form-data")


@pytest.fixture()
def farm(app, login_as):
    client = login_as(role="admin")
    _agri_instance()
    org = organization.get()
    org.name, org.siren = "EARL des Essais", FARM_SIREN
    db.session.add(FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), vat_liable=True,
                              vat_on_receipts=False))
    db.session.commit()
    return client


def test_read_cii_ubl_and_pdf():
    inv = einvoice_reader.read(cii())
    assert (inv.syntax, inv.type_code, inv.number, inv.issue_date) == ("cii", "389", "AF-2026-0042", date(2026, 10, 15))
    assert inv.self_billed and inv.seller.siren == FARM_SIREN and inv.buyer.siren == COOP_SIREN
    assert [(l.label, l.net_cents, l.vat_rate_bp, l.unit) for l in inv.lines] == [
        ("MAIS GRAINS", 225000, 550, "t"), ("TOURNESOL", 160000, 1000, "t")]
    assert (inv.untaxed_cents, inv.tax_cents, inv.total_cents) == (385000, 28375, 413375)
    assert inv.notes == [("AAI", "Autofacturation")] and inv.due_date == date(2026, 11, 15)
    ubl = einvoice_reader.read(UBL)
    assert (ubl.syntax, ubl.number, ubl.buyer.name) == ("ubl", "LAIT-2026-10", "Laiterie Fictive")
    assert [(l.label, l.net_cents, l.kind) for l in ubl.lines] == [("Lait de vache", 180000, "line"),
                                                                    ("Frais de collecte", -5000, "allowance")]
    assert ubl.lines[0].unit == "L" and ubl.notes == [("AAI", "Autofacturation")]
    pdf = einvoice_reader.read(facturx_pdf(cii()))
    assert pdf.container == "pdf" and pdf.number == "AF-2026-0042"
    with pytest.raises(einvoice_reader.EinvoiceError):
        einvoice_reader.read(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><x/>')
    with pytest.raises(einvoice_reader.EinvoiceError):
        einvoice_reader.read(_plain_pdf())


def _plain_pdf():
    doc = pymupdf.open()
    doc.new_page()
    return doc.tobytes()


def test_analyze_proposes_accounts(farm):
    workshop = import_activities._workshop("plant_farming")
    production = import_activities.match_production("MAIS GRAINS")
    activity = analytic.save_activity(None, {"workshop_id": workshop.id, "name": production["name"],
                                             "lexicon_reference": production["reference"]})
    db.session.add(Account(code="7011001", label="Maïs grain", account_type="PRODUIT",
                           parent_id=Account.query.filter_by(code="7011").one().id))
    db.session.add(AnalyticRule(account_prefix="7011001", activity_id=activity.id))
    db.session.commit()
    data = _upload(farm, f"{API}/self-billed/analyze", cii()).get_json()
    assert data["problems"] == [] and data["client"] is None and data["buyer"]["siren"] == COOP_SIREN
    assert data["lines"][0]["account_code"] == "7011001" and data["lines"][0]["account_origin"] == "activité"
    assert data["lines"][1]["account_code"] == ""
    assert (data["untaxed_cents"], data["tax_cents"], data["total_cents"]) == (385000, 28375, 413375)


def test_checks_refuse_incoherent_or_foreign(farm):
    data = _upload(farm, f"{API}/self-billed/analyze", cii(seller="732829320")).get_json()
    assert any("n'est pas l'exploitation" in p for p in data["problems"])
    data = _upload(farm, f"{API}/self-billed/analyze", cii(type_code="380", seller="732829320")).get_json()
    assert any("Achats" in p for p in data["problems"])
    data = _upload(farm, f"{API}/self-billed/analyze", cii(totals=("3800.00", "283.75", "4083.75"))).get_json()
    assert any("somme des lignes" in p for p in data["problems"])
    data = _upload(farm, f"{API}/self-billed/analyze", cii(taxes=[("2250.00", "120.00", "5.50"),
                                                                   ("1600.00", "160.00", "10.00")],
                                                            totals=("3850.00", "280.00", "4130.00"))).get_json()
    assert data["problems"] == [] and any("TVA à 5,5 %" in w for w in data["warnings"])
    resp = _upload(farm, f"{API}/self-billed", cii(seller="732829320"))
    assert resp.status_code == 422


def test_receive_accept_and_duplicate(farm):
    resp = _upload(farm, f"{API}/self-billed", facturx_pdf(cii()), name="af.pdf",
                   accounts='{"0": "7011", "1": "7011"}')
    assert resp.status_code == 201, resp.get_json()
    item = resp.get_json()["item"]
    assert item["self_billed"] and item["number"] == "AF-2026-0042" and item["status"] == "draft"
    assert item["lifecycle"]["status"] == "received" and item["lifecycle"]["code"] is None
    assert (item["untaxed_cents"], item["tax_cents"], item["total_cents"]) == (385000, 28375, 413375)
    sale = db.session.get(Sale, item["id"])
    assert sale.entity.siren == COOP_SIREN and sale.journal_entry_id is None and sale.received_file.endswith(".pdf")
    assert farm.get(f"{API}/{sale.id}/received-file").status_code == 200
    assert farm.get(f"{API}/{sale.id}/pdf").data.startswith(b"%PDF")
    # Pièce reçue : ni modifiable ni émise avec un numéro Lyvre.
    assert farm.patch(f"{API}/{sale.id}", json={}).status_code == 409
    assert farm.post(f"{API}/{sale.id}/issue").status_code == 409
    # Doublon : même client, même numéro.
    dup = _upload(farm, f"{API}/self-billed/analyze", cii()).get_json()
    assert any("Doublon" in p for p in dup["problems"])
    assert _upload(farm, f"{API}/self-billed", cii()).status_code == 409
    # Contestation : motif obligatoire, rappel dans l'échéancier.
    assert farm.post(f"{API}/{sale.id}/lifecycle", json={"status": "disputed"}).status_code == 422
    resp = farm.post(f"{API}/{sale.id}/lifecycle", json={"status": "disputed", "reason": "Poids erroné"})
    assert resp.status_code == 200 and "fr:207" in resp.get_json()["notices"][0]["message"]
    occ = self_billing.agenda_occurrences(date(2026, 11, 1), date(2026, 11, 30))
    assert occ and occ[0]["date"] == date(2026, 11, 15)
    # Acceptation : écriture VE au 411 de la coopérative, ventes et TVA par taux.
    resp = farm.post(f"{API}/{sale.id}/lifecycle", json={"status": "accepted"})
    assert resp.status_code == 200, resp.get_json()
    item = resp.get_json()["item"]
    assert item["status"] == "issued" and item["lifecycle"]["code"] == "fr:205" and item["lifecycle"]["actions"] == []
    entry = db.session.get(JournalEntry, item["journal_entry"]["id"])
    debit = sum(l.debit_cents for l in entry.lines)
    assert debit == sum(l.credit_cents for l in entry.lines) == 413375
    assert sorted(l.account.code for l in entry.lines if l.credit_cents)[-2:] == ["7011", "7011"]
    assert not self_billing.agenda_occurrences(date(2026, 11, 1), date(2026, 11, 30))
    assert farm.post(f"{API}/{sale.id}/lifecycle", json={"status": "refused"}).status_code == 409
    listed = farm.get(f"{API}?self_billed=1").get_json()["items"]
    assert [s["number"] for s in listed] == ["AF-2026-0042"]


def test_ubl_refused_and_account_needed(farm):
    resp = _upload(farm, f"{API}/self-billed", UBL)
    assert resp.status_code == 201, resp.get_json()
    sale = db.session.get(Sale, resp.get_json()["item"]["id"])
    assert sale.total_cents == 184625 and sale.received_file.endswith(".xml")
    assert farm.post(f"{API}/{sale.id}/lifecycle", json={"status": "accepted"}).status_code == 409  # comptes manquants
    db.session.rollback()
    resp = farm.post(f"{API}/{sale.id}/lifecycle", json={"status": "refused", "reason": "Prix non conforme"})
    assert resp.status_code == 200
    sale = db.session.get(Sale, sale.id)
    assert sale.status == "canceled" and sale.journal_entry_id is None and sale.lifecycle_status == "refused"
    # Même numéro chez un autre client : pas un doublon.
    other = Entity.query.filter_by(siren="383474814").one()
    assert self_billing.duplicate(other, "AF-2026-0042") is None


def test_delete_received(farm):
    sale_id = _upload(farm, f"{API}/self-billed", cii(), accounts='{"0": "7011"}').get_json()["item"]["id"]
    path = self_billing.received_path(db.session.get(Sale, sale_id))
    assert path is not None and path.is_file()
    assert farm.delete(f"{API}/{sale_id}").status_code == 200
    assert not path.exists()
