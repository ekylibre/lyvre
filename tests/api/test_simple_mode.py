"""Lot D.2 : mode de tenue par instance (menus de la comptabilité simplifiée, choix à la création)
et catégories de recettes / dépenses pré-remplies depuis le plan associatif."""
import pytest

from app.extensions import db
from app.menu_config import build_nav
from app.models import Account, Instance, SimpleCategory

DOUBLE_ONLY = {"Écritures", "Balance", "Grand livre", "Bilan", "Compte de résultat", "Plan comptable", "Journaux",
               "Catalogue", "Rapprochement", "Factures d'achat"}


def _error(resp, status):
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()["error"]


def _labels(nav):
    out = set()
    for menu in nav:
        out.add(menu["label"])
        out.update(i["label"] for i in menu.get("items", []) if "label" in i)
    return out


def test_simple_mode_hides_double_entry_screens():
    simple = _labels(build_nav("asso", is_admin=True, bookkeeping="simple"))
    double = _labels(build_nav("asso", is_admin=True, bookkeeping="double"))
    assert not simple & DOUBLE_ONLY
    assert DOUBLE_ONLY <= double and "Catégories" not in double
    assert {"Catégories", "Comptes et caisses", "Exercices", "Budget", "Projets", "Reçus fiscaux"} <= simple
    assert _labels(build_nav("asso", is_admin=True)) == double  # défaut : partie double


def test_session_exposes_mode(app, login_as):
    client = login_as(role="admin")
    Instance.query.one().bookkeeping = "simple"
    db.session.commit()
    body = client.get("/api/v1/session").get_json()
    assert body["instance"]["bookkeeping"] == "simple"
    assert "Écritures" not in _labels(body["nav"])


def test_instance_creation_mode(app, login_as, tmp_path, monkeypatch):
    from app.api import instances as api_instances
    monkeypatch.setattr(api_instances, "provision_sqlite_database", lambda url, chart: None)
    client = login_as(is_admin=True, role="admin")
    created = client.post("/api/v1/instances", json={"slug": "petite-asso", "label": "Petite asso", "chart": "asso",
                                                     "bookkeeping": "simple"})
    assert created.status_code == 201 and created.get_json()["item"]["bookkeeping"] == "simple"
    assert "associations" in _error(client.post("/api/v1/instances", json={
        "slug": "sci-x", "label": "SCI X", "chart": "sci", "bookkeeping": "simple"}), 422)["message"]
    _error(client.post("/api/v1/instances", json={"slug": "y", "label": "Y", "bookkeeping": "autre"}), 422)


@pytest.fixture()
def chart(app):
    db.session.add_all([Account(code=c, label=f"Compte {c}", account_type="OTHER")
                        for c in ("756", "7541", "74", "706", "6061", "613", "6411", "512")])
    db.session.commit()


def test_default_categories_and_edit(chart, login_as):
    client = login_as()
    body = client.get("/api/v1/simple-categories").get_json()
    by_code = {c["code"]: c for c in body["items"]}
    assert by_code["cotisations"]["account"]["code"] == "756" and by_code["cotisations"]["kind"] == "income"
    assert by_code["achats"]["account"]["code"] == "6061"      # sous-compte de 606
    assert by_code["salaires"]["account"]["code"] == "6411"
    assert "assurances" not in by_code                          # pas de 616 dans le plan : omise
    assert "autres_recettes" not in by_code                     # le seul 75x (756) est déjà aux cotisations
    assert [c["kind"] for c in body["items"]][:4] == ["income"] * 4  # recettes d'abord
    client.get("/api/v1/simple-categories")
    assert SimpleCategory.query.count() == len(by_code)        # pas de doublon au second accès
    ids = {a.code: a.id for a in Account.query}
    created = client.post("/api/v1/simple-categories", json={"label": "Buvette", "kind": "income", "account_id": ids["706"]})
    assert created.status_code == 201
    assert "compte 7" in _error(client.post("/api/v1/simple-categories", json={
        "label": "X", "kind": "income", "account_id": ids["613"]}), 422)["message"]
    cat = by_code["locations"]
    assert client.put(f"/api/v1/simple-categories/{cat['id']}", json={
        "label": "Loyers", "account_id": ids["613"], "active": False}).get_json()["item"]["active"] is False
    first, second = [c for c in client.get("/api/v1/simple-categories").get_json()["items"] if c["kind"] == "income"][:2]
    client.post(f"/api/v1/simple-categories/{second['id']}/move", json={"direction": "up"})
    order = [c["id"] for c in client.get("/api/v1/simple-categories").get_json()["items"] if c["kind"] == "income"][:2]
    assert order == [second["id"], first["id"]]
