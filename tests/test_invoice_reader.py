"""Lecture des factures : texte, Factur-X, OCR (ignoré sans Tesseract)."""
import shutil
from datetime import date

import numpy as np
import pymupdf
import pytest

from app.services import invoice_reader as reader

FREE = """SCI DES CHENES VERTS
1 RUE DES EXEMPLES
Facture Freebox
n°1400000013 du 02 Septembre 2026
Identifiant abonné : 12345678
HT
TTC
Total
33,33€
39,99€
Dont TVA 20%: 6,66€
Somme à payer le 04 Septembre 2026
39,99€
Montant prélevé sur le compte bancaire FR76 3000 1000 1000 0000 00****** à partir du 04 Septembre 2026
Free SAS au capital de 3.441.812 € - B 421 938 861 RCS Paris - No de TVA intracommunautaire : FR 604 219 388 61
"""

TICKET = """SAINTES (St Georges des Coteaux)
SIRET: 45164790301031
N° Carte Fidélité : 2200172948751
3      LOT 3 BOITES DERIVATION ETANCHES
       3663602434177    4,09    12,27 V5
TOTAL                        171,16 €
Fidélité Pros                 -0,76 €
Carte bancaire              -167,96 €
DETAIL TVA
V5 TVA 20,00%      28,53      142,63 HT
29/09/2026 12:11    2424     002    0058
magasin ou sur www.b
ricodepot.fr
"""


def _pdf(path, text, fontsize=10):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(pymupdf.Rect(40, 40, 560, 800), text, fontsize=fontsize, fontname="helv")
    doc.save(path)
    return path


def _values(ext):
    return {name: f.value for name, f in ext.fields.items()}


# ------------------------------------------------------------------ texte

def test_parse_free_invoice():
    ext = reader.parse_text(FREE)
    assert _values(ext) == {
        "supplier_name": "Free", "vat_number": "FR60421938861", "invoice_number": "1400000013",
        "issue_date": date(2026, 9, 2), "due_date": date(2026, 9, 4),
        "total": 3999, "untaxed": 3333, "tax": 666,
    }
    assert ext.taxes == [(2000, 3333, 666)] and ext.warnings == []
    # Texte natif et montants cohérents : rien à vérifier, sauf ce qui est deviné.
    assert not any(f.check for f in ext.fields.values())


def test_parse_till_receipt():
    ext = reader.parse_text(TICKET)
    values = _values(ext)
    assert values["siret"] == "45164790301031"
    assert values["supplier_name"] == "Bricodepot" and ext.fields["supplier_name"].check
    assert (values["total"], values["untaxed"], values["tax"]) == (17116, 14263, 2853)
    assert values["issue_date"] == date(2026, 9, 29) and ext.fields["issue_date"].check
    assert "invoice_number" not in values  # le n° de carte de fidélité n'est pas un n° de facture
    # Points fidélité déduits après le total (le paiement carte n'en est pas un).
    assert values["discount"] == 76 and ext.fields["discount"].check
    assert ext.taxes == [(2000, 14263, 2853)]


def test_amounts_and_dates():
    assert reader.parse_amount("1 234,56") == 123456
    assert reader.parse_amount("1.234,56 €") == 123456
    assert reader.parse_amount("39.99") == 3999
    assert reader.amounts_in("Capital 3.441.812 € — total 12,50€ 20%") == [1250]
    assert reader.dates_in("du 1er au 30 sept. 2026, émise le 02/10/26") == [
        date(2026, 9, 30), date(2026, 10, 2)]
    assert reader.dates_in("2026-10-22 et 31/02/2026") == [date(2026, 10, 22)]


def test_identifiers_validated():
    assert reader.valid_siret("45164790301031") and not reader.valid_siret("45164790301032")
    assert reader.valid_fr_vat("FR60421938861") and not reader.valid_fr_vat("FR61421938861")
    assert reader.valid_iban("FR7630006000011234567890189")
    assert not reader.valid_iban("FR7630006000011234567890188")


def test_iban_of_supplier_kept_own_ignored():
    text = "Virement sur FR76 3000 6000 0112 3456 7890 189\nTotal TTC 12,00 €"
    assert reader.parse_text(text).value("iban") == "FR7630006000011234567890189"
    ignored = reader.parse_text(text, ignore_ibans={"FR7630006000011234567890189"})
    assert ignored.value("iban") is None


