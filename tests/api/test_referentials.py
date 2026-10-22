"""API des référentiels (phase B) : journaux, exercices, plan comptable, catalogue, règles,
types de tâches, utilisateurs ; pages servies par la SPA aux anciennes URL."""
from datetime import date

import pytest
from flask import url_for

from app.extensions import db
from app.models import (
    Account, Entity, FiscalYear, Journal, Product, Purchase, PurchaseLine, Rule, TaskType, User,
    WorkTime,
)


def _error(resp, status):
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()["error"]


@pytest.fixture()
def client(login_as):
    return login_as()


# ------------------------------------------------------------------ accès et pages


def test_api_requires_login(app):
    anonymous = app.test_client()
    for url in ("/api/v1/journals", "/api/v1/products", "/api/v1/rules", "/api/v1/task-types"):
        assert _error(anonymous.get(url), 401)["code"] == "unauthenticated"


@pytest.mark.parametrize("url", [
    "/journals/", "/journals/new", "/fiscal-years/new", "/accounts/", "/accounts/new",
    "/accounts/3/edit", "/products/", "/products/2/edit", "/rules/", "/rules/new",
    "/work-times/task-types", "/work-times/task-types/4/edit",
])
def test_pages_served_by_spa(client, url):
    resp = client.get(url)
    assert resp.status_code == 200 and '<div id="root"></div>' in resp.get_data(as_text=True)


def test_old_links_still_resolve(app):
    with app.test_request_context():
        assert url_for("accounts.new") == "/accounts/new"
        assert url_for("fiscal_years.new") == "/fiscal-years/new"
        assert url_for("work_times.task_types") == "/work-times/task-types"
        assert url_for("products.edit", product_id=5) == "/products/5/edit"


# ------------------------------------------------------------------ journaux


def test_journals(client):
    db.session.add(Journal(code="VT", label="Ventes"))
    db.session.commit()
    resp = client.post("/api/v1/journals", json={"code": " ac ", "label": "Achats"})
    assert resp.status_code == 201 and resp.get_json()["item"]["code"] == "AC"
    assert resp.get_json()["notices"][0]["message"] == "Journal AC créé."
    assert [j["code"] for j in client.get("/api/v1/journals").get_json()["items"]] == ["AC", "VT"]
    assert _error(client.post("/api/v1/journals", json={"code": "VT", "label": "x"}), 422)["fields"] == {
        "code": "Le journal VT existe déjà."}
    assert "label" in _error(client.post("/api/v1/journals", json={"code": "OD"}), 422)["fields"]
    assert "code" in _error(client.post("/api/v1/journals", json={"code": "X" * 11, "label": "x"}), 422)["fields"]


# ------------------------------------------------------------------ exercices


def test_fiscal_years_create_vat_and_close(client):
    create = lambda **kw: client.post("/api/v1/fiscal-years", json={
        "label": "2027", "start_date": "2027-01-01", "end_date": "2027-12-31", **kw})
    fy27 = create(vat_liable=True).get_json()["item"]
    fy28 = create(label="2028", start_date="2028-01-01", end_date="2028-12-31").get_json()["item"]
    assert fy27["vat_liable"] and not fy28["vat_liable"]
    assert [f["label"] for f in client.get("/api/v1/fiscal-years").get_json()["items"]] == ["2028", "2027"]

    body = client.patch(f"/api/v1/fiscal-years/{fy28['id']}", json={"vat_liable": True}).get_json()
    assert body["item"]["vat_liable"] and "soumis à la TVA" in body["notices"][0]["message"]

    assert client.post(f"/api/v1/fiscal-years/{fy27['id']}/close").get_json()["item"]["closed"]
    assert _error(client.post(f"/api/v1/fiscal-years/{fy27['id']}/close"), 409)["code"] == "conflict"
    assert _error(client.patch(f"/api/v1/fiscal-years/{fy27['id']}", json={"vat_liable": False}), 409)
    assert db.session.get(FiscalYear, fy27["id"]).vat_liable is True


def test_fiscal_year_validation(client):
    err = _error(client.post("/api/v1/fiscal-years", json={
        "label": "2027", "start_date": "2027-12-31", "end_date": "2027-01-01"}), 422)
    assert "end_date" in err["fields"]
    assert "start_date" in _error(client.post("/api/v1/fiscal-years", json={
        "label": "x", "start_date": "31/12/2027", "end_date": "2027-01-01"}), 422)["fields"]
    assert _error(client.patch("/api/v1/fiscal-years/99", json={"vat_liable": True}), 404)


# ------------------------------------------------------------------ plan comptable


