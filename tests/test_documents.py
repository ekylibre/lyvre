"""Lot NV5 : navigateur des documents de l'instance (claudedocs/design_navigation.md § 6)."""
from datetime import date

from app.extensions import db
from app.models import FiscalYear, Purchase
from app.services import documents


def _seed():
    fy25 = FiscalYear(label="2025", start_date=date(2025, 1, 1), end_date=date(2025, 12, 31), fec_path="fec/x.txt")
    fy26 = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    db.session.add_all([fy25, fy26])
    for i in range(55):
        db.session.add(Purchase(source="upload", supplier_name="Coopérative du Val" if i % 2 else "EDF",
                                issue_date=date(2026, 1, 1 + i % 28), attachment_path=f"achats/{i}.pdf",
                                attachment_name=f"facture-{i}.pdf", attachment_mime="application/pdf",
                                attachment_size=1000 + i))
    db.session.add(Purchase(source="upload", supplier_name="Sans pièce", issue_date=date(2026, 2, 1)))
    db.session.add(Purchase(source="upload", supplier_name="Ancien", issue_date=date(2024, 6, 1),
                            attachment_path="achats/old.png", attachment_name="old.png", attachment_mime="image/png"))
    db.session.commit()
    return fy25, fy26


def test_browse_facets_filters_and_pages(app, login_as):
    login_as()
    fy25, fy26 = _seed()
    data = documents.browse()
    assert data["total"] == 57 and len(data["items"]) == documents.PAGE_SIZE
    kinds = {k["value"]: k["count"] for k in data["facets"]["kinds"]}
    assert kinds == {"purchase": 56, "fec": 1}                       # pièces seulement, FEC figé (D-NV3)
    years = {f["label"]: f["count"] for f in data["facets"]["fiscal_years"]}
    assert years == {"2026": 55, "2025": 1, "Hors exercice": 1}
    first = data["items"][0]
    assert first["file_url"].startswith("/purchases/") and first["file_url"].endswith("/attachment")
    assert first["origin"]["url"].startswith("/purchases/") and first["preview"] is True
    assert first["fiscal_year"]["label"] == "2026"
    assert len(documents.browse(page=2)["items"]) == 7
    only_fec = documents.browse(kind="fec")
    assert [d["file_url"] for d in only_fec["items"]] == [f"/fiscal-years/{fy25.id}/fec"]
    assert only_fec["items"][0]["size"] is None                     # fichier absent : pas de taille
    assert documents.browse(fiscal_year_id=fy25.id)["total"] == 1
    assert documents.browse(q="coopérative")["total"] == 27         # recherche sur le tiers


def test_api(app, login_as):
    client = login_as(role="accountant")                            # lecture seule : voit les documents
    _seed()
    body = client.get("/api/v1/documents?kind=purchase&q=edf").get_json()
    assert body["total"] == 28 and body["items"][0]["kind_label"] == "Factures d'achat"
    assert client.get("/api/v1/documents?kind=inconnu").status_code == 422
    assert client.get("/documents/").status_code == 200


def test_associate_sources_follow_the_option(app, login_as):
    login_as()
    assert not documents.BY_KIND["share_movement"].enabled()       # instance de test sans associés
    assert {s.kind for s in documents.SOURCES} >= {"purchase", "sale", "bank_statement", "lease", "fec"}
