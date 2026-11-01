"""Lot T2 : codes de TVA portés par les lignes d'écriture (achats, autoliquidation, ventes en France, dans l'UE
et hors UE, TVA à l'encaissement), régime TVA des tiers, saisie manuelle et contrepassation
(claudedocs/design_societe_tva.md § 3.2-3.3)."""
import pytest

from app.extensions import db
from app.models import Account, BankAccount, Entity, JournalEntry, Product, PurchaseLine, Sale, SalePayment
from app.services import purchase_posting, sale_documents, vat_codes
from app.services.ledger import reverse
from test_purchase_posting import _purchase, books  # noqa: F401  (fixture)
from test_sale_payments import API, TODAY, _invoice, admin  # noqa: F401  (fixture)


def _coded(entry):
    return sorted((l.account.code, l.debit_cents, l.credit_cents, l.vat_code, l.vat_base_cents)
                  for l in entry.lines if l.vat_code)


# ------------------------------------------------------------------ régime et codes

@pytest.mark.parametrize("vat, country, regime", [
    ("FR32123456789", None, "fr"), ("IE6388047V", None, "eu"), ("EL123456789", None, "eu"),
    (None, "Allemagne", "eu"), (None, "États-Unis", "world"), (None, "", "fr"), ("CHE123", "Suisse", "world"),
])
def test_guess_regime(vat, country, regime):
    assert vat_codes.guess_regime(vat, country) == regime


def test_code_choice():
    assert vat_codes.sale_tax_code(2000) == "V20" and vat_codes.sale_tax_code(550) == "V55"
    assert vat_codes.sale_tax_code(850) is None
    assert vat_codes.purchase_code("fr", "services", 1000) == "D10"
    assert vat_codes.purchase_code("eu", "goods", 0) == "AL_B"
    assert vat_codes.purchase_code("eu", "services", 0) == "AL_S"
    assert vat_codes.purchase_code("world", "services", 0) == "AL_S"
    # Biens importés hors UE : TVA à l'importation autoliquidée (A4, I1–I5 selon le taux), due en 4453.
    assert vat_codes.purchase_code("world", "goods", 2000) == "AL_I"
    assert vat_codes.purchase_code("world", "goods", 550) == "AL_I55"
    assert vat_codes.due_account_code("AL_I10") == "4453" and vat_codes.due_account_code("AL_S") == "4452"
    # Fournisseur non établi, TVA due par l'acheteur (art. 283-1) : ligne B4.
    assert vat_codes.purchase_code("fr_rc", "goods", 2000) == "AL_FR"
    assert "fr_rc" in vat_codes.regime_labels() and "fr_rc" not in vat_codes.regime_labels(sales=True)
    assert all(spec["on"] in ("tax", "base") for spec in vat_codes.codes().values())


# ------------------------------------------------------------------ achats

def test_reverse_charge_purchase(books):  # noqa: F811
    books["fy"].vat_liable = True
    supplier = Entity(name="Hetzner", entity_type="FOURNISSEUR", vat_number="DE812871812")
    db.session.add(supplier)
    db.session.commit()
    assert supplier.vat_regime == "eu"  # proposé d'après le n° de TVA (création par une synchronisation)
    p = _purchase(books, entity=supplier, total=10000, lines=[
        PurchaseLine(position=0, account=books["6061"], untaxed_cents=10000, vat_rate_bp=0, vat_cents=0,
                     total_cents=10000)])
    assert purchase_posting.purchase_state(p).code == "ready"
    purchase_posting.post(p)
    lines = sorted((l.account.code, l.debit_cents, l.credit_cents) for l in p.journal_entry.lines)
    assert lines == [("401001", 0, 10000), ("4452", 0, 2000), ("44566", 2000, 0), ("6061", 10000, 0)]
    assert _coded(p.journal_entry) == [("4452", 0, 2000, "AL_S", 10000), ("44566", 2000, 0, "AL_S", 10000)]


def test_foreign_supplier_charging_vat_must_be_checked(books):  # noqa: F811
    books["fy"].vat_liable = True
    supplier = Entity(name="OVH Ireland", entity_type="FOURNISSEUR", vat_regime="eu")
    p = _purchase(books, entity=supplier)  # 100 € + 20 € de TVA
    assert any("régime TVA" in r for r in purchase_posting.purchase_state(p).reasons)
    p.vat_regime = "fr"  # la facture porte la TVA française : régime du document
    db.session.commit()
    assert purchase_posting.purchase_state(p).code == "ready"


def test_fixed_asset_vat_on_44562(books):  # noqa: F811
    books["fy"].vat_liable = True
    computer = Account(code="2183", label="Matériel informatique", account_type="ASSET")
    db.session.add_all([computer, Account(code="44562", label="TVA sur immobilisations", account_type="TIERS")])
    p = _purchase(books, lines=[
        PurchaseLine(position=0, account=computer, untaxed_cents=100000, vat_rate_bp=2000, vat_cents=20000,
                     total_cents=120000)], total=120000)
    purchase_posting.post(p)
    assert _coded(p.journal_entry) == [("44562", 20000, 0, "D20", 100000)]


