"""Lot L2 : modèles de bail (livrés, modifiables, assainis, à relire), texte du bail figé à la
validation, retouche, régénération, PDF (tableau des biens, décomposition du loyer, pieds de page)."""
from datetime import date
from io import BytesIO

import pytest
from pypdf import PdfReader

from app.extensions import db
from app.models import Associate, Instance, Lease, LeaseTemplate
from app.services import lease_documents, organization
from test_lease_wizard import U2_ITEMS, _tenant, admin  # noqa: F401  (fixture)

API = "/api/v1/leases"
YEAR = date.today().year


def _pdf_text(data: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(BytesIO(data)).pages)


@pytest.fixture()
def u2(admin):  # noqa: F811
    org = organization.get()
    org.name, org.legal_form, org.rcs_city, org.siren = "SCI Les Chênes", "Société civile immobilière", "Saintes", "123456782"
    Instance.query.one().has_associates = True
    db.session.commit()
    admin.post("/api/v1/associates", json={"new_name": "Gérante Dupont", "is_manager": True})
    lease = admin.post(API, json={
        "draft": True, "entity_id": _tenant().id, "unit_label": "La Vauzelle", "kind": "derogatory",
        "premises_label": "La Vauzelle", "start_date": date(YEAR, 10, 1).isoformat(),
        "end_date": date(YEAR + 3, 9, 30).isoformat(), "deposit": "200", "index_code": "ILC", "revision_months": "36",
        "index_reference_period": "2025-Q2", "index_reference_value": "135.30"}).get_json()["item"]
    for letter, label, nature, area, price in U2_ITEMS:
        admin.post(f"{API}/{lease['id']}/items", json={"letter": letter, "label": label, "nature": nature, "area_m2": area,
                                                       "unit_price": price, "cadastral_refs": "AH 248"})
    return lease["id"]


def test_activation_freezes_the_u2_lease_text(admin, u2):  # noqa: F811
    preview = admin.get(f"{API}/{u2}/preview.pdf")  # brouillon : modèle rendu à la volée
    assert preview.status_code == 200 and preview.mimetype == "application/pdf"
    assert Lease.query.get(u2).document_html is None

    resp = admin.post(f"{API}/{u2}/activate", json={"frequency": "yearly"})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["item"]["document"]["frozen"] is True
    text = Lease.query.get(u2).document_html
    for expected in ("SCI Les Chênes, Société civile immobilière, 123 456 782 RCS Saintes", "sa gérance, Gérante Dupont",
                     "au lieu-dit « La Vauzelle »", "les éléments A, B, C, E, D et K",
                     "trois années", f"le 1er octobre {YEAR}", f"le 30 septembre {YEAR + 3}",
                     "528,40 € (cinq cent vingt-huit euros et quarante centimes)",
                     "Prix de base de 2,00 € / m² / an : 155 m² × 2,00 € = 310,00 €",
                     "Prix de base de 140,00 € / ha / an : 1,56 ha × 140,00 € = 218,40 €",
                     "indice des loyers commerciaux (ILC)", "périodes triennales", "2e trimestre 2025 : 135,30",
                     "200,00 € (deux cents euros)"):
        assert expected in text, expected
    assert "<table class='premises'>" in text and "<p><table" not in text
    assert text.index("€ / m² / an") < text.index("€ / ha / an")  # bâtiments puis terres, comme le bail
    assert "<td class='num'>155 m²</td></tr></tfoot>" in text  # bâti : la surface des bâtiments par défaut

    pdf = _pdf_text(admin.get(f"{API}/{u2}/preview.pdf").data)
    assert "BAIL DÉROGATOIRE COMMERCIAL" in pdf and "Potager" in pdf and "Page 1 /" in pdf
    assert "Bail dérogatoire commercial — La Vauzelle" in pdf  # pied de page


