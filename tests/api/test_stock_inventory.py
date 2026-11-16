"""Lot AG4.a : inventaire de clôture — lignes de stock et méthodes (design_inventaire_agricole.md §§ 3 et 4, AGD21)."""
import io
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, FiscalYear, Journal, StockLine, TaxOption
from app.models.journal_entry import SOURCE_OPENING
from app.services import stock_inventory as inv
from app.services.ledger import post_entry
from test_agri_fixtures import _agri_instance


@pytest.fixture()
def farm(app, login_as):
    client = login_as(role="admin")
    _agri_instance()
    previous = FiscalYear(label="2025", start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    an = Journal(code="AN", label="À-nouveaux")
    db.session.add_all([previous, fy, an])
    db.session.commit()
    acc = {c: Account.query.filter_by(code=c).one().id for c in ("31111", "110")}
    post_entry(fy.id, an.id, date(2026, 1, 1), "À-nouveaux", [
        {"account_id": acc["31111"], "label": "Engrais", "debit_cents": 669266, "credit_cents": 0},
        {"account_id": acc["110"], "label": "Report", "debit_cents": 0, "credit_cents": 669266}], source=SOURCE_OPENING)
    return {"client": client, "fy": fy, "previous": previous, "url": f"/api/v1/fiscal-years/{fy.id}/stock"}


def _line(farm, status=201, **data):
    resp = farm["client"].post(f"{farm['url']}/lines", json=data)
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()


def _item(body, label):
    return next(i for i in body["item"]["items"] if i["label"] == label)


def test_categories_and_variations():
    assert inv.classify("31111")[1]["variation"] == "6031"
    assert inv.classify("3113")[0]["key"] == "animals_short" and inv.classify("3113")[1]["variation"] == "713552"
    assert inv.classify("31151")[1]["variation"] == "713312" and inv.classify("35511")[1]["variation"] == "713554"
    assert inv.classify("3112")[1]["purchase"] == "60117"                     # animaux achetés (AGD21, Q-S2)
    assert inv.classify("401") is None


def test_actual_cost_line_and_opening(farm):
    body = _line(farm, account_code="31111", label="Ammonitrate", quantity="10.5", unit="t", method="actual",
                 unit_value_cents=25000)
    item = _item(body, "Ammonitrate")
    assert item["value_cents"] == 262500 and item["variation_account"]["code"] == "6031" and item["warnings"] == []
    assert item["purchase_account"] == "60111"
    view = body["item"]
    assert view["totals"]["supplies"]["value_cents"] == 262500 and view["total_cents"] == 262500
    assert view["opening"] == [{"code": "31111", "label": "Engrais et amendements", "balance_cents": 669266, "grouping": False, "counted": True}]
    assert body["meta"]["categories"][0]["key"] == "supplies"


def test_retail_refused_and_discounted(farm):
    for code in ("31111", "31151"):
        resp = _line(farm, 422, account_code=code, label="x", quantity="1", method="retail", market_price_cents=100)
        assert "prix de détail est interdit" in resp["error"]["message"]
    body = _line(farm, account_code="35511", label="Blé", quantity="100", unit="t", method="retail",
                 market_price_cents=20000, price_source="cours du jour")
    assert _item(body, "Blé")["value_cents"] is None and any("Décote" in w for w in _item(body, "Blé")["warnings"])
    assert farm["client"].put(f"{farm['url']}/settings", json={"discounts": {"supplies": 1000}}).status_code == 422
    body = farm["client"].put(f"{farm['url']}/settings", json={"discounts": {"finished": 1500}}).get_json()
    assert _item(body, "Blé")["unit_value_cents"] == 17000 and _item(body, "Blé")["value_cents"] == 1700000


def test_price_reference_warning(farm):
    body = _line(farm, account_code="3113", label="Porcs charcutiers", quantity="1000", unit="kg", method="retail",
                 market_price_cents=17000, price_reference="pig_carcass")
    assert any("loin de l'ordre de grandeur" in w for w in _item(body, "Porcs charcutiers")["warnings"])
    line = StockLine.query.one()
    body = farm["client"].put(f"{farm['url']}/lines/{line.id}", json={"market_price_cents": 180}).get_json()
    assert not any("ordre de grandeur" in w for w in _item(body, "Porcs charcutiers")["warnings"])


def test_flat_method_as_accounting_value(farm):
    assert _line(farm, 422, account_code="31112", label="Semences", quantity="1", method="flat",
                 market_price_cents=100)["error"]["fields"]["method"]
    body = _line(farm, account_code="35511", label="Blé", quantity="100", unit="t", method="flat", market_price_cents=20000)
    assert any("Option de la méthode forfaitaire" in w for w in _item(body, "Blé")["warnings"])
    assert _item(body, "Blé")["value_cents"] == 1600000                     # 100 t × 200 € × (1 − 20 %)
    db.session.add(TaxOption(code="flat_stock_method", start_date=date(2024, 1, 1)))
    db.session.commit()
    body = _line(farm, account_code="3112", label="Vaches", quantity="10", unit="head", method="flat",
                 market_price_cents=150000, flat_rate="cattle_wine")
    assert _item(body, "Vaches")["value_cents"] == 1050000 and body["item"]["flat_allowed"] is True
    assert not any("Option" in w for w in _item(body, "Blé")["warnings"])


def test_standard_cost_and_depreciation(farm):
    client = farm["client"]
    std = client.post("/api/v1/stock-standards", json={"label": "Porcelet 25 kg", "unit": "head", "value_cents": 6500,
                                                         "year": 2026, "source": "barème de l'exploitation"})
    assert std.status_code == 201
    sid = std.get_json()["item"]["id"]
    assert client.post("/api/v1/stock-standards", json={"label": "Porcelet 25 kg", "unit": "head", "value_cents": 1,
                                                         "year": 2026}).status_code == 422
    body = _line(farm, account_code="3113", label="Porcelets", quantity="135", unit="head", method="standard", standard_id=sid)
    assert _item(body, "Porcelets")["value_cents"] == 877500
    line = StockLine.query.one()
    url = f"{farm['url']}/lines/{line.id}"
    assert client.put(url, json={"depreciation_cents": 10000}).status_code == 422          # motif
    assert client.put(url, json={"depreciation_cents": 900000, "depreciation_reason": "maladie"}).status_code == 422
    body = client.put(url, json={"unit": "kg", "depreciation_cents": 10000, "depreciation_reason": "maladie"}).get_json()
    assert any("Unité du barème" in w for w in _item(body, "Porcelets")["warnings"])
    assert body["item"]["totals"]["animals_short"]["depreciation_cents"] == 10000


def test_copy_previous_and_import(farm):
    client, previous = farm["client"], farm["previous"]
    db.session.add(StockLine(fiscal_year_id=previous.id, category="supplies", label="Engrais", quantity=12, unit="t",
                             method="actual", unit_value_cents=30000,
                             account_id=Account.query.filter_by(code="31111").one().id,
                             variation_account_id=Account.query.filter_by(code="6031").one().id))
    db.session.commit()
    body = client.post(f"{farm['url']}/copy-previous").get_json()
    item = _item(body, "Engrais")
    assert item["quantity"] == "0.000" and item["value_cents"] == 0 and item["unit_value_cents"] == 30000
    assert client.post(f"{farm['url']}/copy-previous").status_code == 409
    csv = "Compte;Libellé;Quantité;Unité;Méthode;Valeur unitaire\n31114;Aliment porc;12,5;t;coût réel;310,50\n401;Erreur;1;t;réel;1\n"
    resp = client.post(f"{farm['url']}/import", data={"file": (io.BytesIO(csv.encode()), "stock.csv")},
                       content_type="multipart/form-data")
    assert resp.status_code == 422 and "Ligne 3" in resp.get_json()["error"]["message"]
    assert StockLine.query.filter_by(fiscal_year_id=farm["fy"].id).count() == 1      # tout ou rien
    csv = "Compte;Libellé;Quantité;Unité;Méthode;Valeur unitaire\n31114;Aliment porc;12,5;t;coût réel;310,50\n"
    body = client.post(f"{farm['url']}/import", data={"file": (io.BytesIO(csv.encode()), "stock.csv")},
                       content_type="multipart/form-data").get_json()
    assert _item(body, "Aliment porc")["value_cents"] == 388125


def test_count_files(farm, app, tmp_path):
    client = farm["client"]
    pdf = b"%PDF-1.4\n%feuille de comptage\n"
    resp = client.post(f"{farm['url']}/files", data={"file": (io.BytesIO(pdf), "comptage.pdf"), "note": "hangar"},
                       content_type="multipart/form-data")
    assert resp.status_code == 201, resp.get_json()
    (row,) = resp.get_json()["files"]
    assert row["name"] == "comptage.pdf" and row["note"] == "hangar"
    assert client.get(f"{farm['url']}/files/{row['id']}").data == pdf
    assert client.delete(f"{farm['url']}/files/{row['id']}").get_json()["files"] == []
    bad = client.post(f"{farm['url']}/files", data={"file": (io.BytesIO(b"texte"), "x.txt")}, content_type="multipart/form-data")
    assert bad.status_code == 422


def test_closed_simple_and_accountant(farm, app, login_as):
    fy = farm["fy"]
    fy.status = "closed"
    db.session.commit()
    assert _line(farm, 409, account_code="31111", label="x", quantity="1")["error"]["code"] == "conflict"
    assert farm["client"].get(farm["url"]).get_json()["item"]["editable"] is False


def test_simple_mode_and_accountant(app, login_as):
    client = login_as(role="accountant")
    _agri_instance()
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    db.session.add(fy)
    db.session.commit()
    assert client.get(f"/api/v1/fiscal-years/{fy.id}/stock").status_code == 200
    assert client.post(f"/api/v1/fiscal-years/{fy.id}/stock/lines", json={}).status_code == 403
    from app.models import Instance
    Instance.query.one().bookkeeping = "simple"
    db.session.commit()
    assert client.get(f"/api/v1/fiscal-years/{fy.id}/stock").status_code == 404


def test_depreciation_suggestion_cg5b(farm):
    """Lot CG5.b (BOI-BA-BASE-20-20-20-10 § 90, § 320) : cours du jour inférieur au prix de revient → provision proposée."""
    from app.services import closing
    body = _line(farm, account_code="35511", label="Blé", quantity="10", unit="t", method="actual",
                 unit_value_cents=18000, market_price_cents=16000)
    item = _item(body, "Blé")
    assert item["depreciation_suggested_cents"] == 20000                           # 10 t × (180 − 160) €
    assert not any("provision" in w for w in item["warnings"])                     # pas une ligne « à compléter »
    checks = {c.key: c for c in closing._agri_checks(farm["fy"])}
    assert checks["stock_depreciation_missing"].count == 1 and checks["stock_depreciation_missing"].severity == "info"
    line = StockLine.query.filter_by(label="Blé").one()
    body = farm["client"].put(f"{farm['url']}/lines/{line.id}", json={
        "depreciation_cents": 20000, "depreciation_reason": inv.DEPRECIATION_REASON}).get_json()
    assert _item(body, "Blé")["depreciation_suggested_cents"] is None
    assert "stock_depreciation_missing" not in {c.key for c in closing._agri_checks(farm["fy"])}
    high = _line(farm, account_code="35511", label="Orge", quantity="10", unit="t", method="actual",
                 unit_value_cents=15000, market_price_cents=17000)
    assert _item(high, "Orge")["depreciation_suggested_cents"] is None             # cours au-dessus du prix de revient


def test_copy_opening_for_a_first_inventory(farm):
    """Essai de l'interface (09/11/2026) : premier inventaire dans Lyvre, une ligne par stock initial, rien en valeur."""
    client, fy = farm["client"], farm["fy"]
    acc = {c: Account.query.filter_by(code=c).one().id for c in ("31", "110")}
    post_entry(fy.id, Journal.query.filter_by(code="AN").one().id, date(2026, 1, 1), "À-nouveaux", [
        {"account_id": acc["31"], "label": "Divers", "debit_cents": 123432, "credit_cents": 0},
        {"account_id": acc["110"], "label": "Report", "debit_cents": 0, "credit_cents": 123432}], source=SOURCE_OPENING)
    view = client.get(farm["url"]).get_json()["item"]
    assert {o["code"]: o["grouping"] for o in view["opening"]} == {"31": True, "31111": False}
    body = client.post(f"{farm['url']}/copy-opening").get_json()
    lines = {i["account"]["code"]: i for i in body["item"]["items"]}
    assert set(lines) == {"31", "31111"}
    assert lines["31111"]["quantity"] == "0.000" and lines["31111"]["value_cents"] in (0, None)
    assert "stock initial 6 692,66 €" in lines["31111"]["notes"]
    assert client.post(f"{farm['url']}/copy-opening").status_code == 409
