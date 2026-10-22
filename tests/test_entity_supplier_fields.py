"""Champs fournisseur de la fiche entité (n° de TVA, SIRET, IBAN, produit par défaut).

Catalogue et exercices : tests d'API dans tests/api/test_referentials.py.
"""
from app.extensions import db
from app.models import Account, Entity, Product


def _accounts():
    db.session.add_all([Account(code="6061", label="Fournitures non stockables", account_type="EXPENSE"),
                        Account(code="706", label="Prestations de services", account_type="REVENUE")])
    db.session.commit()


def test_entity_supplier_fields(app, login_as):
    _accounts()
    product = Product(name="Électricité", kind="purchase",
                      purchase_account=Account.query.filter_by(code="6061").one())
    db.session.add(product)
    db.session.commit()
    client = login_as()
    assert "Électricité (6061)" in client.get("/entities/new").get_data(as_text=True)
    client.post("/entities/new", data={"name": "EDF", "entity_type": "FOURNISSEUR",
                                       "default_product_id": str(product.id),
                                       "vat_number": "fr 03 552081317",
                                       "siret": "552 081 317 66522",
                                       "iban": "fr76 3000 4000 0312 3456 7890 143"})
    edf = Entity.query.filter_by(name="EDF").one()
    assert edf.default_product is product
    assert edf.vat_number == "FR03552081317" and edf.iban == "FR7630004000031234567890143"
    assert edf.siret == "55208131766522"
    assert "SIRET <code>55208131766522</code>" in client.get(f"/entities/{edf.id}").get_data(as_text=True)

    page = client.post(f"/entities/{edf.id}/edit", data={"name": "EDF", "entity_type": "FOURNISSEUR",
                                                         "siret": "552081317"})
    assert "14 chiffres" in page.get_data(as_text=True)
    db.session.refresh(edf)
    assert edf.siret == "55208131766522"

    client.post(f"/entities/{edf.id}/edit", data={"name": "EDF", "entity_type": "FOURNISSEUR",
                                                  "default_product_id": ""})
    db.session.refresh(edf)
    assert edf.default_product_id is None and edf.vat_number is None
