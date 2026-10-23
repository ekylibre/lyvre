"""API des tiers (phase C) : tiers, adhérents, relances, temps de travaux, recherche."""
import io
from datetime import date, datetime, timedelta

import pytest

from app.extensions import db
from app.models import (
    Account, BankAccount, BankTransaction, EmailTemplate, Entity, FiscalYear, HelloAssoItem,
    HelloAssoOrder, Journal, JournalEntry, Product, Purchase, PurchaseLine, TaskType, WorkTime,
)
from app.services import external_config


def _error(resp, status):
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()["error"]


@pytest.fixture()
def client(login_as):
    return login_as()


@pytest.mark.parametrize("url", [
    "/entities/", "/entities/new", "/entities/3", "/entities/3/edit", "/entities/members",
    "/entities/members/reminders", "/entities/members/reminder-template",
    "/work-times/", "/work-times/new", "/work-times/4/edit", "/work-times/import",
])
def test_pages_served_by_spa(client, url):
    assert '<div id="root"></div>' in client.get(url).get_data(as_text=True)


# ------------------------------------------------------------------ tiers


def test_tiers_create_with_supplier_fields_and_validation(client):
    account = Account(code="6061", label="Fournitures", account_type="EXPENSE")
    product = Product(name="Électricité", kind="purchase", purchase_account=account)
    db.session.add_all([account, product])
    db.session.commit()
    meta = client.get("/api/v1/tiers").get_json()["meta"]
    assert {"value": str(product.id), "label": "Électricité"} in meta["products"]
    assert set(meta["integrations"]) == {"helloasso", "odoo", "smtp"}

    resp = client.post("/api/v1/tiers", json={
        "name": "EDF", "entity_type": "FOURNISSEUR", "default_product_id": str(product.id),
        "vat_number": "fr 03 552081317", "siret": "552 081 317 66522",
        "iban": "fr76 3000 4000 0312 3456 7890 143"})
    item = resp.get_json()["item"]
    assert resp.status_code == 201 and item["default_product"] == "Électricité"
    assert (item["vat_number"], item["siret"], item["iban"]) == (
        "FR03552081317", "55208131766522", "FR7630004000031234567890143")

    err = _error(client.patch(f"/api/v1/tiers/{item['id']}", json={
        "name": "EDF", "entity_type": "FOURNISSEUR", "siret": "552081317"}), 422)
    assert err["fields"] == {"siret": "Le SIRET doit comporter 14 chiffres."}
    assert db.session.get(Entity, item["id"]).siret == "55208131766522"
    assert "name" in _error(client.post("/api/v1/tiers", json={"name": "EDF"}), 422)["fields"]
    assert "entity_type" in _error(client.post("/api/v1/tiers", json={"name": "X", "entity_type": "FOO"}), 422)["fields"]

    upd = client.patch(f"/api/v1/tiers/{item['id']}", json={
        "name": "EDF", "entity_type": "FOURNISSEUR", "default_product_id": ""}).get_json()["item"]
    assert upd["default_product_id"] is None and upd["vat_number"] is None


def test_tiers_list_search_and_delete(client):
    acc = Account(code="512", label="Banque")
    db.session.add(acc)
    db.session.flush()
    ba = BankAccount(label="Courant", account_id=acc.id)
    edf = Entity(name="EDF", email="contact@edf.fr", entity_type="FOURNISSEUR")
    leroy = Entity(name="Leroy Merlin", email="pro@leroy.fr", entity_type="FOURNISSEUR")
    member = Entity(name="Adhérent", entity_type="ADHERENT")
    db.session.add_all([ba, edf, leroy, member])
    db.session.flush()
    db.session.add(BankTransaction(bank_account_id=ba.id, fitid="t1", transaction_date=date(2026, 1, 2),
                                   amount_cents=-100, entity_id=edf.id))
    db.session.commit()
    items = client.get("/api/v1/tiers").get_json()["items"]
    assert [e["name"] for e in items] == ["EDF", "Leroy Merlin"]  # adhérents à part
    assert items[0]["transactions"] == 1
    assert [e["name"] for e in client.get("/api/v1/tiers?q=leroy.fr").get_json()["items"]] == ["Leroy Merlin"]
    assert "1 transaction(s)" in _error(client.delete(f"/api/v1/tiers/{edf.id}"), 409)["message"]
    assert client.delete(f"/api/v1/tiers/{leroy.id}").status_code == 200