def test_retouch_and_regenerate(admin, u2):  # noqa: F811
    admin.post(f"{API}/{u2}/activate", json={"frequency": "yearly"})
    body = admin.get(f"{API}/{u2}/document").get_json()["item"]["body_html"]
    resp = admin.put(f"{API}/{u2}/document", json={"body_html": body + "<p>Clause particulière.</p><script>x()</script>"})
    assert resp.status_code == 200 and resp.get_json()["item"]["document"]["edited"] is True
    lease = db.session.get(Lease, u2)
    assert lease.document_html.endswith("<p>Clause particulière.</p>")
    assert '<table class="premises">' in lease.document_html  # styles du PDF gardés à la retouche
    admin.put("/api/v1/lease-templates/derogatory", json={"body_html": "<h1>Nouveau modèle</h1><p>{{ preneur.nom }}</p>"})
    assert "Clause particulière" in db.session.get(Lease, u2).document_html  # le modèle ne touche pas un texte figé
    resp = admin.post(f"{API}/{u2}/document/regenerate")
    assert resp.get_json()["item"]["document"]["edited"] is False
    assert db.session.get(Lease, u2).document_html == "<h1>Nouveau modèle</h1><p>Association Preneuse</p>"


def test_templates_delivered_saved_and_reset(admin, u2):  # noqa: F811
    body = admin.get("/api/v1/lease-templates").get_json()
    assert [(t["kind"], t["reviewed"]) for t in body["items"]] == [
        ("derogatory", False), ("commercial", False), ("residential", False), ("rural", False)]
    assert {"value": "{{ biens.tableau }}", "label": "Biens : tableau"} in body["meta"]["fields"]

    resp = admin.put("/api/v1/lease-templates/residential",
                     json={"body_html": '<p onclick="x">Loyer {% if loyer.annuel &gt; "" %}{{ loyer.annuel }}{% endif %}</p>'
                                        '<img src="http://exemple.org/x.png"><a href="javascript:x()">lien</a>'})
    assert resp.status_code == 200, resp.get_json()
    item = resp.get_json()["item"]
    assert item["reviewed"] is True and item["version"] == 2
    assert item["body_html"] == '<p>Loyer {% if loyer.annuel &gt; "" %}{{ loyer.annuel }}{% endif %}</p><a>lien</a>'

    assert admin.put("/api/v1/lease-templates/residential", json={"body_html": "<p>{% if %}</p>"}).status_code == 422
    assert admin.put("/api/v1/lease-templates/residential", json={"body_html": ""}).status_code == 422
    assert admin.get("/api/v1/lease-templates/inconnu").status_code == 404

    preview = admin.post("/api/v1/lease-templates/residential/preview",
                         json={"body_html": "<p>{{ loyer.mensuel }}</p>", "lease_id": u2})
    assert preview.status_code == 422 and "Champ inconnu" in preview.get_json()["error"]["message"]
    preview = admin.post("/api/v1/lease-templates/residential/preview", json={"body_html": item["body_html"], "lease_id": u2})
    assert preview.status_code == 200 and "Loyer 528,40 €" in _pdf_text(preview.data)

    reset = admin.post("/api/v1/lease-templates/residential/reset").get_json()["item"]
    assert reset["reviewed"] is False and "CONTRAT DE LOCATION" in reset["body_html"]


def test_every_delivered_template_renders(admin, u2):  # noqa: F811
    lease = db.session.get(Lease, u2)
    for kind in ("derogatory", "commercial", "residential", "rural"):
        html = lease_documents.render_body(lease_documents.default_body(kind), lease)
        assert "Gérante Dupont" in html and "528,40 €" in html, kind
    assert LeaseTemplate.query.count() == 0  # le rendu seul ne crée pas de modèle


def test_templates_reserved_to_instance_admin(app, login_as):
    assert login_as(role="treasurer").get("/api/v1/lease-templates").status_code == 403


def test_lease_without_kind_has_no_text(admin):  # noqa: F811
    resp = admin.post(API, json={"entity_id": _tenant().id, "unit_label": "Garage", "start_date": date.today().isoformat(),
                                 "rent": "80"})
    lease_id = resp.get_json()["item"]["id"]
    assert resp.get_json()["item"]["document"]["frozen"] is False
    preview = admin.get(f"{API}/{lease_id}/preview.pdf")
    assert preview.status_code == 422 and "type du bail" in preview.get_json()["error"]["message"]
    assert Associate.query.count() == 0
