"""Catalogue : taux de TVA, produit par défaut, validation, utilisation."""
import pytest

from app.extensions import db
from app.models import Account, Entity, Product, Purchase, PurchaseLine
from app.services import catalog
from app.services.catalog import CatalogError


def _accounts(*codes):
    for code in codes:
        db.session.add(Account(code=code, label=f"Compte {code}", account_type="EXPENSE"))
    db.session.commit()


@pytest.mark.parametrize("value, expected", [
    ("20", 2000), ("5.5", 550), ("5,5", 550), ("22.00", 2200), ("2,1 %", 210), ("0", 0),
    ("", None), (None, None), ("  ", None),
])
def test_parse_rate_bp(value, expected):
    assert catalog.parse_rate_bp(value) == expected


@pytest.mark.parametrize("value", ["abc", "-1", "101", "5.555"])
def test_parse_rate_bp_invalid(value):
    with pytest.raises(ValueError):
        catalog.parse_rate_bp(value)


@pytest.mark.parametrize("bp, expected", [
    (2000, "20 %"), (550, "5,5 %"), (210, "2,1 %"), (0, "0 %"), (None, ""),
])
def test_format_rate(bp, expected):
    assert catalog.format_rate(bp) == expected


def test_default_product_uses_first_existing_account(session):
    _accounts("628", "606")
    product = catalog.default_purchase_product()
    assert product.name == "Achats divers" and product.purchase_account.code == "628"
    assert catalog.default_purchase_product().id == product.id  # créé une seule fois


def test_default_product_prefers_6068(session):
    _accounts("628", "6068")
    assert catalog.default_purchase_product().purchase_account.code == "6068"


def test_product_for_supplier(session):
    _accounts("6068", "6061")
    elec = Product(name="Électricité", kind="purchase",
                   purchase_account=Account.query.filter_by(code="6061").one())
    edf = Entity(name="EDF", entity_type="FOURNISSEUR", default_product=elec)
    db.session.add_all([elec, edf])
    db.session.commit()
    assert catalog.product_for(edf) is elec
    assert catalog.product_for(None).name == "Achats divers"
    elec.active = False  # archivé : plus proposé
    assert catalog.product_for(edf).name == "Achats divers"


def test_validate_product_data(session):
    _accounts("6061", "706")
    db.session.add(Account(code="60", label="Achats", account_type="EXPENSE", is_header=True))
    db.session.commit()
    data = catalog.validate_product_data({"name": " Électricité ", "kind": "purchase",
                                          "purchase_account_code": "6061", "vat_rate": "20",
                                          "sale_account_code": "706"})
    assert data["name"] == "Électricité" and data["vat_rate_bp"] == 2000
    assert data["sale_account_id"] is None  # sens achat : compte de vente ignoré

    cases = [
        ({"name": ""}, "obligatoire"),
        ({"name": "X", "kind": "purchase"}, "compte d'achat"),
        ({"name": "X", "kind": "sale", "sale_account_code": "6061"}, "commencer par 7"),
        ({"name": "X", "kind": "purchase", "purchase_account_code": "999"}, "introuvable"),
        ({"name": "X", "kind": "purchase", "purchase_account_code": "60"}, "en-tête"),
        ({"name": "X", "kind": "both", "purchase_account_code": "6061"}, "compte de vente"),
        ({"name": "X", "kind": "purchase", "purchase_account_code": "6061", "vat_rate": "x"}, "invalide"),
    ]
    for form, message in cases:
        with pytest.raises(CatalogError, match=message):
            catalog.validate_product_data(form)

    db.session.add(Product(name="Électricité", kind="purchase"))
    db.session.commit()
    with pytest.raises(CatalogError, match="existe déjà"):
        catalog.validate_product_data({"name": "Électricité", "kind": "purchase",
                                       "purchase_account_code": "6061"})


def test_usage_count(session):
    product = Product(name="Assurance", kind="purchase")
    purchase = Purchase(qonto_id="si-1", total_cents=100)
    purchase.lines.append(PurchaseLine(product=product, total_cents=100))
    db.session.add_all([product, purchase,
                        Entity(name="MAIF", entity_type="FOURNISSEUR", default_product=product)])
    db.session.commit()
    assert catalog.usage_count(product) == 2