def test_chart_of_accounts(client):
    db.session.add(Account(code="60", label="Achats", account_type="EXPENSE", is_header=True))
    db.session.commit()
    resp = client.post("/api/v1/chart-of-accounts", json={
        "code": "6061", "label": "Fournitures", "account_type": "EXPENSE", "parent_code": "60"})
    item = resp.get_json()["item"]
    assert resp.status_code == 201 and item["parent_code"] == "60"
    body = client.get("/api/v1/chart-of-accounts").get_json()
    assert [a["code"] for a in body["items"]] == ["60", "6061"] and body["items"][0]["is_header"]
    assert {"value": "EXPENSE", "label": "Charge"} in body["meta"]["types"]

    upd = client.patch(f"/api/v1/chart-of-accounts/{item['id']}",
                       json={"label": "Fournitures non stockables", "account_type": "EXPENSE", "code": "999"})
    assert upd.get_json()["item"]["label"] == "Fournitures non stockables"
    assert db.session.get(Account, item["id"]).code == "6061"  # le code ne change pas

    assert "code" in _error(client.post("/api/v1/chart-of-accounts", json={"code": "6061", "label": "x"}), 422)["fields"]
    assert "parent_code" in _error(client.post("/api/v1/chart-of-accounts", json={
        "code": "607", "label": "x", "parent_code": "99"}), 422)["fields"]
    assert "account_type" in _error(client.post("/api/v1/chart-of-accounts", json={
        "code": "607", "label": "x", "account_type": "FOO"}), 422)["fields"]


# ------------------------------------------------------------------ catalogue


def _accounts():
    db.session.add_all([Account(code="6061", label="Fournitures non stockables", account_type="EXPENSE"),
                        Account(code="706", label="Prestations de services", account_type="REVENUE")])
    db.session.commit()


def test_products_create_edit_archive(client):
    _accounts()
    resp = client.post("/api/v1/products", json={
        "name": "Électricité", "kind": "purchase", "purchase_account_code": "6061", "vat_rate": "20"})
    item = resp.get_json()["item"]
    assert resp.status_code == 201
    assert item["purchase_account"]["code"] == "6061" and item["vat_rate_bp"] == 2000 and item["vat_rate"] == "20"

    body = client.get("/api/v1/products").get_json()
    assert [p["name"] for p in body["items"]] == ["Électricité"]
    assert body["meta"]["purchase_accounts"] == [{"code": "6061", "label": "Fournitures non stockables"}]

    upd = client.patch(f"/api/v1/products/{item['id']}", json={
        "name": "Électricité", "kind": "both", "purchase_account_code": "6061",
        "sale_account_code": "706", "vat_rate": "5,5"}).get_json()["item"]
    assert upd["sale_account"]["code"] == "706" and upd["vat_rate"] == "5,5"

    assert client.patch(f"/api/v1/products/{item['id']}", json={"active": False}).get_json()["item"]["active"] is False
    assert client.get("/api/v1/products").get_json()["items"] == []
    assert len(client.get("/api/v1/products?archived=1").get_json()["items"]) == 1


def test_invalid_product(client):
    _accounts()
    err = _error(client.post("/api/v1/products", json={
        "name": "Électricité", "kind": "purchase", "purchase_account_code": "706"}), 422)
    assert "commencer par 6" in err["message"]
    assert Product.query.count() == 0


def test_used_product_cannot_be_deleted(client):
    product = Product(name="Assurance", kind="purchase")
    unused = Product(name="Divers", kind="purchase")
    purchase = Purchase(qonto_id="si-1", total_cents=100)
    purchase.lines.append(PurchaseLine(product=product, total_cents=100))
    db.session.add_all([product, unused, purchase])
    db.session.commit()
    assert "utilisé 1 fois" in _error(client.delete(f"/api/v1/products/{product.id}"), 409)["message"]
    assert client.delete(f"/api/v1/products/{unused.id}").status_code == 200
    assert [p.name for p in Product.query.all()] == ["Assurance"]
    assert client.get("/api/v1/products").get_json()["items"][0]["usages"] == 1


# ------------------------------------------------------------------ règles


def test_rules_crud_order_and_toggle(client):
    db.session.add(Account(code="606", label="Achats", account_type="EXPENSE"))
    db.session.commit()
    first = client.post("/api/v1/rules", json={
        "name": "EDF", "label_contains": "EDF", "account_code": "606", "amount_min_cents": 1050}).get_json()["item"]
    second = client.post("/api/v1/rules", json={"name": "Free", "label_contains": "FREE"}).get_json()["item"]
    assert (first["position"], second["position"]) == (1, 2) and first["amount_min_cents"] == 1050

    order = client.post(f"/api/v1/rules/{second['id']}/move", json={"direction": "up"}).get_json()["items"]
    assert [r["name"] for r in order] == ["Free", "EDF"]
    order = client.post(f"/api/v1/rules/{second['id']}/move", json={"direction": "up"}).get_json()["items"]
    assert [r["name"] for r in order] == ["Free", "EDF"]  # déjà en tête

    body = client.patch(f"/api/v1/rules/{first['id']}", json={"is_active": False}).get_json()
    assert body["item"]["is_active"] is False and "désactivée" in body["notices"][0]["message"]
    upd = client.patch(f"/api/v1/rules/{first['id']}", json={
        "name": "EDF énergie", "label_contains": "EDF", "is_active": True}).get_json()["item"]
    assert upd["name"] == "EDF énergie" and upd["account_code"] is None
    assert client.delete(f"/api/v1/rules/{first['id']}").status_code == 200
    assert [r.name for r in Rule.query.all()] == ["Free"]


