"""API des écrans associatifs (phase G) : Odoo (commandes, factures clients, import par lots),
Visibilité & Impact, rapport d'activité (textes, tonnages, photos, logo, archives) ;
pages servies par la SPA, fichiers par Flask."""
import io
from datetime import date, datetime

import pytest

from app.extensions import db
from app.models import (
    CustomerInvoice, CustomerInvoiceLine, EcoDeclaration, FiscalYear, ImpactFactor, MetricSnapshot, OdooImportLine,
    Order, OrderLine, OrderPayment, ReportArchive, ReportAsset, ReportContent,
)
from app.services import external_config

ODOO = {"url": "https://erp.example.org", "db": "prod", "username": "a@b.fr", "api_key": "k-123456"}


def _error(resp, status):
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()["error"]


@pytest.fixture()
def client(login_as):
    return login_as()


@pytest.fixture()
def admin(login_as):
    return login_as(is_admin=True)


def test_spa_shell_serves_asso_pages(client):
    for url in ("/orders/", "/orders/1", "/customer-invoices/", "/customer-invoices/1", "/imports/odoo",
                "/imports/odoo/batch/lot-1", "/impact/", "/impact/report", "/impact/factors", "/impact/manual",
                "/rapport-activite/", "/rapport-activite/edit", "/rapport-activite/eco",
                "/rapport-activite/photos", "/rapport-activite/archives"):
        assert 'id="root"' in client.get(url).get_data(as_text=True), url


# ------------------------------------------------------------------ Odoo


def _orders():
    o = Order(odoo_id=10, name="POS/0010", session_name="S1", partner_name="Alice", state="done",
              date_order=datetime(2026, 6, 10, 14, 30), amount_total_cents=1200, amount_tax_cents=200,
              amount_paid_cents=1500, amount_return_cents=300)
    db.session.add_all([o, Order(odoo_id=11, state="cancel", date_order=datetime(2026, 5, 2), amount_total_cents=99)])
    db.session.flush()
    db.session.add_all([
        OrderLine(odoo_id=1, order_id=o.id, full_product_name="Chaise", qty=2, price_unit_cents=600,
                  price_subtotal_cents=1000, price_subtotal_incl_cents=1200),
        OrderPayment(odoo_id=1, order_id=o.id, payment_method_name="Espèces", amount_cents=1500,
                     payment_date=datetime(2026, 6, 10, 14, 31)),
    ])
    db.session.commit()
    return o


def test_orders_list_detail_and_month(client):
    o = _orders()
    body = client.get("/api/v1/orders").get_json()
    assert [r["reference"] for r in body["items"]] == ["POS/0010", "11"]
    row = body["items"][0]
    assert row["lines"] == 1 and row["payments"] == 1 and row["state_label"]
    assert [r["reference"] for r in client.get("/api/v1/orders?month=2026-05").get_json()["items"]] == ["11"]
    detail = client.get(f"/api/v1/orders/{o.id}").get_json()
    assert detail["item"]["return_cents"] == 300 and detail["lines"][0]["product"] == "Chaise"
    assert detail["payments"][0]["method"] == "Espèces"
    _error(client.get("/api/v1/orders/999"), 404)


def test_orders_sync(client, monkeypatch):
    external_config.set_many("odoo", ODOO)
    monkeypatch.setattr("app.api.odoo.sync_pos_orders", lambda: {
        "orders_imported": 2, "orders_updated": 1, "lines_total": 5, "payments_total": 3})
    body = client.post("/api/v1/orders/sync").get_json()
    assert "2 nouvelle(s), 1 mise(s) à jour" in body["notices"][0]["message"]

    def boom():
        raise RuntimeError("délai dépassé")
    monkeypatch.setattr("app.api.odoo.sync_pos_orders", boom)
    assert "délai dépassé" in _error(client.post("/api/v1/orders/sync"), 502)["message"]


def _invoice():
    inv = CustomerInvoice(odoo_id=7, name="FAC/2026/0007", ref="R7", partner_name="Mairie", partner_email="m@ex.org",
                          state="posted", payment_state="not_paid", invoice_date=date(2026, 6, 3),
                          amount_untaxed_cents=1000, amount_tax_cents=200, amount_total_cents=1200,
                          amount_residual_cents=1200, narration="<p>Merci <b>beaucoup</b><script>x()</script></p>")
    db.session.add(inv)
    db.session.flush()
    db.session.add(CustomerInvoiceLine(odoo_id=1, invoice_id=inv.id, product_name="Atelier", qty=1,
                                       price_unit_cents=1000, price_subtotal_cents=1000, price_total_cents=1200))
    db.session.commit()
    return inv


def test_customer_invoices_filters_and_detail(client):
    inv = _invoice()
    body = client.get("/api/v1/customer-invoices").get_json()
    assert [r["number"] for r in body["items"]] == ["FAC/2026/0007"] and body["meta"]["states"]
    for qs in ("q=mairie", "state=posted", "payment_state=not_paid", "month=2026-06"):
        assert len(client.get(f"/api/v1/customer-invoices?{qs}").get_json()["items"]) == 1, qs
    for qs in ("q=zzz", "state=draft", "payment_state=paid", "month=2026-05"):
        assert client.get(f"/api/v1/customer-invoices?{qs}").get_json()["items"] == [], qs
    detail = client.get(f"/api/v1/customer-invoices/{inv.id}").get_json()
    assert detail["lines"][0]["product"] == "Atelier"
    assert "<" not in detail["item"]["narration"] and "Merci beaucoup" in detail["item"]["narration"]


