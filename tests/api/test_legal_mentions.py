"""Lot G2 : mentions légales saisies dans la Structure (seule source), reprises par les factures (PDF
et Factur-X) ; SIREN et activité des tiers."""
import pytest

from app.extensions import db
from app.models import Entity, Sale
from app.services import billing, organization, sale_documents
from test_sales import _draft, admin  # noqa: F401  (fixture)

VAT = "FR44732829320"  # clé de TVA calculée du SIREN 732829320


def _error(resp, status):
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()["error"]


@pytest.fixture()
def tiers(app, login_as):
    return login_as()


def test_structure_holds_the_legal_mentions(admin):  # noqa: F811
    resp = admin.put("/api/v1/organization", json={
        "name": "SCI Exemple", "legal_form": "Société civile immobilière", "share_capital": "274 890,00",
        "rcs_city": "Paris", "vat_number": "fr 44 732 829 320", "naf_code": "68.20B", "naf_nomenclature": "NAFRev2"})
    assert resp.status_code == 200, resp.get_json()
    item = resp.get_json()["item"]
    assert (item["share_capital"], item["vat_number"], item["naf_code"]) == ("274890,00", VAT, "6820B")
    assert item["rcs_mention"] == "123 456 789 RCS Paris"

    fields = _error(admin.put("/api/v1/organization", json={"name": "X", "vat_number": "FR00732829320",
                                                            "naf_code": "68B", "share_capital": "abc"}), 422)["fields"]
    assert set(fields) == {"vat_number", "naf_code", "share_capital"}


def test_rcs_mention_without_registry(instance):
    org = organization.get()
    org.siren, org.rcs_city = "732829320", None
    assert organization.rcs_mention(org) == "SIREN 732829320"
    org.siren = None
    assert organization.rcs_mention(org) == ""


def test_invoice_prints_the_structure_mentions(admin):  # noqa: F811
    org = organization.get()
    org.legal_form, org.share_capital_cents, org.rcs_city, org.vat_number = "SCI", 27489000, "Paris", VAT
    db.session.commit()
    sale = db.session.get(Sale, _draft(admin)["id"])
    html = sale_documents.render_html(sale)
    for expected in ("SCI au capital de 274", "123 456 789 RCS Paris", f"TVA intracommunautaire {VAT}"):
        assert expected in html, expected
    assert sale_documents.einvoice_document(sale).seller.vat_number == VAT


def test_billing_readiness_points_to_the_structure(admin):  # noqa: F811
    organization.get().vat_number = None
    db.session.commit()
    rows = {r["key"]: r for r in billing.readiness(vat_liable=True)}
    assert rows["vat_number"] == {"key": "vat_number", "ok": False,
                                  "label": "N° de TVA intracommunautaire (Configuration › Structure)"}


def test_tiers_siren_from_siret_or_alone(tiers):
    resp = tiers.post("/api/v1/tiers", json={"name": "Établissement", "siret": "732 829 320 00074"})
    assert resp.status_code in (200, 201), resp.get_json()
    assert Entity.query.filter_by(name="Établissement").one().siren == "732829320"

    resp = tiers.post("/api/v1/tiers", json={"name": "Unité légale", "siren": "732 829 320", "naf_code": "68.20B",
                                             "naf_nomenclature": "NAFRev2"})
    assert resp.status_code in (200, 201), resp.get_json()
    entity = Entity.query.filter_by(name="Unité légale").one()
    assert (entity.siren, entity.siret, entity.naf_code, entity.naf_nomenclature) == ("732829320", None, "6820B", "NAFRev2")
    detail = tiers.get(f"/api/v1/tiers/{entity.id}").get_json()["item"]
    assert (detail["siren"], detail["naf_code"]) == ("732829320", "6820B")

    assert "siren" in _error(tiers.post("/api/v1/tiers", json={"name": "X", "siren": "732829321"}), 422)["fields"]
    assert "siren" in _error(tiers.post("/api/v1/tiers", json={"name": "Y", "siren": "552100554",
                                                               "siret": "73282932000074"}), 422)["fields"]


def test_every_siret_writer_keeps_the_siren(app):
    entity = Entity(name="Fournisseur", siret="73282932000074")
    db.session.add(entity)
    db.session.commit()
    assert entity.siren == "732829320"
    entity.siret = None  # SIRET effacé : le SIREN reste
    assert entity.siren == "732829320"