def test_inconsistent_amounts_flagged():
    ext = reader.parse_text("Facture n° F-2026-12 du 03/10/2026\nTotal HT 100,00 €\n"
                            "Total TVA 20,00 €\nNet à payer 130,00 €")
    assert ext.value("invoice_number") == "F-2026-12"
    assert ext.value("total") == 13000 and ext.fields["total"].check
    assert any("HT + TVA" in w for w in ext.warnings)


def test_missing_amount_deduced_and_multiple_rates():
    ext = reader.parse_text("FACTURE N° 2026/0042\nDate de facture : 15/10/2026\n"
                            "Échéance : 14/11/2026\nTVA 5,5 % 5,50 100,00\nTVA 20 % 10,00 50,00\n"
                            "Total TTC 165,50 €")
    assert ext.value("invoice_number") == "2026/0042"
    assert (ext.value("issue_date"), ext.value("due_date")) == (date(2026, 10, 15), date(2026, 11, 14))
    assert ext.taxes == [(550, 10000, 550), (2000, 5000, 1000)]
    assert (ext.value("untaxed"), ext.value("tax"), ext.value("total")) == (15000, 1550, 16550)
    assert not ext.fields["total"].check


def test_credit_note_detected():
    ext = reader.parse_text("AVOIR n° AV-12\ndu 05/10/2026\nTotal TTC 24,00 €")
    assert ext.value("is_credit_note") is True and ext.value("invoice_number") == "AV-12"


def test_ocr_text_digit_confusion_fixed():
    ext = reader.parse_text("Facture n° 1234 du O2 Septembre 2026\nNet à payer 1O,00 €", origin="ocr")
    assert ext.value("issue_date") == date(2026, 9, 2) and ext.value("total") == 1000
    assert all(f.check for f in ext.fields.values())


# ------------------------------------------------------------------ cohérence, vocabulaire, identifiants

def test_absurd_amounts_flagged():
    # Ancienne lecture d'un tableau en colonnes : HT 0, TVA = TTC passait « HT + TVA = TTC ».
    ext = reader.parse_text("Total HT 0,00 €\nTotal TVA 85,49 €\nTotal TTC 85,49 €")
    assert ext.fields["total"].check and any("vraisemblables" in w for w in ext.warnings)


def test_coherent_triple_beats_items_header():
    # L'en-tête « Total HT » du tableau d'articles précède le vrai total HT.
    ext = reader.parse_text("Désignation   Total HT\nTotal HT : 69,00\nDéplacement   69,00\n"
                            "Total HT   377,70\nMontant TVA   75,54\nTOTAL TTC   453,24\n"
                            "NET À PAYER   453,24 EUR")
    assert (ext.value("total"), ext.value("untaxed"), ext.value("tax")) == (45324, 37770, 7554)
    assert ext.taxes == [(2000, 37770, 7554)] and ext.coherent
    assert not ext.fields["total"].check


def test_total_row_with_three_amounts():
    ext = reader.parse_text("Réf. Facture : 25 150416 A du 25/02/2025\nTOTAL A PAYER   119,72   6,58   126,30\n"
                            "Facture Prélevée le : 05/04/2025")
    assert (ext.value("total"), ext.value("untaxed"), ext.value("tax")) == (12630, 11972, 658)
    assert ext.taxes == [(550, 11972, 658)]
    assert ext.value("invoice_number") == "25 150416 A"
    assert (ext.value("issue_date"), ext.value("due_date")) == (date(2025, 2, 25), date(2025, 4, 5))


def test_zero_rate_line_and_labelled_dates():
    ext = reader.parse_text("Facture n° 10237045906 du 10/10/2025\nMontant Hors TVA   60,16 €\n"
                            "Montant total à payer (TTC)   70,59 €\nProchaine facture vers le 10/11/2025\n"
                            "Vous serez prélevé d'un montant de   70,59 €\nà partir du :   27/10/2025\n"
                            "Venant à échéance le 30/09/2026\nTVA à 0%   8,00 €   0,00 €\n"
                            "TVA à 20,00%   52,16 €   10,43 €")
    assert (ext.value("total"), ext.value("untaxed"), ext.value("tax")) == (7059, 6016, 1043)
    assert ext.taxes == [(0, 800, 0), (2000, 5216, 1043)]
    assert (ext.value("issue_date"), ext.value("due_date")) == (date(2025, 10, 10), date(2025, 10, 27))