def test_not_liable_has_no_code(books):  # noqa: F811
    purchase_posting.post(_purchase(books))
    assert not [l for l in JournalEntry.query.one().lines if l.vat_code]


# ------------------------------------------------------------------ ventes

def _foreign_client(name, regime, vat=None):
    entity = Entity(name=name, entity_type="CLIENT", address_line1="1 Main St", postal_code="10001", city="Berlin",
                    country="Allemagne", vat_number=vat, vat_regime=regime)
    db.session.add(entity)
    db.session.commit()
    return entity


def test_sale_to_an_eu_business_without_french_vat(admin):  # noqa: F811
    client = _foreign_client("Agri GmbH", "eu", "DE812871812")
    item = admin.post(API, json={"entity_id": client.id, "issue_date": TODAY.isoformat(),
                                 "lines": [{"label": "Abonnement", "unit_price": "100", "vat_rate": "20"}]}).get_json()["item"]
    assert item["tax_cents"] == 0 and item["vat_regime"] == "eu"
    assert item["vat_exemptions"] == ["Autoliquidation — article 283-2 du CGI : TVA due par le preneur."]
    assert admin.post(f"{API}/{item['id']}/issue").status_code == 200
    sale = db.session.get(Sale, item["id"])
    assert _coded(sale.journal_entry) == [("706", 0, 10000, "V_UE_S", None)]
    assert "283-2" in sale_documents.render_html(sale)
    xml = sale_documents.einvoice_document(sale)
    assert xml.lines[0].exemption == ("AE", "VATEX-EU-AE", "Autoliquidation")


def test_eu_consumer_pays_french_vat(admin):  # noqa: F811
    client = _foreign_client("Hans", "eu")  # sans n° de TVA : particulier
    item = admin.post(API, json={"entity_id": client.id, "issue_date": TODAY.isoformat(),
                                 "lines": [{"label": "Abonnement", "unit_price": "100", "vat_rate": "20"}]}).get_json()["item"]
    assert item["tax_cents"] == 2000 and item["vat_exemptions"] == []


def test_export_of_goods(admin):  # noqa: F811
    client = _foreign_client("Farm Inc", "world")
    item = admin.post(API, json={"entity_id": client.id, "issue_date": TODAY.isoformat(), "lines": [
        {"label": "Capteur", "unit_price": "50", "vat_rate": "20", "nature": "goods"}]}).get_json()["item"]
    admin.post(f"{API}/{item['id']}/issue")
    assert _coded(db.session.get(Sale, item["id"]).journal_entry) == [("706", 0, 5000, "V_EXP", None)]


def test_french_sale_on_receipts_declared_when_paid(admin):  # noqa: F811
    inv = _invoice(admin)  # 1 000 € HT, 20 %, prestation : TVA à l'encaissement
    sale = db.session.get(Sale, inv["id"])
    assert _coded(sale.journal_entry) == [("44574", 0, 20000, "V20", 100000)]
    bank = BankAccount.query.filter_by(kind="bank").one()
    admin.post(f"{API}/{inv['id']}/payments", json={"amount": "450", "paid_on": TODAY.isoformat(),
                                                   "bank_account_id": bank.id, "method": "check"})
    admin.post(f"{API}/{inv['id']}/payments", json={"amount": "750", "paid_on": TODAY.isoformat(),
                                                   "bank_account_id": bank.id, "method": "check"})
    released = [line for p in SalePayment.query.order_by(SalePayment.id) for line in p.journal_entry.lines
                if line.vat_code and line.account.code == "44571"]
    assert [(l.credit_cents, l.vat_code, l.vat_base_cents) for l in released] == [(7500, "V20", 37500),
                                                                                 (12500, "V20", 62500)]
    assert sum(l.vat_base_cents for l in released) == 100000


def test_reversal_keeps_the_codes(admin):  # noqa: F811
    inv = _invoice(admin)
    bank = BankAccount.query.filter_by(kind="bank").one()
    admin.post(f"{API}/{inv['id']}/payments", json={"amount": "1200", "paid_on": TODAY.isoformat(),
                                                   "bank_account_id": bank.id, "method": "check"})
    entry = SalePayment.query.one().journal_entry
    reversal = reverse(entry)
    assert sorted((l.account.code, l.vat_code, l.vat_base_cents, l.debit_cents) for l in reversal.lines if l.vat_code) \
        == [("44571", "V20", 100000, 20000), ("44574", "V20", 100000, 0)]


# ------------------------------------------------------------------ tiers et saisie manuelle

def test_tiers_regime(admin):  # noqa: F811
    created = admin.post("/api/v1/tiers", json={"name": "Google Ireland", "vat_number": "IE6388047V"}).get_json()["item"]
    assert created["vat_regime"] == "eu"
    chosen = admin.post("/api/v1/tiers", json={"name": "Stripe", "vat_number": "IE3206488LH",
                                               "vat_regime": "fr"}).get_json()["item"]
    assert chosen["vat_regime"] == "fr"
    assert admin.post("/api/v1/tiers", json={"name": "X", "vat_regime": "mars"}).status_code == 422
    updated = admin.patch(f"/api/v1/tiers/{created['id']}", json={"name": "Google Ireland", "vat_regime": "world"})
    assert updated.get_json()["item"]["vat_regime"] == "world"