def test_tiers_detail_with_purchases_balance_work_times_and_helloasso(client):
    edf = Entity(name="EDF", entity_type="FOURNISSEUR", account_code="401001", is_member=True)
    account = Account(code="401001", label="EDF", account_type="TIERS")
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    journal = Journal(code="AC", label="Achats")
    charge = Account(code="606", label="Achats", account_type="EXPENSE")
    db.session.add_all([edf, account, fy, journal, charge])
    db.session.commit()
    from app.services.ledger import post_entry
    post_entry(fy.id, journal.id, date(2026, 3, 1), "F-009", [
        {"account_id": charge.id, "debit_cents": 12000, "credit_cents": 0},
        {"account_id": account.id, "debit_cents": 0, "credit_cents": 12000}])
    db.session.add(Purchase(qonto_id="si-9", invoice_number="F-009", entity=edf,
                            issue_date=date(2026, 3, 1), total_cents=12000))
    tt = TaskType(name="Caisse", hourly_rate_cents=2000)
    db.session.add(WorkTime(entity=edf, task_type=tt, work_date=date(2026, 4, 1), hours=1.5))
    order = HelloAssoOrder(helloasso_id=1, entity_id=edf.id, date=datetime(2026, 2, 1),
                           amount_total_cents=2500, form_slug="adhesion", form_type="Membership")
    db.session.add(order)
    db.session.flush()
    db.session.add(HelloAssoItem(helloasso_id=2, order_id=order.id, entity_id=edf.id, type="Membership",
                                 name="Adhésion", amount_cents=2500))
    db.session.commit()

    body = client.get(f"/api/v1/tiers/{edf.id}").get_json()
    assert body["supplier"] == {"account_code": "401001", "balance_cents": 12000}
    assert body["purchases"][0]["invoice_number"] == "F-009" and body["purchases"][0]["url"].startswith("/purchases/")
    assert body["work_times"][0]["valuation_cents"] == 3000
    assert body["item"]["last_helloasso_membership"].startswith("2026-02-01")
    assert body["helloasso"]["items"][0]["type"] == "Membership"
    assert body["pos_orders"] == [] and body["customer_invoices"] == []
    assert _error(client.get("/api/v1/tiers/999"), 404)


def test_tiers_actions_need_their_integration(client, monkeypatch):
    edf = Entity(name="EDF")
    db.session.add(edf)
    db.session.commit()
    assert "Odoo" in _error(client.post(f"/api/v1/tiers/{edf.id}/odoo-note"), 409)["message"]

    from app.api import entities as api_entities
    from app.services.helloasso_client import HelloAssoConfigError

    def not_configured():
        raise HelloAssoConfigError("HelloAsso n'est pas configuré.")
    monkeypatch.setattr(api_entities, "sync_helloasso", not_configured)
    assert _error(client.post("/api/v1/helloasso/sync"), 409)["message"] == "HelloAsso n'est pas configuré."
    monkeypatch.setattr(api_entities, "sync_helloasso", lambda: {
        "orders_imported": 1, "orders_updated": 0, "items_imported": 1, "items_updated": 0,
        "payments_imported": 0, "payments_updated": 0, "members_created": 1, "members_flagged": 0})
    body = client.post("/api/v1/helloasso/sync").get_json()
    assert body["notices"][0]["message"].startswith("Synchronisation HelloAsso terminée : 1 commande(s)")


# ------------------------------------------------------------------ adhérents


