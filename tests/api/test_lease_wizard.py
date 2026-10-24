"""Lot L1 : assistant de bail — brouillon, lignes (m², hectares, forfait), loyer annuel, validation
avec une ligne de facture récurrente par ligne de bail, gérants, forme juridique."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, Associate, BankAccount, Entity, FiscalYear, Lease, LeaseItem
from app.services import leases, organization

TODAY = date.today()
API = "/api/v1/leases"

# Bail dérogatoire de la SCI (récit U2) : lettre, désignation, nature, surface, prix annuel par unité.
U2_ITEMS = [
    ("A", "Potager", "land", 350, "140"),
    ("B", "Bureau", "building", 40, "2"),
    ("C", "Salle préparation", "building", 115, "2"),
    ("E", "Orme 5 têtes devant", "land", 4940, "140"),
    ("D", "Orme 5 têtes 1", "land", 10323, "140"),
    ("K", "Forage", "flat", 0, "0"),
]


@pytest.fixture()
def admin(app, login_as):
    client = login_as(role="admin")
    org = organization.get()
    org.address_line1, org.postal_code, org.city, org.siren = "1 rue des Exemples", "17250", "Saint-Porchaire", "123456789"
    bank = Account(code="512", label="Banque", account_type="TRESORERIE")
    db.session.add_all([
        Account(code="411", label="Clients", account_type="TIERS", is_header=True),
        Account(code="706", label="Loyers", account_type="PRODUIT"),
        Account(code="708", label="Charges refacturées", account_type="PRODUIT"), bank,
        FiscalYear(label="An", start_date=date(TODAY.year, 1, 1), end_date=date(TODAY.year, 12, 31)),
        Entity(name="Association Preneuse", entity_type="CLIENT", address_line1="4 rue C", postal_code="17250",
               city="Geay", email="preneur@example.org"),
    ])
    db.session.flush()
    db.session.add(BankAccount(label="Banque", kind="bank", account_id=bank.id))
    db.session.commit()
    return client


def _tenant():
    return Entity.query.filter_by(name="Association Preneuse").one()


def _draft(admin, **extra):
    resp = admin.post(API, json={"draft": True, "entity_id": _tenant().id, "unit_label": "La Vauzelle",
                                 "start_date": date(TODAY.year, 1, 1).isoformat(), "kind": "derogatory", **extra})
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["item"]


def _add(admin, lease_id, **data):
    resp = admin.post(f"{API}/{lease_id}/items", json=data)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


def test_u2_lease_lines_and_annual_rent(admin):
    lease = _draft(admin, premises_label="La Vauzelle", index_code="ILC", revision_months="36",
                   index_reference_period="2025-Q2", index_reference_value="135.30")
    assert lease["status"] == "draft" and lease["rent_cents"] == 0 and lease["next_date"] is None
    for letter, label, nature, area, price in U2_ITEMS:
        body = _add(admin, lease["id"], letter=letter, label=label, nature=nature, area_m2=area, unit_price=price,
                    cadastral_refs="AH 248")
    lease = body["lease"]
    assert [i["billing_unit"] for i in lease["items"]] == ["ha", "m2", "m2", "ha", "ha", "flat"]
    assert [i["annual_cents"] for i in lease["items"]] == [560, 8000, 23000, 6860, 14420, 0]
    assert lease["annual_cents"] == 52840  # 155 m² × 2 € + 1,56 ha × 140 €

    resp = admin.post(f"{API}/{lease['id']}/activate", json={"frequency": "yearly", "due_day": "1", "vat_rate": "0"})
    assert resp.status_code == 200, resp.get_json()
    item = resp.get_json()["item"]
    assert item["status"] == "active" and item["rent_cents"] == 52840 and item["next_date"]
    lines = Lease.query.one().recurrence.template.lines
    assert [l.label for l in lines] == [  # le forage (0 €) n'est pas facturé
        "Loyer {periode} — A Potager", "Loyer {periode} — B Bureau", "Loyer {periode} — C Salle préparation",
        "Loyer {periode} — E Orme 5 têtes devant", "Loyer {periode} — D Orme 5 têtes 1"]
    assert sum(l.unit_price_cents for l in lines) == 52840
    assert item["next_revision_date"] == date(TODAY.year + 3, 1, 1).isoformat()


def test_period_rounding_goes_to_last_line(admin):
    lease = _draft(admin)
    for label in ("Un", "Deux", "Trois"):
        _add(admin, lease["id"], label=label, nature="flat", unit_price="100")
    admin.post(f"{API}/{lease['id']}/activate", json={"frequency": "monthly"})
    lines = Lease.query.one().recurrence.template.lines
    assert [l.unit_price_cents for l in lines] == [833, 833, 834]  # 300 € / 12 = 25 €


def test_letters_and_validation(admin):
    lease = _draft(admin)
    first = _add(admin, lease["id"], label="Maison", nature="building", area_m2=90, unit_price="80")["item"]
    assert first["letter"] == "A" and first["billing_unit"] == "m2"
    assert _add(admin, lease["id"], label="Jardin", nature="land", area_m2=500)["item"]["letter"] == "B"
    resp = admin.post(f"{API}/{lease['id']}/items", json={"label": "Garage", "letter": "a"})
    assert resp.status_code == 422 and "déjà utilisée" in resp.get_json()["error"]["message"]
    assert admin.post(f"{API}/{lease['id']}/items", json={"label": ""}).status_code == 422
    assert admin.post(f"{API}/{lease['id']}/items", json={"label": "X", "nature": "?"}).status_code == 422

    empty = _draft(admin, unit_label="Vide")
    assert admin.post(f"{API}/{empty['id']}/activate", json={}).status_code == 422
    _add(admin, empty["id"], label="Gratuit", nature="flat", unit_price="0")
    resp = admin.post(f"{API}/{empty['id']}/activate", json={})
    assert resp.status_code == 422 and "loyer annuel est nul" in resp.get_json()["error"]["message"]


def test_active_lease_lines_follow_and_draft_rules(admin):
    lease = _draft(admin)
    item = _add(admin, lease["id"], label="Maison", nature="flat", unit_price="1200")["item"]
    assert admin.post(f"{API}/{lease['id']}/deposit", json={"bank_account_id": BankAccount.query.one().id}).status_code == 409
    admin.post(f"{API}/{lease['id']}/activate", json={"frequency": "monthly", "charges": "20"})
    assert [l.unit_price_cents for l in Lease.query.one().recurrence.template.lines] == [10000, 2000]

    resp = admin.patch(f"{API}/{lease['id']}/items/{item['id']}", json={"unit_price": "2400"})
    assert resp.get_json()["lease"]["rent_cents"] == 20000
    assert [l.unit_price_cents for l in Lease.query.one().recurrence.template.lines] == [20000, 2000]
    assert admin.delete(f"{API}/{lease['id']}/items/{item['id']}").status_code == 409  # dernière ligne
    assert admin.delete(f"{API}/{lease['id']}").status_code == 409  # bail validé

    draft = _draft(admin, unit_label="Abandonné")
    _add(admin, draft["id"], label="Cave", nature="flat", unit_price="10")
    assert admin.delete(f"{API}/{draft['id']}").status_code == 200
    assert LeaseItem.query.filter_by(lease_id=draft["id"]).count() == 0


def test_terms_validation(admin):
    resp = admin.post(API, json={"draft": True, "entity_id": _tenant().id, "unit_label": "X",
                                 "start_date": TODAY.isoformat(), "kind": "inconnu"})
    assert resp.status_code == 422
    resp = admin.post(API, json={"draft": True, "entity_id": _tenant().id, "unit_label": "X",
                                 "start_date": TODAY.isoformat(), "index_code": "IRL", "revision_months": "24"})
    assert resp.status_code == 422
    lease = _draft(admin, index_code="IRL")
    assert lease["revision_months"] == "12"
    lease = admin.patch(f"{API}/{lease['id']}", json={"index_code": ""}).get_json()["item"]
    assert lease["revision_months"] == "" and lease["next_revision_date"] is None


def test_one_shot_lease_gets_a_flat_line(admin):
    resp = admin.post(API, json={"entity_id": _tenant().id, "unit_label": "Appartement 2B",
                                 "start_date": TODAY.isoformat(), "rent": "800", "frequency": "quarterly"})
    assert resp.status_code == 201, resp.get_json()
    item = resp.get_json()["item"]
    assert item["status"] == "active" and item["rent_cents"] == 80000 and item["frequency"] == "quarterly"
    assert [(i["label"], i["annual_cents"]) for i in item["items"]] == [("Appartement 2B", 320000)]


def test_manager_and_organization_fields(admin):
    from app.models import Instance
    Instance.query.one().has_associates = True
    db.session.commit()
    assoc = admin.post("/api/v1/associates", json={"new_name": "Gérante Dupont", "is_manager": True})
    assert assoc.status_code == 201, assoc.get_json()
    assert Associate.query.one().is_manager is True
    associate_id = Associate.query.one().id
    admin.patch(f"/api/v1/associates/{associate_id}", json={"is_manager": False})
    assert db.session.get(Associate, associate_id).is_manager is False
    resp = admin.put("/api/v1/organization", json={"name": "SCI Test", "legal_form": "Société civile immobilière",
                                                   "rcs_city": "Saintes"})
    assert resp.status_code == 200, resp.get_json()
    assert (organization.get().legal_form, organization.get().rcs_city) == ("Société civile immobilière", "Saintes")
    assert leases.hectares(4940) == leases.hectares(4949) and str(leases.hectares(350)) == "0.04"