def _manual(admin, vat_line):
    accounts = {a.code: a for a in Account.query.all()}
    db.session.add(Account(code="44566", label="TVA déductible", account_type="TIERS"))
    db.session.add(Account(code="6226", label="Honoraires", account_type="EXPENSE"))
    db.session.commit()
    from app.models import FiscalYear, Journal
    payload = {"fiscal_year_id": FiscalYear.query.first().id, "journal_id": Journal.query.first().id,
               "entry_date": TODAY.isoformat(), "description": "Honoraires", "lines": [
                   {"account_id": Account.query.filter_by(code="6226").one().id, "debit_cents": 10000},
                   {"account_id": Account.query.filter_by(code="44566").one().id, "debit_cents": 2000, **vat_line},
                   {"account_id": accounts["512"].id, "credit_cents": 12000}]}
    return admin.post("/api/v1/entries", json=payload)


def test_manual_entry_with_a_code(admin):  # noqa: F811
    resp = _manual(admin, {"vat_code": "D20", "vat_base_cents": 10000})
    assert resp.status_code in (200, 201), resp.get_json()
    line = next(l for l in JournalEntry.query.order_by(JournalEntry.id.desc()).first().lines if l.vat_code)
    assert (line.vat_code, line.vat_base_cents) == ("D20", 10000)

    resp = admin.put(f"/api/v1/entries/{line.entry_id}/lines/{line.id}/vat", json={"vat_code": "D10",
                                                                                   "vat_base_cents": 20000})
    assert resp.status_code == 200, resp.get_json()
    assert (line.vat_code, line.vat_base_cents) == ("D10", 20000)
    assert admin.put(f"/api/v1/entries/{line.entry_id}/lines/{line.id}/vat", json={"vat_code": "X"}).status_code == 422


def test_manual_entry_unknown_code_refused(admin):  # noqa: F811
    resp = _manual(admin, {"vat_code": "ZZ", "vat_base_cents": 10000})
    assert resp.status_code == 422
    assert "lines[1].vat_code" in resp.get_json()["error"]["fields"]


def test_validated_line_code_is_locked(admin):  # noqa: F811
    inv = _invoice(admin)  # écriture de vente validée d'office
    line = next(l for l in db.session.get(Sale, inv["id"]).journal_entry.lines if l.vat_code)
    assert admin.put(f"/api/v1/entries/{line.entry_id}/lines/{line.id}/vat", json={"vat_code": ""}).status_code == 409


def test_product_nature_drives_goods_autoliquidation(books):  # noqa: F811
    books["fy"].vat_liable = True
    supplier = Entity(name="Bauer AG", entity_type="FOURNISSEUR", vat_regime="eu")
    sensor = Product(name="Capteur", kind="purchase", nature="goods")
    db.session.add(sensor)
    p = _purchase(books, entity=supplier, total=5000, lines=[
        PurchaseLine(position=0, account=books["6061"], product=sensor, untaxed_cents=5000, vat_rate_bp=0,
                     vat_cents=0, total_cents=5000)])
    purchase_posting.post(p)
    assert {l.vat_code for l in p.journal_entry.lines if l.vat_code} == {"AL_B"}


def test_imported_goods_self_assess_import_vat_on_4453(books):  # noqa: F811
    """Bien acheté hors UE : TVA à l'importation autoliquidée (AL_I), due en 4453 créé au besoin ; un service
    du même fournisseur reste en A3 (AL_S, 4452)."""
    books["fy"].vat_liable = True
    supplier = Entity(name="Acme Inc", entity_type="FOURNISSEUR", vat_regime="world")
    sensor = Product(name="Capteur US", kind="purchase", nature="goods")
    db.session.add(sensor)
    p = _purchase(books, entity=supplier, total=15000, lines=[
        PurchaseLine(position=0, account=books["6061"], product=sensor, untaxed_cents=10000, vat_rate_bp=0,
                     vat_cents=0, total_cents=10000),
        PurchaseLine(position=1, account=books["6061"], untaxed_cents=5000, vat_rate_bp=0, vat_cents=0,
                     total_cents=5000)])
    purchase_posting.post(p)
    assert _coded(p.journal_entry) == [("4452", 0, 1000, "AL_S", 5000), ("4453", 0, 2000, "AL_I", 10000),
                                       ("44566", 1000, 0, "AL_S", 5000), ("44566", 2000, 0, "AL_I", 10000)]


def test_article_283_1_regime_on_a_purchase(books):  # noqa: F811
    books["fy"].vat_liable = True
    supplier = Entity(name="Installateur NL", entity_type="FOURNISSEUR", vat_regime="fr_rc")
    p = _purchase(books, entity=supplier, total=10000, lines=[
        PurchaseLine(position=0, account=books["6061"], untaxed_cents=10000, vat_rate_bp=0, vat_cents=0,
                     total_cents=10000)])
    purchase_posting.post(p)
    assert {l.vat_code for l in p.journal_entry.lines if l.vat_code} == {"AL_FR"}