def _members():
    today = date.today()
    expired = Entity(name="Ancien", email="ancien@ex.org", entity_type="ADHERENT", is_member=True)
    fresh = Entity(name="Récent", email="recent@ex.org", entity_type="ADHERENT", is_member=True)
    unknown = Entity(name="Inconnu", entity_type="ADHERENT")
    db.session.add_all([expired, fresh, unknown])
    db.session.flush()
    for i, (entity, when) in enumerate(((expired, today - timedelta(days=400)), (fresh, today - timedelta(days=10)))):
        order = HelloAssoOrder(helloasso_id=10 + i, entity_id=entity.id,
                               date=datetime.combine(when, datetime.min.time()))
        db.session.add(order)
        db.session.flush()
        db.session.add(HelloAssoItem(helloasso_id=20 + i, order_id=order.id, entity_id=entity.id, type="Membership"))
    db.session.commit()
    return expired, fresh, unknown


def test_members_list_filters_and_exports(client):
    expired, fresh, unknown = _members()
    body = client.get("/api/v1/members?sort_by=status").get_json()
    assert [m["name"] for m in body["items"]] == ["Ancien", "Inconnu", "Récent"]
    colors = {m["name"]: (m["color"], m["status"]) for m in body["items"]}
    assert colors["Ancien"] == ("red", "ok") and colors["Récent"] == ("green", "ok") and colors["Inconnu"][1] == "?"
    assert body["meta"]["export_urls"]["csv"] == "/entities/members/export?format=csv&sort_by=status"
    since = (date.today() - timedelta(days=30)).isoformat()
    assert [m["name"] for m in client.get(f"/api/v1/members?date_from={since}").get_json()["items"]] == ["Récent"]
    assert client.get("/entities/members/export?format=csv").status_code == 200


def test_members_benevole_and_odoo_notes(client):
    expired, fresh, _ = _members()
    body = client.post("/api/v1/members/benevole", json={"ids": [expired.id, fresh.id], "value": True}).get_json()
    assert body["updated"] == 2 and "2 adhérent(s) marqué(s)" in body["notices"][0]["message"]
    client.post("/api/v1/members/benevole", json={"ids": [expired.id], "value": False})
    assert (db.session.get(Entity, expired.id).is_benevole, db.session.get(Entity, fresh.id).is_benevole) == (False, True)
    assert _error(client.post("/api/v1/members/benevole", json={"ids": [], "value": True}), 422)["message"] == \
        "Aucun adhérent sélectionné."
    assert _error(client.post("/api/v1/members/odoo-notes", json={"ids": [expired.id]}), 409)


def test_reminders_targets_and_sending(client, monkeypatch):
    expired, fresh, _ = _members()
    body = client.get("/api/v1/members/reminders").get_json()
    assert [m["name"] for m in body["items"]] == ["Ancien"]
    external_config.set_enabled("smtp", False)
    assert "SMTP" in _error(client.post("/api/v1/members/reminders", json={"ids": [expired.id]}), 409)["message"]

    from app.services import membership_reminders
    external_config.set_enabled("smtp", True)
    monkeypatch.setattr(membership_reminders, "smtp_configured", lambda: True)
    sent = []
    monkeypatch.setattr(membership_reminders, "send_reminders",
                        lambda rows: sent.extend(rows) or {"sent": len(rows), "errors": 0, "error_lines": []})
    body = client.post("/api/v1/members/reminders", json={"ids": [expired.id, fresh.id]}).get_json()
    assert [r["name"] for r in sent] == ["Ancien"]  # seuls les expirés sont relancés
    assert body["notices"][0]["message"] == "Relance : 1 email(s) envoyé(s), 0 erreur(s)."
    assert _error(client.post("/api/v1/members/reminders", json={"ids": [fresh.id]}), 422)


def test_reminder_template_preview_save_and_sandbox(client):
    body = client.get("/api/v1/members/reminder-template").get_json()
    assert body["item"]["subject"] and body["preview"]["sample"]["real"] is False

    preview = client.post("/api/v1/members/reminder-template/preview", json={
        "subject": "Bonjour {{ nom }}", "body_html": "<p>{{ date_anniversaire }}</p>"}).get_json()["preview"]
    assert preview["subject"] == "Bonjour Jean Dupont" and preview["error"] is None
    attack = client.post("/api/v1/members/reminder-template/preview", json={
        "subject": "x", "body_html": "{{ ''.__class__.__mro__[1].__subclasses__() }}"}).get_json()["preview"]
    assert attack["error"] and "unsafe" in attack["error"]

    assert "subject" in _error(client.put("/api/v1/members/reminder-template",
                                          json={"subject": "", "body_html": "x"}), 422)["fields"]
    client.put("/api/v1/members/reminder-template", json={"subject": "Relance", "body_html": "<p>Merci</p>"})
    assert EmailTemplate.query.one().subject == "Relance"