def test_english_invoice():
    ext = reader.parse_text("Invoice number: INV-2026-881\nInvoice date: August 3, 2026\n"
                            "Due date: 02 September 2026\nSubtotal 85,49\nVAT 20% 17,10\nAmount due 102,59")
    assert ext.value("invoice_number") == "INV-2026-881"
    assert (ext.value("issue_date"), ext.value("due_date")) == (date(2026, 8, 3), date(2026, 9, 2))
    assert (ext.value("total"), ext.value("untaxed"), ext.value("tax")) == (10259, 8549, 1710)


def test_tax_free_mention():
    ext = reader.parse_text("Facture F-2026-010\nTVA non applicable, art. 293 B du CGI\nTotal 875,00 €")
    assert (ext.value("total"), ext.value("untaxed"), ext.value("tax")) == (87500, 87500, 0)


def test_number_is_not_a_date_nor_a_decree():
    ext = reader.parse_text("N° pièce : 260305768FCLCF01\nDate facture : 18/03/2026\n"
                            "article 192 du décret n° 2012-1246")
    assert ext.value("invoice_number") == "260305768FCLCF01"


def test_customer_identifiers_ignored():
    text = ("N° TVA client : FR11123456782\nSIRET : 12345678200028\n"
            "Référence acheminement : 15201302453425\n"
            "SAS au capital de 1 649 000 € - SIRET 401 282 553 00049 - N°TVA intra FR 71401282553")
    ext = reader.parse_text(text, ignore_sirens={"123456782"})
    assert (ext.value("vat_number"), ext.value("siret")) == ("FR71401282553", "40128255300049")
    # Sans SIREN de l'organisation : le libellé « client » suffit pour la TVA.
    assert reader.parse_text(text).value("vat_number") == "FR71401282553"


def test_supplier_from_address_block_not_own_name():
    text = ("FACTURE\nLES CHENES VERTS\n1 Rue des Exemples\n17250 SAINT-PORCHAIRE\n"
            "COUTANT LOCATION   SCI LES CHENES VERTS\n5 rue du champs fleuri\n17250 BEURLAY\nTotal TTC 204,00 €")
    ext = reader.parse_text(text, ignore_names=["SCI des Chênes Verts"])
    assert ext.value("supplier_name") == "Coutant Location" and ext.fields["supplier_name"].check
    assert reader.same_name("LES CHENES VERTS", "SCI des Chênes Verts")
    assert not reader.same_name("Coutant Location", "SCI des Chênes Verts")


def test_legal_name_before_address():
    ext = reader.parse_text("HM France Bétons - 4 Place des Saisons, 92400 Courbevoie - SAS au capital de "
                            "27 159 732 € - RCS Nanterre B 642016166")
    assert ext.value("supplier_name") == "HM France Bétons"


def test_ocr_confusions_in_amounts():
    ext = reader.parse_text("Sommeà prélever\nL 905,00 €", origin="ocr")
    assert ext.value("total") == 190500


def test_supplier_hints():
    text = "Facture 2026-77 du 03/10/2026\nCommande n° 2026-0001\nNet à payer 120,00 €"
    assert reader.parse_text(text).value("untaxed") is None
    hints = reader.SupplierHints(rates=frozenset({2000}), number_shapes=frozenset({"9999-99"}))
    ext = reader.parse_text(text, hints=hints)
    assert (ext.value("untaxed"), ext.value("tax")) == (10000, 2000) and ext.fields["total"].check
    assert reader.parse_text(text, hints=reader.SupplierHints(tax_free=True)).value("tax") == 0
    assert reader.number_shape("F-2026-010") == "A-9999-999"


# ------------------------------------------------------------------ fichiers

def test_read_text_pdf(tmp_path):
    ext = reader.read(_pdf(tmp_path / "free.pdf", FREE))
    assert ext.source == "text" and ext.value("total") == 3999 and ext.value("supplier_name") == "Free"