def test_customer_invoices_sync_unconfigured(client):
    assert "Odoo" in _error(client.post("/api/v1/customer-invoices/sync"), 409)["message"]


CSV = ("name,invoice_date,partner_id/name,product_id/name,price_subtotal,price_total,account_id/code\n"
       "FAC/1,2026-06-01,Mairie,Atelier,100.00,120.00,706000\n")


def test_odoo_csv_import_and_batches(client):
    resp = client.post("/api/v1/imports/odoo", data={"batch_name": "lot-1", "csv_file": (io.BytesIO(CSV.encode()), "f.csv")},
                       content_type="multipart/form-data")
    body = resp.get_json()
    assert body["result"]["imported"] == 1 and body["result"]["url"] == "/imports/odoo/batch/lot-1"
    assert body["result"]["preview"][0]["invoice_number"] == "FAC/1"
    assert client.get("/api/v1/imports/odoo").get_json()["items"] == [
        {"name": "lot-1", "lines": 1, "url": "/imports/odoo/batch/lot-1"}]
    lines = client.get("/api/v1/imports/odoo/batches/lot-1").get_json()["items"]
    assert lines[0]["total_cents"] == 12000 and lines[0]["entry_url"] is None
    assert OdooImportLine.query.count() == 1
    _error(client.post("/api/v1/imports/odoo", data={}, content_type="multipart/form-data"), 422)


# ------------------------------------------------------------------ Visibilité & Impact


def test_impact_dashboard_and_export_link(client):
    body = client.get("/api/v1/impact?gran=month&month=2026-06").get_json()
    assert body["period"]["gran"] == "month" and body["current"]["month"] == "2026-06"
    assert body["highlights"] and body["sections"][0]["kpis"]
    assert body["meta"]["export_url"].startswith("/impact/export.xlsx?")
    resp = client.get(body["meta"]["export_url"])
    assert resp.status_code == 200 and resp.data[:2] == b"PK"


def test_impact_sync_month(client, monkeypatch):
    monkeypatch.setattr("app.services.metrics_sync.sync_metrics",
                        lambda y, m: {"ga4": {"imported": 3, "errors": []}, "facebook": {"imported": 0, "errors": ["x"]}})
    body = client.post("/api/v1/impact/sync", json={"scope": "month", "month": "2026-06"}).get_json()
    assert body["notices"][0]["message"] == "Synchronisation (2026-06) : 3 métrique(s) importée(s)."
    assert body["notices"][0]["level"] == "warning" and body["notices"][1]["message"] == "x"


def test_impact_manual_roundtrip_and_validation(client):
    resp = client.put("/api/v1/impact/manual", json={"month": "2026-06", "values": {"vinted.revenue_cents": "12,5"}})
    assert resp.status_code == 200
    fields = {f["key"]: f for f in client.get("/api/v1/impact/manual?month=2026-06").get_json()["fields"]}
    assert fields["vinted.revenue_cents"]["value"] == 12.5 and fields["vinted.revenue_cents"]["in_euros"]
    err = _error(client.put("/api/v1/impact/manual", json={"month": "2026-06", "values": {
        "vinted.items_sold": "abc", "vinted.revenue_cents": "99"}}), 422)
    assert "vinted.items_sold" in err["fields"]
    # Rien n'est écrit quand une valeur est invalide.
    assert float(MetricSnapshot.query.filter_by(metric_key="vinted.revenue_cents").one().value) == 1250


def test_admin_only_endpoints(client, fy):
    for method, url in (("get", "/api/v1/impact/factors"), ("put", "/api/v1/impact/factors"),
                        ("get", "/api/v1/activity-report/texts"), ("put", "/api/v1/activity-report/texts"),
                        ("get", "/api/v1/activity-report/eco"), ("get", "/api/v1/activity-report/photos"),
                        ("post", "/api/v1/activity-report/archives"), ("delete", "/api/v1/activity-report/archives/1"),
                        ("delete", "/api/v1/activity-report/logo")):
        _error(getattr(client, method)(url, json={}), 403)
    assert client.get("/api/v1/activity-report/archives").status_code == 200  # consultation ouverte


def test_impact_factors(admin):
    items = admin.get("/api/v1/impact/factors").get_json()["items"]
    first = items[0]
    resp = admin.put("/api/v1/impact/factors", json={"items": [{**first, "value": "1,5", "source_label": "ADEME"}]})
    assert resp.status_code == 200
    assert float(db.session.get(ImpactFactor, first["id"]).value) == 1.5
    err = _error(admin.put("/api/v1/impact/factors", json={"items": [{**first, "source_url": "javascript:alert(1)"}]}), 422)
    assert f"source_url_{first['id']}" in err["fields"]