# ------------------------------------------------------------------ temps de travaux


def _benevole():
    ent = Entity(name="Alice", is_benevole=True)
    tt = TaskType(name="Caisse", hourly_rate_cents=2500)
    db.session.add_all([ent, tt])
    db.session.commit()
    return ent, tt


def test_work_times_crud_filters_and_totals(client):
    ent, tt = _benevole()
    resp = client.post("/api/v1/work-times", json={
        "entity_id": str(ent.id), "task_type_id": str(tt.id), "work_date": "2026-10-01", "hours": 2.5})
    item = resp.get_json()["item"]
    assert resp.status_code == 201 and item["valuation_cents"] == 6250
    client.post("/api/v1/work-times", json={
        "entity_id": ent.id, "task_type_id": tt.id, "work_date": "2026-09-01", "hours": 1, "notes": "tri"})

    body = client.get("/api/v1/work-times?month=2026-10").get_json()
    assert [w["work_date"] for w in body["items"]] == ["2026-10-01"]
    all_body = client.get(f"/api/v1/work-times?entity_id={ent.id}&sort=asc").get_json()
    assert [w["work_date"] for w in all_body["items"]] == ["2026-09-01", "2026-10-01"]
    assert all_body["meta"]["total_hours"] == 3.5 and all_body["meta"]["total_valuation_cents"] == 8750
    assert all_body["meta"]["benevoles"] == [{"value": str(ent.id), "label": "Alice"}]

    err = _error(client.post("/api/v1/work-times", json={"entity_id": ent.id, "hours": 0}), 422)
    assert set(err["fields"]) == {"task_type_id", "work_date", "hours"}
    upd = client.patch(f"/api/v1/work-times/{item['id']}", json={
        "entity_id": ent.id, "task_type_id": tt.id, "work_date": "2026-10-02", "hours": 3}).get_json()["item"]
    assert upd["work_date"] == "2026-10-02" and upd["hours"] == 3
    assert client.delete(f"/api/v1/work-times/{item['id']}").status_code == 200
    assert WorkTime.query.count() == 1


def test_work_times_import(client):
    _benevole()
    csv = "Bénévole;Type de tâche;Date;Heures;Notes\nAlice;Caisse;01/06/2026;2,5;\nBob;Caisse;02/06/2026;1;\n"
    resp = client.post("/api/v1/work-times/import", content_type="multipart/form-data",
                       data={"file": (io.BytesIO(csv.encode("utf-8-sig")), "temps.csv")})
    body = resp.get_json()
    assert body["result"]["imported"] == 1 and len(body["result"]["errors"]) == 1
    assert body["notices"][0]["level"] == "warning"
    assert "file" in _error(client.post("/api/v1/work-times/import", content_type="multipart/form-data",
                                        data={}), 422)["fields"]


# ------------------------------------------------------------------ recherche


def test_search_groups(client):
    db.session.add_all([Entity(name="EDF", email="contact@edf.fr"),
                        Purchase(qonto_id="s1", invoice_number="EDF-2026-01", supplier_name="EDF",
                                 issue_date=date(2026, 3, 1), total_cents=100)])
    db.session.commit()
    groups = client.get("/api/v1/search?q=edf").get_json()["groups"]
    assert [g["label"] for g in groups] == ["Tiers", "Factures d'achat"]
    assert groups[0]["items"][0]["url"].startswith("/entities/")
    assert groups[1]["items"][0]["label"] == "Facture EDF-2026-01"
    assert client.get("/api/v1/search?q=e").get_json()["groups"] == []
