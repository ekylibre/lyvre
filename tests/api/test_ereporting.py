"""Lot AG10.e : Factur-X agricole (note BAR = B2C, RFA sans motif sourcé, facture mixte à un particulier) et
e-reporting B2C des ventes directes (agrégats, export JSON au format SUPER PDP). Données fictives."""
import json
from datetime import date

import pymupdf
import pytest

from app.extensions import db
from app.models import (
    Account, Entity, EreportingExport, FiscalYear, Journal, Sale, SaleLine, SimpleCategory, TaxProfile,
)
from app.services import einvoice, einvoice_reader, ereporting, organization, reg_params, sale_documents, sale_issue
from app.services.ledger import post_entry

from test_agri_fixtures import _agri_instance

API = "/api/v1/ereporting"


@pytest.fixture()
def farm(app, login_as):
    client = login_as(role="admin")
    _agri_instance()
    org = organization.get()
    org.name, org.siren, org.address_line1, org.postal_code, org.city = "EARL des Essais", "552100554", "1 chemin", "17000", "La Rochelle"
    db.session.add(FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), vat_liable=True,
                              vat_on_receipts=False))
    db.session.commit()
    return client


def _doc(**kw):
    party = einvoice.Party("EARL des Essais", address1="1 chemin", postcode="17000", city="La Rochelle", siren="552100554")
    return einvoice.Document(number="F-2026-0001", issue_date=date(2026, 10, 1), seller=party,
                             buyer=einvoice.Party("Mme Martin", address1="2 rue", postcode="17000", city="La Rochelle"),
                             lines=[einvoice.Line("Panier de légumes", 1000, 2000, 2000, 550)], **kw)


def test_b2c_note_in_cii():
    xml = einvoice.cii_xml(_doc(b2c=True))
    inv = einvoice_reader.parse_xml(xml)
    assert ("BAR", "B2C") in inv.notes
    assert ("BAR", "B2C") not in einvoice_reader.parse_xml(einvoice.cii_xml(_doc())).notes


def test_rfa_exemption_from_param_only():
    doc = _doc(vat_exempt=True, exempt_reason=("CODE-SOURCE", "Motif sourcé"))
    inv = einvoice_reader.parse_xml(einvoice.cii_xml(doc))
    assert inv.taxes[0].exemption == "Motif sourcé" and inv.taxes[0].category == "E"
    assert "293 B" in einvoice_reader.parse_xml(einvoice.cii_xml(_doc(vat_exempt=True))).taxes[0].exemption


def _sale(person_kind="individual", natures=("goods",), vat_mode="debits"):
    entity = Entity(name=f"Client {person_kind} {len(natures)}", entity_type="CLIENT", person_kind=person_kind,
                    address_line1="2 rue", postal_code="17000", city="La Rochelle")
    account = Account.query.filter_by(code="7011").one()
    sale = Sale(kind="invoice", status="issued", number=f"F-{person_kind}-{len(natures)}", entity=entity,
                issue_date=date(2026, 10, 1), vat_mode=vat_mode,
                lines=[SaleLine(position=i, label=f"Ligne {i}", untaxed_cents=1000, total_cents=1000, account_id=account.id,
                                nature=n) for i, n in enumerate(natures)])
    db.session.add(sale)
    db.session.commit()
    return sale


def test_sale_b2c_and_mixed(farm):
    sale = _sale()
    assert sale_documents.is_b2c(sale) and sale_documents.einvoice_document(sale).b2c
    assert not sale_documents.is_b2c(_sale("company"))
    mixed = _sale(natures=("goods", "services"))
    mixed.status = "draft"
    db.session.commit()
    assert any("biens et services" in p for p in sale_issue.issue_problems(mixed))


def test_rfa_without_param_no_facturx(farm, monkeypatch):
    db.session.add(TaxProfile(kind="vat_regime", value="rfa", start_date=date(2026, 1, 1)))
    db.session.commit()
    sale = _sale("company", vat_mode="none")
    assert sale_documents.is_rfa(sale) and sale_documents.rfa_exemption(sale) is None
    assert "pas encore sourcé" in sale_documents.facturx_warning(sale)
    assert sale_documents.exempt_mention(sale) is None                   # pas de « 293 B » pour un producteur au RFA
    pdf = pymupdf.open("pdf", sale_documents.render_pdf(sale))
    assert pdf.embfile_count() == 0
    real = reg_params.value
    monkeypatch.setattr(reg_params, "value", lambda key, on=None, default=None: (
        {"code": "CODE-SOURCE", "reason": "Motif sourcé", "mention": "Mention sourcée"}
        if key == sale_documents.RFA_PARAM else real(key, on, default)))
    assert sale_documents.facturx_warning(sale) is None and sale_documents.exempt_mention(sale) == "Mention sourcée"
    assert sale_documents.einvoice_document(sale).exempt_reason == ("CODE-SOURCE", "Motif sourcé")


