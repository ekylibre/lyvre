"""Écrans du catalogue, champs fournisseur de l'entité, TVA de l'exercice."""
from datetime import date

from app.extensions import db
from app.models import Account, Entity, FiscalYear, Product, Purchase, PurchaseLine


def _accounts():
    db.session.add_all([Account(code="6061", label="Fournitures non stockables", account_type="EXPENSE"),
                        Account(code="706", label="Prestations de services", account_type="REVENUE")])
    db.session.commit()


def test_create_edit_archive_product(app, login_as):
    _accounts()
    client = login_as()
    assert client.get("/products/new").status_code == 200
    resp = client.post("/products/new", data={"name": "Électricité", "kind": "purchase",
                                              "purchase_account_code": "6061", "vat_rate": "20"})
    assert resp.status_code == 302
    product = Product.query.one()
    assert product.purchase_account.code == "6061" and product.vat_rate_bp == 2000

    page = client.get("/products/").get_data(as_text=True)
    assert "Électricité" in page and "20 %" in page

    resp = client.post(f"/products/{product.id}/edit", data={
        "name": "Électricité", "kind": "both", "purchase_account_code": "6061",
        "sale_account_code": "706", "vat_rate": "5,5"})
    assert resp.status_code == 302
    db.session.refresh(product)
    assert product.sale_account.code == "706" and product.vat_rate_bp == 550

    client.post(f"/products/{product.id}/archive")
    db.session.refresh(product)
    assert not product.active
    assert "<td>Électricité" not in client.get("/products/").get_data(as_text=True)
    assert "<td>Électricité" in client.get("/products/?archived=1").get_data(as_text=True)


def test_invalid_product_redisplays_form(app, login_as):
    _accounts()
    client = login_as()
    resp = client.post("/products/new", data={"name": "Électricité", "kind": "purchase",
                                              "purchase_account_code": "706"})
    assert resp.status_code == 200
    assert "commencer par 6" in resp.get_data(as_text=True)
    assert Product.query.count() == 0


def test_used_product_cannot_be_deleted(app, login_as):
    client = login_as()
    product = Product(name="Assurance", kind="purchase")
    unused = Product(name="Divers", kind="purchase")
    purchase = Purchase(qonto_id="si-1", total_cents=100)
    purchase.lines.append(PurchaseLine(product=product, total_cents=100))
    db.session.add_all([product, unused, purchase])
    db.session.commit()
    client.post(f"/products/{product.id}/delete")
    client.post(f"/products/{unused.id}/delete")
    assert [p.name for p in Product.query.all()] == ["Assurance"]


def test_catalogue_in_compta_menu(app, login_as):
    page = login_as().get("/products/").get_data(as_text=True)
    assert 'href="/products/"' in page


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


def test_fiscal_year_vat_liable(app, login_as):
    client = login_as()
    client.post("/fiscal-years/new", data={"label": "2027", "start_date": "2027-01-01",
                                           "end_date": "2027-12-31", "vat_liable": "1"})
    client.post("/fiscal-years/new", data={"label": "2028", "start_date": "2028-01-01",
                                           "end_date": "2028-12-31"})
    fy27, fy28 = FiscalYear.query.order_by(FiscalYear.start_date).all()
    assert fy27.vat_liable and not fy28.vat_liable

    client.post(f"/fiscal-years/{fy28.id}/vat", data={"vat_liable": "1"})
    client.post(f"/fiscal-years/{fy27.id}/vat", data={"vat_liable": "0"})
    db.session.refresh(fy27)
    db.session.refresh(fy28)
    assert fy28.vat_liable and not fy27.vat_liable
    assert "Non soumis" in client.get("/fiscal-years/").get_data(as_text=True)


def test_closed_fiscal_year_vat_unchanged(app, login_as):
    client = login_as()
    fy = FiscalYear(label="2024", start_date=date(2024, 1, 1), end_date=date(2024, 12, 31),
                    closed=True)
    db.session.add(fy)
    db.session.commit()
    client.post(f"/fiscal-years/{fy.id}/vat", data={"vat_liable": "1"})
    db.session.refresh(fy)
    assert not fy.vat_liable