# ------------------------------------------------------------------ rapport d'activité


@pytest.fixture()
def fy(app, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "instance_path", str(tmp_path))
    fy = FiscalYear(label="2025", start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
    db.session.add(fy)
    db.session.commit()
    return fy


def test_report_context_and_preview(client, fy):
    body = client.get("/api/v1/activity-report").get_json()
    assert body["fiscal_year"] == {"id": fy.id, "label": "2025"} and body["prorata"] is False
    assert body["links"]["pdf"] == f"/rapport-activite/pdf?fy_id={fy.id}&prorata=0"
    preview = client.get(body["links"]["preview"])
    assert preview.status_code == 200 and "script-src 'none'" in preview.headers["Content-Security-Policy"]
    assert "<html" in preview.get_data(as_text=True).lower()
    assert client.get(f"/api/v1/activity-report?fy_id={fy.id}&prorata=1").get_json()["prorata"] is True


def test_report_without_fiscal_year(client):
    assert _error(client.get("/api/v1/activity-report"), 409)["code"] == "no_fiscal_year"


def test_report_texts(admin, fy):
    blocks = admin.get("/api/v1/activity-report/texts").get_json()["blocks"]
    key = blocks[0]["key"]
    admin.put("/api/v1/activity-report/texts", json={"fy_id": fy.id, "blocks": [
        {"key": key, "title": "Édito", "body": "<p>Bonjour</p>"}]})
    row = ReportContent.query.one()
    assert (row.block_key, row.title, row.body_html) == (key, "Édito", "<p>Bonjour</p>")
    admin.put("/api/v1/activity-report/texts", json={"fy_id": fy.id, "blocks": [{"key": key, "title": "", "body": " "}]})
    assert ReportContent.query.count() == 0


def test_report_eco_import_and_edit(admin, fy):
    from test_activity_report import _bilan_xlsx
    resp = admin.post("/api/v1/activity-report/eco/import", data={"file": (_bilan_xlsx(), "bilan.xlsx")},
                      content_type="multipart/form-data")
    rows = resp.get_json()["items"]
    assert len(rows) == EcoDeclaration.query.count() > 0
    first, second = rows[0], rows[1]
    body = admin.put("/api/v1/activity-report/eco", json={"rows": [
        {**first, "entrant_t": 3.5, "financing_cents": 1234}, {"id": second["id"], "delete": True}]}).get_json()
    edited = next(r for r in body["items"] if r["id"] == first["id"])
    assert edited["entrant_t"] == 3.5 and edited["financing_cents"] == 1234 and edited["source"] == "manual"
    assert all(r["id"] != second["id"] for r in body["items"])
    _error(admin.put("/api/v1/activity-report/eco", json={"rows": [{**first, "sortant_t": -1}]}), 422)
    _error(admin.post("/api/v1/activity-report/eco/import", data={"file": (io.BytesIO(b"x"), "bilan.csv")},
                      content_type="multipart/form-data"), 422)


PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def test_report_photos_and_logo(admin, fy):
    upload = lambda name, slot="cover": admin.post("/api/v1/activity-report/photos", data={
        "fy_id": str(fy.id), "slot": slot, "file": (io.BytesIO(PNG), name)}, content_type="multipart/form-data")
    body = upload("couv.png").get_json()
    cover = body["slots"][0]
    assert cover["slot"] == "cover" and cover["photo"]["url"].startswith("/rapport-activite/photo/")
    assert admin.get(cover["photo"]["url"]).data == PNG
    _error(upload("page.html"), 422)
    _error(upload("couv.png", slot="ailleurs"), 422)
    admin.patch(f"/api/v1/activity-report/photos/{cover['photo']['id']}", json={"caption": "Atelier"})
    assert ReportAsset.query.one().caption == "Atelier"
    admin.delete(f"/api/v1/activity-report/photos/{cover['photo']['id']}")
    assert ReportAsset.query.count() == 0

    logo = admin.post("/api/v1/activity-report/logo", data={"file": (io.BytesIO(PNG), "logo.png")},
                      content_type="multipart/form-data").get_json()
    assert logo["logo_url"] == "/rapport-activite/logo-file"
    assert admin.delete("/api/v1/activity-report/logo").get_json()["logo_url"] is None


def test_report_archives(admin, fy):
    resp = admin.post("/api/v1/activity-report/archives", json={"fy_id": fy.id, "label": "AG", "prorata": True})
    assert resp.status_code == 201
    items = admin.get("/api/v1/activity-report/archives").get_json()["items"]
    assert items[0]["version"] == 1 and items[0]["label"] == "AG" and items[0]["prorata"] is True
    assert admin.get(items[0]["url"]).data[:4] == b"%PDF"
    admin.delete(f"/api/v1/activity-report/archives/{items[0]['id']}")
    assert ReportArchive.query.count() == 0


def test_missing_photo_file_is_404(admin, fy):
    db.session.add(ReportAsset(fiscal_year_id=fy.id, slot="cover", path="uploads/report/absent.jpg"))
    db.session.commit()
    assert admin.get(f"/rapport-activite/photo/{ReportAsset.query.one().id}").status_code == 404