def test_rules_validation_and_apply(client):
    assert "Au moins une condition" in _error(client.post("/api/v1/rules", json={"name": "Vide"}), 422)["message"]
    assert "min doit être" in _error(client.post("/api/v1/rules", json={
        "name": "x", "amount_min_cents": 500, "amount_max_cents": 100}), 422)["message"]
    assert _error(client.post("/api/v1/rules", json={"name": "x", "amount_min_cents": "abc"}), 422)
    assert _error(client.post("/api/v1/rules/1/move", json={"direction": "left"}), 404)
    body = client.post("/api/v1/rules/apply", json={"overwrite": False}).get_json()
    assert body["result"]["total"] == 0 and body["notices"][0]["message"].startswith("Règles appliquées")


# ------------------------------------------------------------------ types de tâches


def test_task_types(client):
    created = client.post("/api/v1/task-types", json={"name": "Compta", "hourly_rate_cents": 2550})
    item = created.get_json()["item"]
    assert created.status_code == 201 and item["hourly_rate_cents"] == 2550 and item["is_active"]
    assert "name" in _error(client.post("/api/v1/task-types", json={"name": "compta"}), 422)["fields"]
    assert "hourly_rate_cents" in _error(client.post("/api/v1/task-types", json={
        "name": "Caisse", "hourly_rate_cents": -1}), 422)["fields"]
    upd = client.patch(f"/api/v1/task-types/{item['id']}", json={
        "name": "Comptabilité", "hourly_rate_cents": 3000, "is_active": False}).get_json()["item"]
    assert upd["name"] == "Comptabilité" and not upd["is_active"]

    ent = Entity(name="X", is_benevole=True)
    db.session.add(ent)
    db.session.commit()
    db.session.add(WorkTime(entity_id=ent.id, task_type_id=item["id"], work_date=date(2026, 6, 1), hours=1))
    db.session.commit()
    assert client.get("/api/v1/task-types").get_json()["items"][0]["work_times"] == 1
    assert "Impossible de supprimer" in _error(client.delete(f"/api/v1/task-types/{item['id']}"), 409)["message"]
    free = client.post("/api/v1/task-types", json={"name": "Libre"}).get_json()["item"]
    assert client.delete(f"/api/v1/task-types/{free['id']}").status_code == 200
    assert TaskType.query.count() == 1


# ------------------------------------------------------------------ utilisateurs


def test_users_admin_only(login_as):
    client = login_as()
    assert _error(client.get("/api/v1/users"), 403)["code"] == "forbidden"
    assert _error(client.post("/api/v1/users", json={"email": "x@y.z", "password": "p"}), 403)


def test_users_crud_and_self_protection(login_as):
    client = login_as(is_admin=True)
    me = User.query.one()
    created = client.post("/api/v1/users", json={
        "email": " Benevole@Example.org ", "password": "secret", "full_name": "Bénévole"})
    item = created.get_json()["item"]
    assert created.status_code == 201 and item["email"] == "benevole@example.org" and item["is_active"]
    assert "password" in _error(client.post("/api/v1/users", json={"email": "a@b.c"}), 422)["fields"]
    assert "email" in _error(client.post("/api/v1/users", json={
        "email": "benevole@example.org", "password": "x"}), 422)["fields"]

    upd = client.patch(f"/api/v1/users/{item['id']}", json={
        "email": "benevole@example.org", "full_name": "", "is_admin": True, "is_active": True}).get_json()["item"]
    assert upd["is_admin"] and upd["full_name"] is None
    assert db.session.get(User, item["id"]).check_password("secret")  # inchangé sans nouveau mot de passe

    assert client.patch(f"/api/v1/users/{item['id']}", json={"is_active": False}).get_json()["item"]["is_active"] is False
    assert _error(client.patch(f"/api/v1/users/{me.id}", json={"is_active": False}), 409)
    assert "propre statut admin" in _error(client.patch(f"/api/v1/users/{me.id}", json={
        "email": me.email, "is_admin": False, "is_active": True}), 422)["message"]
    assert _error(client.delete(f"/api/v1/users/{me.id}"), 409)
    assert client.delete(f"/api/v1/users/{item['id']}").status_code == 200
    users = client.get("/api/v1/users").get_json()["items"]
    assert [u["is_me"] for u in users] == [True]


def test_users_api_needs_no_instance(app):
    """Méta-base seulement : utilisable sans instance choisie (comme les pages /users)."""
    admin = User(email="admin@example.org", is_admin=True)
    admin.set_password("x")
    db.session.add(admin)
    db.session.commit()
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(admin.id)
    assert client.get("/api/v1/users").status_code == 200
    assert client.get("/users/").status_code == 200