def test_read_unreadable_file(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-1.4 tronque")
    ext = reader.read(bad)
    assert ext.source == "none" and ext.fields == {} and ext.warnings


def test_read_totals_table_in_columns(tmp_path):
    # Totaux en colonnes : libellés sur une ligne, montants dessous (facture Scaleway).
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((40, 60), "Facture n° 5418525", fontsize=10)
    page.insert_text((40, 80), "Date de facturation : 03 August 2026", fontsize=10)
    for x, label, value in ((200, "Total HT", "85,49 Euros"), (290, "Taux TVA", "20,00 %"),
                            (370, "Total TVA", "17,10 Euros"), (460, "Total TTC", "102,59 Euros")):
        page.insert_text((x, 200), label, fontsize=10)
        page.insert_text((x - 10, 215), value, fontsize=10)
    page.insert_text((40, 300), "Scaleway SAS, 8 rue de la Ville l'Evêque, 75008 Paris - SAS au capital de "
                     "141 420 Euros", fontsize=8)
    doc.save(tmp_path / "cols.pdf")
    ext = reader.read(tmp_path / "cols.pdf")
    assert (ext.value("total"), ext.value("untaxed"), ext.value("tax")) == (10259, 8549, 1710)
    assert ext.taxes == [(2000, 8549, 1710)] and not ext.fields["total"].check
    assert ext.value("issue_date") == date(2026, 8, 3) and ext.value("supplier_name") == "Scaleway"


def test_layout_keeps_stacked_lines_apart(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((40, 100), "Depuis 2019, nous plantons des arbres", fontsize=6)
    page.insert_text((40, 107), "pour les forêts en danger.", fontsize=6)
    page.insert_text((300, 105), "Rem Mt   -40,00", fontsize=12)
    lines = reader.layout_lines(page)
    assert "Depuis 2019, nous plantons des arbres" in lines[0]
    assert lines[1] == "pour les forêts en danger." or "pour les forêts en danger." in lines[1]


def test_clean_scan_removes_table_rules():
    dark = np.zeros((100, 200), dtype=bool)
    dark[10:90, 50] = True        # filet vertical
    dark[40, 20:180] = True       # filet horizontal
    dark[60:68, 100:104] = True   # trait de lettre
    vertical = reader._dark_runs(dark, 60)
    horizontal = reader._dark_runs(dark.T, 120).T
    assert vertical[:, 50].sum() == 80 and horizontal[40].sum() == 160
    assert not (vertical | horizontal)[60:68, 100:104].any()


FACTURX = """<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
  xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
  xmlns:udt="urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100">
 <rsm:ExchangedDocument>
  <ram:ID>FA-2026-0077</ram:ID><ram:TypeCode>{type_code}</ram:TypeCode>
  <ram:IssueDateTime><udt:DateTimeString format="102">20261012</udt:DateTimeString></ram:IssueDateTime>
 </rsm:ExchangedDocument>
 <rsm:SupplyChainTradeTransaction>
  <ram:ApplicableHeaderTradeAgreement>
   <ram:SellerTradeParty>
    <ram:Name>Dupré Maintenance</ram:Name>
    <ram:SpecifiedLegalOrganization><ram:ID schemeID="0009">45164790301031</ram:ID></ram:SpecifiedLegalOrganization>
    <ram:SpecifiedTaxRegistration><ram:ID schemeID="VA">FR60421938861</ram:ID></ram:SpecifiedTaxRegistration>
   </ram:SellerTradeParty>
  </ram:ApplicableHeaderTradeAgreement>
  <ram:ApplicableHeaderTradeSettlement>
   <ram:SpecifiedTradeSettlementPaymentMeans>
    <ram:PayeePartyCreditorFinancialAccount><ram:IBANID>FR7630006000011234567890189</ram:IBANID></ram:PayeePartyCreditorFinancialAccount>
   </ram:SpecifiedTradeSettlementPaymentMeans>
   <ram:ApplicableTradeTax><ram:CalculatedAmount>20.00</ram:CalculatedAmount><ram:BasisAmount>100.00</ram:BasisAmount><ram:RateApplicablePercent>20</ram:RateApplicablePercent></ram:ApplicableTradeTax>
   <ram:ApplicableTradeTax><ram:CalculatedAmount>1.10</ram:CalculatedAmount><ram:BasisAmount>20.00</ram:BasisAmount><ram:RateApplicablePercent>5.5</ram:RateApplicablePercent></ram:ApplicableTradeTax>
   <ram:SpecifiedTradePaymentTerms><ram:DueDateDateTime><udt:DateTimeString format="102">20261111</udt:DateTimeString></ram:DueDateDateTime></ram:SpecifiedTradePaymentTerms>
   <ram:SpecifiedTradeSettlementHeaderMonetarySummation>
    <ram:TaxBasisTotalAmount>120.00</ram:TaxBasisTotalAmount>
    <ram:TaxTotalAmount currencyID="EUR">21.10</ram:TaxTotalAmount>
    <ram:GrandTotalAmount>141.10</ram:GrandTotalAmount>
    <ram:DuePayableAmount>141.10</ram:DuePayableAmount>
   </ram:SpecifiedTradeSettlementHeaderMonetarySummation>
  </ram:ApplicableHeaderTradeSettlement>
 </rsm:SupplyChainTradeTransaction>
</rsm:CrossIndustryInvoice>"""


def test_read_facturx_pdf(tmp_path):
    path = _pdf(tmp_path / "fx.pdf", "Facture FA-2026-0077\nTotal TTC 999,99 €\nwww.dupre.fr")
    doc = pymupdf.open(path)
    doc.embfile_add("factur-x.xml", FACTURX.format(type_code="380").encode())
    doc.saveIncr()
    doc.close()
    ext = reader.read(path)
    assert ext.source == "facturx"
    assert _values(ext) | {} == {
        "invoice_number": "FA-2026-0077", "issue_date": date(2026, 10, 12),
        "supplier_name": "Dupré Maintenance", "vat_number": "FR60421938861",
        "siret": "45164790301031", "iban": "FR7630006000011234567890189",
        "due_date": date(2026, 11, 11), "total": 14110, "untaxed": 12000, "tax": 2110,
    }
    assert ext.taxes == [(2000, 10000, 2000), (550, 2000, 110)]
    # Le XML fait foi : le TTC du texte (999,99) est ignoré.
    assert not any(f.check for f in ext.fields.values())


def test_facturx_credit_note_and_hostile_xml():
    assert reader.parse_facturx(FACTURX.format(type_code="381").encode()).value("is_credit_note")
    assert reader.parse_facturx(b"<!DOCTYPE x [<!ENTITY a 'b'>]><x>&a;</x>") is None
    assert reader.parse_facturx(b"<Invoice/>") is None
    assert reader.parse_facturx(b"pas du xml") is None


# ------------------------------------------------------------------ OCR

def _tesseract_fra():
    if shutil.which("tesseract") is None:
        return False
    try:
        pymupdf.get_tessdata()
    except Exception:  # noqa: BLE001
        return False
    return True


needs_ocr = pytest.mark.skipif(not _tesseract_fra(), reason="Tesseract (fra) absent")


def _scan(tmp_path, kind):
    # La police de base n'a pas de glyphe « € » : « EUR » à la place pour l'image.
    text_doc = pymupdf.open(_pdf(tmp_path / "src.pdf", FREE.replace("€", " EUR"), fontsize=12))
    pix = text_doc[0].get_pixmap(dpi=200, colorspace=pymupdf.csGRAY)
    if kind == "png":
        path = tmp_path / "photo.png"
        pix.save(path)
        return path, "image/png"
    scan = pymupdf.open()
    page = scan.new_page(width=text_doc[0].rect.width, height=text_doc[0].rect.height)
    page.insert_image(page.rect, pixmap=pix)
    path = tmp_path / "scan.pdf"
    scan.save(path)
    return path, "application/pdf"


@needs_ocr
@pytest.mark.parametrize("kind", ["pdf", "png"])
def test_read_scanned_invoice(tmp_path, kind):
    path, mime = _scan(tmp_path, kind)
    ext = reader.read(path, mime)
    assert ext.source == "ocr"
    assert ext.value("total") == 3999 and ext.value("tax") == 666
    assert ext.value("invoice_number") == "1400000013"
    assert ext.value("issue_date") == date(2026, 9, 2)
    assert ext.fields["total"].check


def test_ocr_unavailable_warns(tmp_path, monkeypatch):
    path, mime = _scan(tmp_path, "pdf")

    def no_tesseract(page, *args):
        raise RuntimeError("No tessdata specified and Tesseract is not installed")

    monkeypatch.setattr(reader, "_ocr_textpage", no_tesseract)
    ext = reader.read(path, mime)
    assert ext.fields == {} and "OCR indisponible" in ext.warnings[0]