def _entry(journal, day, lines, source=None):
    fy = FiscalYear.query.one()
    j = Journal.query.filter_by(code=journal).first() or Journal(code=journal, label=journal)
    db.session.add(j)
    db.session.flush()
    rows = [{"account_id": Account.query.filter_by(code=c).one().id, "label": "x", "debit_cents": d, "credit_cents": cr,
             "vat_code": v} for c, d, cr, v in lines]
    return post_entry(fy.id, j.id, day, "Vente", rows, source=source or "MANUAL", commit=True)


def _accounts():
    for code, label, kind in (("530", "Caisse", "TRESORERIE"), ("512", "Banque", "TRESORERIE"), ("44571", "TVA collectée", "TIERS"),
                              ("706", "Prestations", "PRODUIT")):
        if Account.query.filter_by(code=code, is_header=False).first() is None:
            db.session.add(Account(code=code, label=label, account_type=kind))
    db.session.commit()


def test_aggregate_and_export(farm):
    _accounts()
    # Marché : caisse, légumes à 5,5 %.
    _entry("CA", date(2026, 10, 3), [("530", 10550, 0, None), ("7011", 0, 10000, None), ("44571", 0, 550, "V55")])
    _entry("CA", date(2026, 10, 3), [("530", 2110, 0, None), ("7011", 0, 2000, None), ("44571", 0, 110, "V55")])
    # Prestation encaissée en banque, catégorie « vente directe » (706).
    db.session.add(SimpleCategory(code="accueil", label="Accueil à la ferme", kind="income",
                                  account_id=Account.query.filter_by(code="706", is_header=False).one().id))
    db.session.commit()
    _entry("BQ", date(2026, 10, 4), [("512", 12000, 0, None), ("706", 0, 10000, "V20"), ("44571", 0, 2000, "V20")])
    # Vente facturée : exclue (la facture part avec la note BAR).
    _entry("VE", date(2026, 10, 5), [("512", 1055, 0, None), ("7011", 0, 1000, None), ("44571", 0, 55, "V55")], source="SALE")
    data = farm.get(f"{API}?start=2026-10-01&end=2026-10-31").get_json()
    assert [(d["date"], d["category"], d["base_cents"], d["tax_cents"]) for d in data["days"]] == [("2026-10-03", "TLB1", 12000, 660)]
    category = next(c for c in data["categories"] if c["label"] == "Accueil à la ferme")
    assert farm.put(f"{API}/categories", json={"ids": [category["id"]]}).status_code == 200
    data = farm.get(f"{API}?start=2026-10-01&end=2026-10-31").get_json()
    assert [(d["date"], d["category"], d["base_cents"], d["tax_cents"]) for d in data["days"]] == [
        ("2026-10-03", "TLB1", 12000, 660), ("2026-10-04", "TPS1", 10000, 2000)]
    assert data["pending_days"] == ["2026-10-03", "2026-10-04"]
    assert ereporting.months_pending(date(2026, 10, 1), date(2026, 11, 30)) == [date(2026, 10, 31)]
    resp = farm.post(f"{API}/export", json={"start": "2026-10-01", "end": "2026-10-31"})
    assert resp.status_code == 200 and "attachment" in resp.headers["Content-Disposition"]
    body = json.loads(resp.data)
    assert body["data"][0] == {"date": "2026-10-03", "category_code": "TLB1", "currency": "EUR", "role_code": "SE",
                               "tax_exclusive_amount": "120.00", "tax_total": "6.60",
                               "tax_subtotals": [{"tax_percent": "5.50", "taxable_amount": "120.00", "tax_total": "6.60"}]}
    assert EreportingExport.query.one().transactions == 2
    assert farm.get(f"{API}?start=2026-10-01&end=2026-10-31").get_json()["pending_days"] == []
    assert ereporting.months_pending(date(2026, 10, 1), date(2026, 11, 30)) == []
    csv = farm.get(f"{API}/csv?start=2026-10-01&end=2026-10-31").data.decode("utf-8-sig")
    assert "2026-10-04;TPS1;20;100,00;20,00" in csv
    assert farm.post(f"{API}/export", json={"start": "2026-11-01", "end": "2026-11-30"}).status_code == 409


def test_not_agri(app, login_as):
    assert login_as(role="admin").get(API).status_code == 404
